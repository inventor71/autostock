# Unit A (daemon-timeline) — Business Logic Model

> monitor.json/turns.jsonl 확장의 함수/흐름. 모든 변경은 읽기 전용 집계 + 직렬화.

## BLM-1 — et_date 계산 (`turn_log.py`)

```
def compute_et_date(ts_aware: datetime) -> str:
    # ts를 America/New_York로 변환 후 date. 정규장 기준 거래일.
    et = ts_aware.astimezone(ZoneInfo("America/New_York"))
    return et.date().isoformat()
```

- `record_turn`: `ts`를 **tz-aware**(`datetime.now().astimezone()`)로 저장 + `et_date` 필드 추가.
- After-hours가 ET 자정을 넘지 않으므로(20:00 ET < 24:00) ET date = 거래일로 단순 일치.
  (pre-market 4:00 ET도 같은 ET date. 즉 ET 기준으론 자정 넘김 없음 — KST 표시만 넘김.)
- 따라서 et_date = `astimezone(ET).date()`로 충분. 추가 세션 경계 보정 불필요.

## BLM-2 — Market 규칙 publish (`runtime.py` + `modes/agent.py`)

- `modes/agent.py`가 `config/settings.yaml`의 trading 설정(또는 기본값)에서 마켓 wall-clock 시각을
  읽어 `SteeringRuntime`에 주입(생성자 or setter).
- `publish_monitor`가 payload에 `market` 블록 + `session_et_date` 추가.
- `session_et_date` 계산:
  ```
  now_et = datetime.now(ZoneInfo("America/New_York"))
  if is_within_regular_or_extended(now_et):  # pre_open <= time < after_close, 평일
      session = now_et.date()
  else:
      session = next_weekday(now_et.date())  # 마감 후/주말 → 다음 평일 (Q8=A: 공휴일은 빈 바 허용)
  ```
  - `is_market_open`(broker)은 정규장만 True. 확장 세션 판정은 wall-clock 비교로 보완.
  - broker 호출 실패/오프라인 시 fail-safe: now_et.date() 사용(SECURITY-15).

## BLM-3 — turns 직렬화 변경 (`_turns_summary`)

```
for r in rows (et_date 필터 없이 최근 _MONITOR_TURNS):
    recent.append({
        ..기존 필드..,
        "ts": <full ISO, naive면 로컬 tz 부여>,   # _hhmm 절단 제거
        "et_date": r.get("et_date") or compute_et_date_from_naive(r["ts"]),
    })
```

- monitor.json `turns.recent`는 현재 세션(`session_et_date`) 턴 위주지만, 필터는 **TS가** 수행
  (daemon은 최근 N개 + et_date 동봉). 과거는 TS가 turns.jsonl 직접 읽음.
- `today_count`/`today_cost`는 `session_et_date` 기준으로 재정의(KST today → ET session).

## BLM-4 — interventions 수집 (`runtime.py` 신규 `_interventions_tail`)

```
def _interventions_tail(path: Path) -> list[dict]:
    recs = read_jsonl(path / "human_directives.jsonl")   # InterventionRecord
    out = []
    for r in recs[-_MONITOR_INTERVENTIONS:]:
        verb = r.get("command", "")
        if verb not in _TRADE_VERBS:        # Q5=A 필터
            continue
        ts = parse_aware(r["ts"])
        out.append({
            "ts": ts.isoformat(), "et_date": compute_et_date(ts),
            "verb": verb, "symbol": extract_symbol(r),
            "outcome": r.get("outcome", ""), "detail": r.get("detail", ""),
        })
    return out
```

- `_TRADE_VERBS = {buy, sell, flatten, flatten_all, place_order, cancel, cancel_order,
  cancel_all, close_position, close_all}`.
- `extract_symbol`: verb별 args에서 symbol 추출(buy/sell→args["symbol"]; place_order→args["symbol"];
  cancel_order→없으면 order_id; flatten_all/close_all→None).
- SECURITY-03: InterventionRecord은 토큰 미포함(safe_view). detail/args에 시크릿 없음 재확인.

## BLM-5 — publish_monitor 통합

```
payload = {
  "ts": ..., "current_turn": ..., "workspace_root": ...,
  "market": self._market_rule,                       # BLM-2
  "session_et_date": self._session_et_date(),        # BLM-2
  "turns": _turns_summary(...),                       # BLM-3 (et_date+full ISO)
  "decisions": _decisions_tail(...),                  # 기존 + ts full ISO (선택)
  "interventions": _interventions_tail(...),          # BLM-4
  "log": _log_tail(...),
}
atomic_write_text(monitor.json, ...)
```

## 불변식
- 거래/리스크 경로 무변경 — advisor-only gate, decisions.jsonl→RiskManager→Broker 그대로.
- monitor.json 직렬화 실패는 catch & continue(기존 패턴) — daemon 루프 안 죽음.
- 0 new runtime dep: `zoneinfo`는 stdlib(py3.9+).
