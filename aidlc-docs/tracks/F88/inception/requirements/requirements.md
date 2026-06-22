# F88 Requirements — Agent self-authored long-horizon triggers

> Depth: **comprehensive** (agent 작성 코드 실행 + 격리가 핵심이라 보안 추적 필요).
> 작성: F88 worktree 세션 (single writer). 베이스라인: CodeKB (read-only).

## 1. 배경 / 문제

trading agent는 현재 daemon-side `WakeDetector`(`src/agent/intraday/wake.py`)가 감지하는
**고정 조건**(fill / 급변동 / `WatchStore` 가격알림)으로만 out-of-band wake된다. 이는 장중·종목
수준의 *마이크로* 트리거다. agent가 스스로 정의하는 **macro·뉴스 수준의 장기(long-horizon) 조건**
(예: "VIX 25 돌파 + SPY 5일 -4%", "반도체 capex 하향 뉴스 다발")으로 대기했다가 self-wake하는
경로는 없다. 또한 agent는 autostock이 큐레이션한 시그널만 보며, "큐레이션 밖의 것을 자유롭게
관찰"할 자율성이 없다.

## 2. 목표 / 비목표

**목표**
- agent가 long-horizon 트리거를 **직접 Python predicate 코드로** 작성·등록·조회·취소.
- 트리거 발화 시 agent를 **self-wake**(wake turn 예약), agent가 추론 → 기존 매매 경로(gate) 사용.
- agent에게 **큐레이션 밖 데이터**(WebSearch/allowlist WebFetch 포함)를 트리거 조건에 끌어쓸 자유 부여.

**비목표 (out of scope)**
- 트리거가 직접 주문/매매하는 것 (predicate는 `{fire, why}`만 반환, 매매 능력 0).
- agent 작성 코드가 autostock `src/`를 읽거나 수정하는 것 (구조적 차단이 핵심 요구).
- 장중 마이크로 wake 대체 (기존 `WakeDetector`는 유지; F88은 보완·상위 레이어).
- 백테스트/시뮬레이션상의 트리거 (라이브 daemon 한정).

## 3. 락된 아키텍처 (설계 토의 결과 — design 단계 입력)

```
agent turn ──MCP(HTTP loopback +토큰)──▶ daemon control plane (신뢰)
 register/list/cancel/inspect              ├─ TriggerStore: workspace/triggers/<id>/
                                           │    trigger.md(spec)  predicate.py(agent)  state.json(daemon)
                                           ├─ brokered fetch (선언 소스 → ctx.json)
                                           └─ TriggerEvaluator (느린 cadence, hourly floor)
                                                └─ Docker 샌드박스 실행 (execution plane, 불신)
                                                     src 미마운트 / --network=none / --read-only
                                                     cap-drop=ALL / non-root / no-new-privileges
                                                     mem·cpu·pids 상한 / timeout / 시크릿 제거 env / tmpfs
                                                   → {fire,why} → rate-limit
                                                   → TurnCoordinator.trigger(WakeEvent "agent_trigger")
                                                        └─▶ wake turn (매매는 supervisor gate 통과)
```

**control plane(신뢰: MCP·brokered fetch·평가루프) ↔ execution plane(불신: predicate)** 분리가 보안의 핵.

## 4. 기능 요구사항 (FR)

- **FR-1 트리거 등록**: agent가 MCP `trigger.register`로 트리거 생성. 입력 = spec(thesis, expires,
  cadence, 선언 데이터 소스) + predicate.py 본문. daemon이 검증(스키마 + AST 스크린) 후 저장.
- **FR-2 트리거 조회/취소**: MCP `trigger.list`(요약), `trigger.inspect`(상세+최근 평가 결과/근거),
  `trigger.cancel`. 살아있는 레지스트리를 daemon이 노출(stdio 불가 → HTTP loopback).
- **FR-3 저장**: 트리거당 `workspace/triggers/<id>/`에 `trigger.md`(spec, agent), `predicate.py`(agent),
  `state.json`(daemon 관리: created/last_run/last_verdict/fired_count/consecutive_errors/disabled).
- **FR-4 브로커드 데이터 주입**: daemon이 트리거 선언 소스를 대신 fetch해 `ctx.json` 조립. predicate는
  ctx만 보고 네트워크 0. **카탈로그 (R1 승인 + critic#2 정정): `signal`=기존 signals(macro/movers/
  earnings/holdings/sentiment, `collector.collect` 직접 호출) + `webfetch`=allowlist 도메인 URL을
  daemon이 httpx GET.** 일반 `websearch`(검색 API+키 필요)는 **첫 컷 제외, 후속**. (WebSearch/WebFetch
  CLI 툴은 claude 턴 전용이라 daemon 파이썬에서 호출 불가 — critic 확인.)
- **FR-5 격리 평가**: daemon이 predicate를 일회용 Docker 컨테이너에서 실행. `src/` 미마운트,
  `--network=none --read-only`, cap-drop=ALL, non-root, no-new-privileges, mem/cpu/pids 상한,
  wall-clock timeout, 시크릿 제거 env, 쓰기는 tmpfs만. 진입점이 `predicate.py`의
  `should_fire(ctx) -> {fire: bool, why: str}`를 호출, stdout(크기 cap)로 결과 회수.
- **FR-6 평가 cadence**: `TriggerEvaluator`가 트리거별 cadence로 평가. **최소 주기 floor = hourly
  (R4, 승인됨)**; hourly/daily 선택 가능(더 짧은 건 기존 intraday wake 담당).
- **FR-7 발화 → self-wake**: predicate `fire=true`면 rate-limit 통과 시
  `TurnCoordinator.trigger(WakeEvent(kind="agent_trigger", trigger_id, why))`. wake turn 프롬프트에
  트리거 컨텍스트(thesis + why + 근거 데이터) 주입. 기존 wake와 **dedup/coalesce**.
- **FR-8 매매 게이트 불변**: agent_trigger wake turn에서 나온 BUY/SELL은 기존 supervisor
  `gate_agent_decision()` 그대로 통과 (predicate 자체는 매매 불가).
- **FR-9 lifecycle/limits**: TTL(expires) 필수·기본값/상한, 최대 활성 트리거 수, 트리거별 발화
  rate-limit, predicate 연속 에러 N회 시 자동 비활성화(disabled=true) + agent에 피드백.
- **FR-10 가시성 제약**: 트리거 메커니즘은 agent의 자기 workspace 한정. normal 모드 agent는
  여전히 `src/` 불가시(기존 F39 제약 유지). supervisor만 트리거 디렉토리/평가 로그 전체 열람.

## 5. 비기능 요구사항 (NFR)

- **NFR-보안(핵심)**: predicate 실행은 autostock `src/` 기밀(불가시)·무결성(불변)·시크릿(0)·
  네트워크 유출(0)을 **구조적으로** 보장해야 한다. 언어 레벨 샌드박스(RestrictedPython 등)에
  의존 금지 — OS/컨테이너 경계가 신뢰 경계.
- **NFR-비용/부하**: hourly floor + 최대 활성 수 + Docker spawn으로 평가 비용 통제. brokered fetch는
  TTL 캐시 재사용(기존 signals 캐시 패턴).
- **NFR-격리(가용성)**: predicate 무한루프/폭주가 daemon에 영향 0 (별 컨테이너 + timeout + pids/mem cap).
- **NFR-fail-closed**: predicate 에러/타임아웃/파싱실패 → **발화하지 않음**(fire=false 취급) + 에러 카운트.
- **NFR-관측성**: 모든 등록/평가/발화/에러를 audit 로깅(누가/언제/근거). agent는 자기 트리거 상태만,
  supervisor는 전체.
- **NFR-기존 동작 보존**: 트리거 기능 비활성(트리거 0개·기능 off)이면 daemon 동작은 기존과 동일.

## 6. 보안 컴플라이언스 매핑 (Security Baseline — Enabled, 전 단계 추적)

| Rule | 적용 | F88에서의 의미 |
|------|------|----------------|
| SECURITY-05 입력검증 | **적용** | MCP 툴 파라미터(spec/predicate) 타입·길이·스키마 검증; predicate AST 스크린(차단 import/호출). |
| SECURITY-06 최소권한 | **적용** | Docker cap-drop=ALL, non-root, 읽기전용 마운트는 predicate.py+ctx.json만; MCP 토큰 scope 최소. |
| SECURITY-07 네트워크 제한 | **적용** | predicate `--network=none`(deny-by-default 극단); MCP는 loopback 전용. |
| SECURITY-09 하드닝/오구성 | **적용** | 시크릿 제거 env, 기본 크리덴셜 0, 에러 stdout 내부정보 노출 금지, no-new-privileges. |
| SECURITY-10 공급망 | **적용** | Docker 베이스 이미지 **핀(다이제스트/태그 고정, `latest` 금지)**, 기존 lockfile 재사용. |
| SECURITY-11 시큐어 디자인 | **적용** | control/execution plane 분리(관심사 격리), defense-in-depth(AST+컨테이너+net off+fail-closed), 트리거 발화 rate-limit, **오용 시나리오**(아래 §7). |
| SECURITY-13 무결성 | **적용** | trigger spec/ctx.json **안전 역직렬화**(스키마 검증, 임의 타입 역직렬화 금지); predicate.py 변조 불가 마운트. |
| SECURITY-14 로그무결성 | **적용** | audit append-only, predicate가 자기 audit/로그 삭제·수정 불가(컨테이너가 audit에 쓰기 권한 0). |
| SECURITY-15 fail-safe | **적용** | predicate 에러→fire=false(fail closed), 컨테이너 자원정리(--rm), daemon 글로벌 핸들러로 평가 예외 격리. |
| SECURITY-01 암호화 | N/A | 새 데이터스토어 없음(workspace 파일은 기존 gitignored 런타임 상태). |
| SECURITY-02 LB 로깅 | N/A | 네트워크 LB/게이트웨이 없음(loopback MCP만). |
| SECURITY-03 앱 로깅 | 부분적용 | 기존 구조적 로깅 재사용; 시크릿/PII 미로깅 확인. |
| SECURITY-04 HTTP 헤더 | N/A | HTML 서빙 엔드포인트 없음(MCP는 로컬 툴 API). |
| SECURITY-08 앱 접근제어 | 부분적용 | MCP loopback+토큰 인증; agent 가시성 제약(FR-10)이 권한 경계. |
| SECURITY-12 인증/크리덴셜 | 부분적용 | 사용자 인증 없음; MCP 토큰은 하드코딩 금지(기존 시크릿 관리 재사용). |

> 위 "적용" 룰은 design/code/build 단계에서 verification 기준으로 재평가. 현 requirements 단계에서
> 블로킹 미준수 항목 **없음**(아키텍처가 각 룰을 충족하도록 설계됨).

## 7. 오용/남용 시나리오 (SECURITY-11)

- **소스 탈취 시도**: predicate가 `open('/app/src/...')`/import → 컨테이너에 src 미마운트 + AST 스크린 → 불가.
- **시크릿 탈취**: predicate가 `os.environ` 스캔 → env에서 시크릿 제거 → 빈손.
- **유출(exfil)**: predicate가 외부 전송 → `--network=none` → 불가.
- **자원 고갈**: 무한루프/fork bomb → timeout + pids/mem/cpu cap → 컨테이너만 죽음.
- **wake 폭주**: 트리거가 매번 fire → 트리거별 rate-limit + 최대 활성 수 + dedup → 제한.
- **에러 루프**: predicate가 계속 깨짐 → 연속 에러 N회 자동 비활성화 + agent 피드백.

## 8. PBT 대상 (PBT-01 식별 — Functional Design에서 확정, Partial: 02/03/07/08/09 enforce)

- **직렬화 round-trip(PBT-02)**: trigger spec ↔ trigger.md, ctx 객체 ↔ ctx.json.
- **불변(PBT-03)**: TTL/만료 판정(만료 트리거는 평가 제외), rate-limit 카운터 단조성, verdict 파싱이
  허용 범위(fire∈{true,false}) 강제.
- **생성기 품질/재현성(PBT-07/08)**: 도메인 생성기(트리거 spec, cadence, 데이터소스 선언), seed 로깅.
- **프레임워크(PBT-09)**: Hypothesis (기존 파이썬 스택 정합).

## 9. 가정 / 의존성

- 기존 docker-verify 하니스(`docker-compose.verify.yml`, `scripts/worktree-setup.sh --docker-verify`)의
  컨테이너 실행 패턴 재사용 가능 (`[[worktree-live-verification]]` 메모리 참조).
- daemon이 장기 실행 프로세스라 HTTP MCP 엔드포인트 호스팅 가능; agent `claude -p` 세션은
  `.mcp.json`/allowed-tools로 연결(`src/agent/session.py`).
- signals collector가 brokered fetch 소스 제공(`src/signals/collector.py`).
- 호스트에 Docker 데몬 가용(프로덕션 daemon 환경 기준 — design에서 가용성·권한 확인 필요).

## 10. 확정된 결정 (Requirements UAQ)

- Security Baseline extension: **Enabled** (blocking).
- Property-Based Testing extension: **Partial** (PBT-02/03/07/08/09 enforce, Hypothesis).
- R1 데이터 카탈로그: signals + webfetch(httpx allowlist); **websearch는 후속(critic#2 정정)**.
- R4 cadence floor: **hourly**.

## 11. design 단계로 넘길 미해결 상세

- predicate `ctx` 정확 스키마 & `should_fire` 시그니처 계약.
- AST 스크린 차단 목록(import/호출) 구체화.
- lifecycle 수치: TTL 기본·상한, 최대 활성 트리거 수, rate-limit 임계, 연속에러 임계.
- wake 프롬프트 주입 포맷 & 기존 `WakeDetector` 이벤트와 dedup/coalesce 규칙.
- Docker 베이스 이미지 선정·핀, WebFetch 도메인 allowlist 관리(설정 위치).
- MCP 토큰 발급/보관 & `.mcp.json` 배선.
