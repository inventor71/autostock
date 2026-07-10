# F96 Application Design (경량)

**Status**: DRAFT (승인 대기) · 근거 파일 라인은 base 4f3fcbf 기준.

기존 컴포넌트 경계 내부 확장이라 신규 서비스/컴포넌트 없음. 계약(시그니처·설정·출력 shape)만 고정한다.

## U1 — Execution drift guard (RiskManager 확장)

> **구현 중 재결정 (옵션 B, 사용자 승인)**: anchor = `entry`(=d.limit) 있으면 그것, 없으면
> **`ref_price`**(결정시각 가격, orchestrator가 turn 직후 market 진입에 스탬프). 최초 "entry-only
> anchor"는 near-no-op이었음(아래 배치 근거의 buy-the-dip가 entry-present 상방을 이미 캡). 배선:
> `Decision.ref_price`(additive) · `AgentTradingLoop(price_provider)` · `main.py get_latest_price` ·
> `executor._to_signal` metadata · `RiskManager`가 `anchor = entry or ref_price`로 가드.

### 배치 근거
진입 주문의 MARKET/LIMIT 결정은 이미 `RiskManager._build_bracket_buy`(`manager.py:280`)와
`_build_bracket_short`(`manager.py:507`)에 있고, 여기서 `entry`(LLM anchor)와 실행시점 `price`를
모두 본다. executor는 `price`(`executor.py:266`)와 `key_levels.entry`(`executor.py:353`)를 이미
넘겨준다 → **executor 변경 없음**, RiskManager 국소 확장으로 근본 지점을 고친다.

### 계약 변경
1. **`RiskManager.__init__`** — 신규 파라미터
   `entry_drift_guard_atr: float = 0.5` (self에 저장). `0.0` → 가드 비활성(off 스위치).
2. **`_build_bracket_buy`** — 기존 `use_limit = entry is not None and entry < price` 를 3분기로 확장:
   ```
   slip = (self.entry_drift_guard_atr * atr) if (atr is not None and self.entry_drift_guard_atr > 0) else None
   if entry is not None and entry < price:          # 기존 buy-the-dip (불변)
       use_limit, limit_px = True, entry
   elif slip is not None and entry is not None and price > entry + slip:  # 드리프트 가드
       use_limit, limit_px, guarded = True, entry + slip, True
   else:                                            # 정상 범위 → 기존 MARKET
       use_limit, limit_px = False, None
   ```
   Order의 `limit_price = round(limit_px, 2) if use_limit else None`. (기존엔 `entry_ref`를 그대로
   썼으나, 가드 케이스는 `entry+slip`이 되어야 하므로 별도 `limit_px` 도입.)
3. **`_build_bracket_short`** — 대칭: `price < entry - slip` 이면 `use_limit, limit_px = True, entry - slip`.
   기존 sell-the-rip(`entry > price`)은 불변.
4. **로깅**: 가드 발동 시 기존 "Risk approved: BRACKET …" 로그에 `guard=drift-capped(entry+{slip})` 접미.
   Order.order_type이 LIMIT로 바뀌므로 `execution_outcomes.jsonl` detail에서 이미 구분됨(추가 필드 불요).

### 설정 배선
- `config/settings.yaml` `risk:` 블록에 `entry_drift_guard_atr: 0.5` 추가(주석 포함).
- `settings.risk` pydantic 모델(RiskConfig)에 `entry_drift_guard_atr: float = 0.5` 필드 추가.
- `main.py:_build_risk_manager`(단일 chokepoint, `:430`)의 kwargs에 `entry_drift_guard_atr=r.entry_drift_guard_atr` 추가.
- **aggressiveness 연동 없음(v1)**: `aggressiveness.py`의 risk-override allowlist에 추가하지 않는다
  (posture와 독립적인 실행-품질 안전장치로 고정). 후속에서 필요 시 편입 가능.

### 불변식 / 엣지
- `entry is None`(무앵커) 또는 `atr is None` → 가드 미적용, 기존 동작 그대로(fail-honest).
- `entry + slip >= price` (정상) → 바이트-동일 회귀 없음.
- `use_bracket_orders=False` 경로(_simple_buy)는 anchor를 읽지 않으므로 범위 밖(진입 대부분 stop 동반→bracket).
- limit_px가 stop/target 기하와 모순되지 않음: entry 근처(≤0.5 ATR)라 stop(≥아래) / target(위) 정합 유지.

## U2 — News freshness surface (market.news + 프롬프트)

### 계약 변경
1. **`src/agent/tools/market.py::news`** (`:225`) — 각 news 항목 dict에 2개 필드 추가:
   - `age_hours: float | None` — `(now - published_at)` 시간. tz-safe(둘 다 aware/naive 정합).
     `published_at` 없거나 파싱 불가 → `None`.
   - `priced_in_risk: "fresh" | "elevated" | None` — `age_hours`가 임계(기본 24.0h) 초과 → `"elevated"`,
     이하 → `"fresh"`, `age_hours is None` → `None`.
   - 순수·결정론: 비교 기준시각 `now`를 주입 가능한 인자(`_now: datetime | None = None`, 기본 현재)로
     받아 단위테스트가 클럭 고정 가능. 임계는 모듈 상수 `_PRICED_IN_HOURS = 24.0`.
2. **프롬프트/레슨** (`src/agent/prompts.py`) — 진입/held 뉴스 점검 가이드에 규칙 1개 추가(간결):
   "뉴스의 `priced_in_risk`가 elevated(촉매 24h 초과)이고 진입가가 20d high 근처면 priced-in 위험을
   가중하라 — 신선한 촉매만으로 고점 추격 진입하지 말 것."
3. **aggressiveness 정합** (`src/agent/aggressiveness.py:84`) — same-week catalyst 선호 문구에
   "단, 이미 급등해 priced-in된 촉매는 예외" 취지 한 구절 보강(선호 자체는 유지).

### 불변식 / 엣지
- 필드는 additive — 기존 news 소비자(있다면) 영향 없음.
- tz 혼재(`published_at` aware, now naive) 시 `_now_like` 패턴처럼 정합 맞춰 비교(예외로 age=None 강등).

## 테스트 계약 (예제 기반, PBT 미적용)
- U1: (a) price가 entry+0.5ATR 초과 → LIMIT@entry+slip, (b) 정상범위 → MARKET 불변,
  (c) buy-the-dip 불변, (d) atr=None/entry=None → 미적용, (e) short 대칭 3케이스.
- U2: (a) age<24h→fresh, (b) >24h→elevated, (c) published_at=None→age/risk=None,
  (d) tz-aware/naive 혼재 정합, (e) 주입 클럭 결정론.

## Merge Risk
- 공유 파일: `market.py`(F95 warm-cache가 quote 계열 손댈 수 있음 — news()는 별 함수라 충돌 가능성 낮음),
  `prompts.py`, `main.py`, `settings.yaml`, `manager.py`. 모두 additive/국소.
