# Unit A (daemon-timeline) — Business Rules

## BR-1 (et_date 권위)
turn/intervention의 거래일 = `ts.astimezone(America/New_York).date()`. KST 로컬 날짜가 아님.
ET 기준 거래일은 자정을 넘지 않으므로(pre 04:00 ~ after 20:00 ET) 단순 date 변환으로 충분.

## BR-2 (시간은 full ISO로 전달)
monitor.json의 모든 ts는 **tz-aware full ISO**. `_hhmm` 절단(F22)은 제거. HH:MM·로컬 변환은 TS 책임.

## BR-3 (구버전 레코드 호환)
`et_date` 없는 기존 turns.jsonl 레코드: naive `ts`를 daemon 로컬 tz로 해석 후 ET 변환해
best-effort et_date 계산. 파싱 실패 시 해당 레코드 스킵(SECURITY-15, fail-safe).

## BR-4 (market 규칙 출처)
`market` 블록 값은 `config/settings.yaml` trading 설정 우선, 없으면 US equity 기본
(pre 04:00 / open 09:30 / close 16:00 / after 20:00, tz America/New_York). DST는 TS의 IANA tz 변환에 위임.

## BR-5 (intervention 거래 필터)
`interventions[]`에는 `command ∈ _TRADE_VERBS`만 포함(Q5=A). 그 외(pause/note/approve 등) 제외.

## BR-6 (SECURITY-03)
직렬화되는 intervention/turn 어디에도 operator token·시크릿 없음. InterventionRecord은 이미
safe_view로 token 미포함. log_tail은 기존 `_SECRET_KV`/`_SECRET_BLOB` 레닥션 유지.

## BR-7 (fail-safe 직렬화)
monitor.json publish는 try/except로 감싸 실패해도 daemon 루프 지속(기존 동작 보존). 부분 실패
(예: human_directives.jsonl 없음)는 빈 리스트로 degrade.

## BR-8 (session_et_date)
현재 ET 시각이 확장 세션(pre_open~after_close, 평일) 내면 오늘 ET date, 아니면 다음 평일.
broker 마켓 클락 조회 실패 시 now_et.date()로 fail-safe.

## BR-9 (불변식 — 거래 경로 무영향)
Unit A는 monitor.json/turns.jsonl 기록·직렬화만 변경. RiskManager→Broker gate, decisions.jsonl,
advisor-only 모델 일절 무변경.

## BR-10 (0 new dependency)
`zoneinfo`(stdlib py3.9+)만 사용. 신규 런타임 의존성 없음.
