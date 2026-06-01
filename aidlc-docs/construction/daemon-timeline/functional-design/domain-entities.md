# Unit A (daemon-timeline) — Domain Entities & monitor.json 계약

> F25 Unit A Functional Design. daemon이 monitor.json/turns.jsonl을 F25 요구에 맞게 확장.
> 거래 로직 무영향 — 읽기 전용 집계 + 직렬화만.

## 핵심 문제: ET date 세션 그룹핑 (자정 넘김)

`turn_log.record_turn`은 `"date": datetime.now().date()` = **daemon 로컬(KST) 날짜**를 저장.
미장 정규장은 KST 자정을 넘으므로(22:30 KST ~ 05:00 KST+1, EDT 기준) **같은 ET 거래일**의 턴이
서로 다른 KST date로 쪼개진다. 타임라인 "한 세션" = **ET 거래일(et_date)** 기준이어야 함.

**해결**: 각 turn/intervention 레코드에 `et_date`(ET 거래일, `America/New_York` 기준 date)를 추가.
TS는 `et_date`로 세션을 묶고, `ts`(tz-aware ISO)를 로컬(KST)로 변환해 표시.

## E1 — MarketSessionRule (monitor.json `market` 블록)

거래 세션의 **규칙**을 publish (특정 날짜 인스턴스가 아니라 규칙). TS가 임의 et_date에
대해 IANA tz(`Intl`/`Temporal`)로 경계 instant를 계산 → 로컬 변환.

```json
"market": {
  "tz": "America/New_York",
  "pre_open":      "04:00",
  "regular_open":  "09:30",
  "regular_close": "16:00",
  "after_close":   "20:00"
}
```

- 값은 `config/settings.yaml`의 trading 설정에서 읽음(없으면 US equity 기본값).
- **DST는 TS가 IANA tz로 처리** — daemon은 wall-clock ET 시각(고정)만 전달. 표준 라이브러리
  (`Intl.DateTimeFormat` timeZone 옵션)가 날짜별 올바른 오프셋을 계산하므로 손으로 짠 DST 산술 없음.
- daemon이 시간대 산술을 하는 유일한 곳 = `et_date` 계산(아래) + 현재 세션 판정.

## E2 — TurnRecord 확장 (turns.jsonl + monitor.json `turns.recent[]`)

기존 F22 필드(id/type/ts/cost_usd/num_decisions/duration_ms/summary/health) 유지 + 추가:

| 필드 | 의미 | 비고 |
|------|------|------|
| `et_date` | ET 거래일 (`YYYY-MM-DD`) | 세션 그룹핑 키. record_turn이 기록 시 계산 |
| `ts` | **tz-aware ISO** (오프셋 포함) | 기존 naive local → tz-aware로 승격. TS가 로컬 변환 |

- `_hhmm` 절단 제거: monitor.json에 `ts`를 **full ISO**로 전달(TS가 로컬 HH:MM 변환).
  (F22는 `_hhmm`로 HH:MM만 보냈으나 tz/날짜 손실 → F25는 full ISO 필요.)
- 구버전 레코드(naive ts, et_date 없음): daemon 로컬 tz로 해석해 et_date 후행 계산(best-effort).

## E3 — InterventionMarker (monitor.json `interventions[]` + human_directives.jsonl)

`human_directives.jsonl`의 `InterventionRecord`를 읽어 **거래성 명령만** 필터(Q5=A).

```json
"interventions": [
  { "ts": "<tz-aware ISO>", "et_date": "YYYY-MM-DD",
    "verb": "buy", "symbol": "AAPL", "outcome": "executed", "detail": "10sh @ market" }
]
```

- **거래 verb 집합** (FR-3, Q5=A): `{buy, sell, flatten, flatten_all, place_order,
  cancel, cancel_order, cancel_all, close_position, close_all}`.
  pause/resume/halt/kill/note/directive/approve/reject/unlock 은 **제외**.
- `InterventionRecord`은 이미 `ts/kind/command/args/outcome/detail` 보유 → **새 기록 불필요, 읽기만**.
  `symbol`은 `args`에서 추출(verb별 키: buy/sell=args["symbol"], cancel_order=order_id 등).
- SECURITY-03: token은 InterventionRecord에 애초에 없음(`safe_view`로 strip됨) — 직렬화 시 재확인.

## monitor.json 최종 스키마 (F25)

```json
{
  "ts": "<publish time ISO>",
  "current_turn": { "id": "...", "type": "...", "started_at": "<ISO>" },
  "workspace_root": "...",
  "market": { "tz": "...", "pre_open": "...", "regular_open": "...", "regular_close": "...", "after_close": "..." },
  "session_et_date": "YYYY-MM-DD",         // 현재(또는 다가올) 세션의 ET date
  "turns":  { "today_count": N, "today_cost_usd": X, "recent": [TurnRecord...] },
  "decisions": [ ... ],
  "interventions": [ InterventionMarker... ],
  "log": [ ... ]
}
```

## 과거 날짜 조회 경로 (FD 결정)

**TS 직접 파일 읽기** (Q4=C 무제한 + F22 패턴 재사용). monitor.json은 **현재/다가올 세션**의
live 뷰만 담는다. 과거 날짜 네비게이션 시 TS가 `turns.jsonl` + `human_directives.jsonl`을 직접 읽어
`et_date`로 필터 (F22 `readThesis`/`readPositions`가 이미 워크스페이스 파일 직접 읽는 패턴).

- 장점: 요청/응답 채널 불필요, 무제한 히스토리 자연 지원.
- daemon은 `et_date`만 정확히 기록하면 됨(나머지는 TS 필터).
- `market` 규칙은 monitor.json에 항상 있으므로 과거 날짜도 TS가 경계 계산 가능.

## 다가올 세션 (장 마감 시)

`session_et_date` = 현재 진행 세션의 ET date, 장 마감/주말이면 **다음 거래 세션의 ET date**.
- daemon이 `is_market_open` + 현재 ET 시각으로 판정: 정규장 중이면 오늘 ET date,
  마감 후면 다음 평일 ET date(주말 스킵; 공휴일은 Q8=A로 빈 바 허용 → 단순 평일 계산).
