# F69 Unit 1 — Functional Design (minimal)

> Health Check TUI 통합. 데이터 모델은 F63 `HealthReport`로 확정 → 신규 모델 없음.
> 설계는 기존 패턴(monitor.json 발행 + TUI poll-diff + 클릭 오버레이)을 그대로 미러한다.

## A. Producer (Python 데몬) — **경량 subset 발행** (critic HIGH 대응)

> **중요(critic 검증).** F63 `run_all_checks`(9차원 전체)는 publish 1회당 **broker 5개 생성**
> (`broker.py:34,60,87` + `account.py:22` + `risk.py:101`, 각 `AlpacaBroker.__init__` init 로그
> `alpaca_broker.py:96`) + **실제 LLM API ping**(`llm.py:63`, 매번 무조건) + 데이터 provider
> 생성(`data_pipeline.py:36`)을 한다. 5분 주기면 LLM 288회/일 + init 로그 ~1440줄/일.
> → 데몬 주기 발행은 **전체 9차원을 돌리지 않는다.** 외부 호출 없는 cheap 차원만 + 데몬이 이미
> 가진 데이터 재사용. 전체 9차원 deep check는 `scripts/health.py`(FR-4)로 on-demand 유지.

### A1. 발행 메서드 — `SteeringRuntime.publish_health()`
`src/agent/steering/runtime.py`에 추가 (publish_monitor 인접). F63 모듈 **로직 변경 없음** —
공개 API(`CheckerDispatcher.register_all`)로 cheap 차원만 등록해 실행한다.

```
# imports (runtime.py 상단)
from src.monitoring.health import CheckerDispatcher
from src.monitoring.health.dimensions.process import ProcessChecker
from src.monitoring.health.dimensions.logs import LogChecker
from src.monitoring.health.dimensions.config_env import ConfigEnvChecker
from src.monitoring.health.dimensions.resources import ResourceChecker
from config.config import get_settings

def publish_health(self) -> None:
    """경량 시스템 health를 steering/health.json에 발행 (외부 호출 없음, 비차단).
    cheap 차원(process/logs/config_env/resources)만 실행하고, account/market은
    데몬이 이미 보유한 self.last_snapshot에서 파생(broker 재호출 없음)."""
    try:
        s = get_settings()
        d = CheckerDispatcher(s)                 # F63 공개 API, 로직 무변경
        d.register_all([ProcessChecker(s), LogChecker(s),
                        ConfigEnvChecker(s), ResourceChecker(s)])
        report = d.run()                          # 외부 broker/LLM/network 미접촉, 로컬만
        self._augment_health_from_snapshot(report)  # account/market 재사용 (A1a)
        payload = report.model_dump(mode="json")
        payload["publish_interval_seconds"] = s.monitoring.health_publish_seconds  # #6: TUI stale 계산용
    except Exception as e:
        logger.warning("health publish failed (keeping last health.json): {}", e)
        return                                    # 예기치 못한 크래시에서만 직전값 유지
    atomic_write_text(self.steering_dir / "health.json", json.dumps(payload, default=str))
```

- **외부 호출 0**: cheap 4차원은 broker/network/LLM을 건드리지 않는다(로컬 파일·proc·disk
  subprocess만 — `process.py`, `logs.py`, `config_env.py`, `resources.py` 검증). NFR-2 복원.
- **settings**: `SteeringRuntime`/agent.py 모두 `self.settings` 미보유 → `get_settings()`
  (`@lru_cache`, 저렴) 직접 호출. 생성자 변경 불필요.

### A1a. account/market 파생 — `_augment_health_from_snapshot(report)`
데몬은 `publish_snapshot`에서 `self.last_snapshot`(account 블록, market_open, positions)을 이미
보관(`runtime.py:97,278`). broker **재호출 없이** 이걸로 "account" 차원 1개를 합성:
- `last_snapshot` None(아직 스냅샷 전)이면 → account 차원 status=SKIPPED("no snapshot yet"), graceful.
- 있으면 → equity/포지션수/market_open 요약을 `DimensionResult("account", checks=[...])`로 추가.
  (cash/buying_power 음수 등 명백 이상만 WARNING; 단순 표시 위주.)
- `DimensionResult`/`CheckResult`/`CheckStatus`는 `src.monitoring.health.report`에서 import.
- 합성 후 `report.overall`을 cheap차원+account 최악값으로 재계산.

### A2. 기동 — 스케줄러 seconds-job (별도 풀 워커)
`src/trading/modes/agent.py`의 `if self.steering is not None:` 블록에 추가 (agent.py도
`self.settings` 미보유 → `get_settings()`; 0이면 미등록):

```
_hp = get_settings().monitoring.health_publish_seconds
if _hp > 0:
    self.scheduler.add_seconds_job(self.steering.publish_health, _hp, "steering_health")
```

- **왜 raw Thread가 아니라 scheduler job인가**: APScheduler `BackgroundScheduler` +
  `ThreadPoolExecutor(16)`, `max_instances=1`(자기중복 방지), `coalesce=True`(`scheduler.py:23`).
  이 job은 2초 command-poll·5초 snapshot과 **다른 풀 워커**에서 돌아 핫루프/트레이딩을 막지
  않는다(NFR-1). max_instances=1+16워커라 자기중복·풀 starvation 없음(critic 검증 OK).
- **실행 비용/시간**: cheap subset은 로컬 전용이라 통상 1초 미만. (참고: `CheckerDispatcher.run`은
  내부적으로 `ThreadPoolExecutor(6)`를 잠깐 띄운다 — "스케줄러 워커 1 + 내부 6"이며, cheap
  차원이라 거의 즉시 종료. 전체 9차원이었다면 broker HTTP로 최악 ~20-30s였을 것 → subset이 이를 회피.)

### A3. 설정 — `MonitoringConfig.health_publish_seconds`
`config/config.py` `MonitoringConfig`에 필드 추가:
```
health_publish_seconds: int = 300   # F69: steering/health.json 발행 주기(초). 0이면 비활성.
```
- `0`이면 job 미등록(off 스위치). settings.yaml에서 오버라이드 가능.

## B. Consumer (TUI — `operator-console/cli/packages/tui-trading`, TS/SolidJS)

### B1. TS 타입 — `src/types.ts`
F63 report.py 미러 (CheckStatus enum 값 = OK/WARNING/ERROR/CRITICAL/SKIPPED):
```
export interface HealthCheck { name: string; status: HealthStatus; detail?: string; error?: string | null }
export interface HealthDimension { dimension: string; status: HealthStatus; checks: HealthCheck[] }
export type HealthStatus = "OK" | "WARNING" | "ERROR" | "CRITICAL" | "SKIPPED"
export interface HealthReport {
  run_id: string; ts: string; duration_ms: number;
  overall: HealthStatus; summary: string;
  dimensions: Record<string, HealthDimension>;
  publish_interval_seconds?: number;   // A1 동봉, stale 계산용
}
```
- 주기 발행은 cheap subset(process/logs/config_env/resources) + 파생 account = **5개 차원**만
  담긴다(전체 9개 아님). 오버레이는 `dimensions`를 동적으로 순회하므로 개수 가변 OK.
- `OverlayState`에 `health: HealthReport | null` 필드 + `type: "health"` 추가.

### B2. 폴링 훅 — `src/hooks/use-health-data.ts` (use-monitor-data.ts 미러)
- `useHealthData(steeringDir, intervalMs=5000)` → `health.json` 읽기.
- **poll-and-diff (NFR-3, critic #5 반영)**: content signature는 `overall + 각 dimension.status
  + 실패(OK 아닌) check name 집합`만 사용. **휘발 필드 제외**: `ts`/`run_id`/`duration_ms`,
  그리고 per-check `duration_ms`·변동 `detail`(equity·resting order 수 등)도 시그니처에서 뺀다.
  (use-monitor-data.ts:11-22가 휘발 필드를 의도적으로 빼는 것과 동일 — dimensions를 통째로
  넣으면 매 publish 시그니처가 바뀌어 무churn이 깨짐.)
- 파일 부재/torn JSON → 직전 양호값 유지(return). 최초 부재 시 `null`.
  (참고: 데몬은 `atomic_write_text`=temp+`os.replace`로 쓰므로 리더는 torn JSON을 실제로는
  보지 않음(critic 검증) — `JSON.parse` 가드는 안전망.)
- **stale 판정 (critic #6 반영)**: 임계를 TS에 하드코딩하지 않는다. health.json의
  `publish_interval_seconds`(A1에서 동봉)를 읽어 `now - ts > interval*3`이면 `stale=true`.
  필드 부재 시 보수적 고정값(20분) fallback.
- 반환: `{ health: () => HealthReport | null, stale: () => boolean }`.

### B3. 상단바 글리프 — TimelineBar 우측 끝 셀
`src/components/timeline-bar.tsx`에 health 글리프 셀 추가 (또는 우측 코너 오버레이 셀).
- props 확장: `health?: () => HealthReport | null`, `healthStale?: () => boolean`,
  `onHealthClick?: (x, y) => void`.
- 글리프/색 (`utils/format.ts`에 `healthGlyph/healthColor` 추가):
  | status | glyph | color |
  |--------|-------|-------|
  | OK | ✓ | green |
  | WARNING | ⚠ | yellow |
  | ERROR | ✗ | red |
  | CRITICAL | ⊘ | red(강조) |
  | SKIPPED / stale / no-data | ○ | dim |
- 클릭 시 `onHealthClick(x, y)` 호출(셀 좌표 anchor) — z-order/hit-test 규약 준수
  [[opentui-zorder-hittest]] (글리프 셀이 마커보다 위, 클릭 보존).

### B4. 오버레이 — `src/components/health-overlay.tsx` (turn-overlay 패턴)
- props: `report: HealthReport`, `anchorX/Y`, `termWidth/Height`, `onClose`.
- `OverlayPanel` 재사용. 헤더: `overall` 글리프 + summary + ts(상대시각).
- 본문: 9개 차원 리스트 — 각 `dimension`의 status 글리프 + 이름, 그 아래 OK 아닌 sub-check의
  `name: detail/error`. OK 차원은 한 줄 요약.
- 닫기: `onClose`(ESC/재클릭). 드릴다운 불필요(정보량 적음) — 평면 리스트.

### B5. 오버레이 스토어 — `src/hooks/use-overlay.ts`
- `openHealth(report, x, y)` 추가 (turn/symbol과 동일 토글 패턴: 이미 health면 close).
- `index.ts`: `useHealthData`, `HealthOverlay` export.

## C. 호스트 앱 wiring — `opencode .../routes/session/index.tsx`
- import: `useHealthData`, `HealthOverlay` (`@tui-trading/core`).
- `const healthHooks = steeringDir ? useHealthData(steeringDir) : null`.
- `<TimelineBar ... health={health} healthStale={stale} onHealthClick={(x,y)=>overlay.openHealth(health()!, x, y)} />`.
- overlay 컨테이너에 `<Show when={overlay.state().type === "health" && overlay.state().health}>` →
  `<HealthOverlay report=... anchorX/Y=... termWidth/Height=... onClose=.../>`.

## D. 미적용/주의
- 기존 `MonitorTurn.health`(턴별 ok/error)와 **이름만 겹침** — 별개 개념(시스템 health). 혼동
  방지 위해 타입/컴포넌트 명에 Health(시스템) 명확화. (TS 스코프상 컴파일 충돌은 없음 — critic 검증.)
- `scripts/health.py` 무변경(FR-4) — **전체 9차원 deep check는 여기 유지**(broker/llm/account/risk
  live 포함). 데몬 주기 발행은 cheap subset만(A 머리말).
- **F63 health 모듈(`src/monitoring/health/*`) 로직 무변경** — `CheckerDispatcher.register_all`
  공개 API로 차원 subset만 등록(범위 밖 준수).

## E. critic 리뷰 반영 요약 (검증 후)
- **HIGH(broker 5개+LLM ping+로그 스팸)**: 주기 발행을 cheap subset + 스냅샷 재사용으로 전환 (A 머리말/A1/A1a). → 외부 호출 0, NFR-2 복원.
- **MEDIUM(타이밍/스레드 표현)**: A2에 실제 모델(스케줄러 워커1+내부 풀6, subset은 <1s) 명시.
- **MEDIUM(FR-3 dead code)**: 아래 추적성 FR-3 정정 — 열화 리포트는 발행하는 게 맞고, try/except는 예기치 못한 크래시 안전망.
- **LOW(#5 churn)**: B2 시그니처를 status 집합으로 한정.
- **LOW(#6 stale)**: `publish_interval_seconds` 페이로드 동봉 + TS가 읽음 (A1/B1/B2).

## 추적성
- FR-1→A2 · FR-2→A1 · **FR-3→A1(예외=직전값 유지는 *예기치 못한 크래시* 한정; cheap 차원의
  통상 실패는 `run_safe`가 흡수해 열화 리포트로 *정상 발행*되며 이게 health 모니터로서 올바름)**
  · FR-4→D · FR-5→B2 · FR-6→B3 · FR-7→B4/B5/C.
- NFR-1→A2 · **NFR-2→A/A1(주기 발행은 외부 호출 없는 cheap subset; 전체 deep check만 외부 호출,
  그건 scripts/health.py 수동 실행에 한정)** · NFR-3→B2 · NFR-4→B2/B3.
