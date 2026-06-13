# evals/ — F74 Prompt Eval & Regression Harness

실전 교훈(lesson)을 동결한 합성 시나리오로 agent turn의 **행동**(decisions.jsonl 산출물)을
자동 채점하는 회귀 게이트. promptfoo = matrix runner + diff UI + LLM judge 레이어,
파이프라인 코어 = `src/evals/`.

## 실행

```bash
cd evals
PATH=~/.bun/bin:$PATH bun install          # promptfoo 고정 버전 (최초 1회)
bun run eval                               # Tier-1: 구독 claude CLI만, API 토큰 0
bun run eval:tier2                         # Tier-2: LLM judge — ANTHROPIC_API_KEY 종량 과금
bun run view                               # 웹 뷰어 (버전 간 side-by-side diff)
```

- **Tier-1** (`promptfooconfig.yaml`): 하드 assert는 추출 무결성/프로바이더 에러만.
  행동 매칭·no-churn·executor replay 결과는 output JSON으로 리포트(비차단 — NFR-3).
- **Tier-2** (`promptfooconfig.tier2.yaml`): `rubrics/common.md` 루브릭으로 judge 채점.
  명시 실행 전용 — CI/cron 금지.
- 케이스당 실제 agent turn 1회(수 분). `maxConcurrency: 1`이 구독 rate limit 보호.

## 시나리오

`scenarios/{intraday,wake,eod}/<id>.json` — 스키마는 `src/evals/scenario.py`.
신규 작성 경로 두 가지:

1. **추출기**: `python -m src.evals.extract --date YYYY-MM-DD --symbol SYM --turn-type intraday`
   → 재구성 가능한 슬라이스(보유/계좌/가격)는 자동, 뉴스/펀더멘털은 `TODO_MANUAL` 마커
   (1차 보강 소스: `workspace/positions/<SYM>.md`의 Call-vs-Outcome 서술).
2. **record 모드**: 라이브 데몬 환경에 `AUTOSTOCK_TOOLS_RECORD_DIR`를 설정하면 turn의
   실제 tool 응답이 fixture 포맷으로 캡처됨 — 이후 사건은 그대로 시나리오가 된다.

테스트 매트릭스는 `tests.yaml` (시나리오 × guidance 버전). guidance 버전 비교는
`guidance_file` var로 history.json 페이로드를 핀 — intraday/wake turn에만 적용
(EOD는 프로덕션도 guidance 미주입).

## 격리 보장

- 시나리오 turn은 임시 sandbox workspace에서 `one_shot` 세션으로 실행 — 운영
  `workspace/`·세션 store·브로커를 건드리지 않는다.
- market-data tool 15종은 fixture 인터셉트로만 응답(`src/agent/tools/fixtures.py`),
  미정의 키는 명시 `fixture_missing` 에러 (실데이터 폴백 불가).
- 가드레일 판정은 실제 `DecisionExecutor`+SimulatedBroker replay — 룰 재구현 없음.
