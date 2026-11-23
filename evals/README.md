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

`scenarios/{research,intraday,wake,eod}/<id>.json` — 스키마는 `src/evals/scenario.py`.
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

- 시나리오 turn은 임시 sandbox workspace에서 실행 — 운영
  `workspace/`·세션 store·브로커를 건드리지 않는다.
  intraday/wake/eod는 `one_shot`; research는 같은 실행의 검토 라운드 사이에서만 세션을 재개한다.
- market-data tool은 fixture 인터셉트로만 응답(`src/agent/tools/fixtures.py`),
  미정의 키는 명시 `fixture_missing` 에러 (실데이터 폴백 불가).
- 가드레일 판정은 실제 `DecisionExecutor`+SimulatedBroker replay — 룰 재구현 없음.

## Research-mode comparison

From the repository root, using the logged-in Claude CLI:

```bash
python -m src.evals.compare_research --model opus --repeats 3
python -m src.evals.compare_research --report research-comparisons/<experiment>
```

For a paired model, effort, and prompt comparison:

```bash
python -m src.evals.compare_research --profiles evals/research_profiles.json \
  --select opus-legacy-high opus-current-high fable-current-high fable-current-medium \
  --repeats 3 --timeout 600
# Requires OPENAI_API_KEY, independently of Codex login:
python -m src.evals.compare_research --profiles evals/research_profiles.json \
  --select astra-current-high astra-current-max --repeats 3
```

Profiles specify `provider`, `model`, `effort`, and `prompt_ref`. The bundled
`baseline:pre-frontier` preserves the old turn prompts and manual from commit
`76ae872cbe3d7b43df2d98f5c01fc865730c6fa0`; all profiles share current execution,
guidance, tools and risk code. This isolates the prompt/manual change, not the entire
old repository. Git commit references are also supported for trusted local code.
Each experiment captures exact prompt contents/hashes and effective scenario risk
settings. Results remain grouped by profile AND mode, never pooled across models.
Missing API credentials create explicit failed runs, not simulated successes.
Claude Fable 5.2 requires Claude Code 2.1.321 or later. Claude CLI effort is set
explicitly in the child environment as well as the command, so saved session or
operator shell settings cannot silently change an experiment's effort.

The first command makes real model calls; the second only rebuilds reports.
`--modes single sequential parallel`, `--n-agents 3`, `--seed 0`, `--timeout 240`,
and `--scenarios <file-or-directory>` control the experiment. Sequential uses one
session across research/review/synthesis. Parallel uses separate analysts and a manager.
Both multi modes use three calls at the default agent count. Mode order is shuffled
within each scenario/repeat; market evidence is identical and external web is unavailable.

Each experiment is saved incrementally under **gitignored `research-comparisons/`**:

`research-comparisons/README.md` indexes all experiments, including partial/error runs.

- `summary.md` / `summary.csv`: behavior/schema passes, execution-gate issues, errors,
  permission denials, elapsed time, all-call token/cache usage, and CLI-reported cost.
- `runs/*.json`: each decision and thesis change, gate result, every call's prompt and
  response, and resolved model IDs. Aliases such as `opus` can change over time.
- `manifest.json`, `source.zip`, `source.diff`, `scenarios/`: parameters and captured
  source/evidence for reproducibility, including local uncommitted changes.

Failures stay in the denominator; unavailable usage is null, never zero. With Claude
CLI 2.1.277+, resumed turns report cumulative session cost: the comparison counts each
session's last total once, and sums per-turn usage. See the [cost accounting contract](https://code.claude.com/docs/en/agent-sdk/cost-tracking).
CLI cost is reported telemetry, not a subscription invoice. Inspect paired decisions and gate results
alongside costs; a matching action alone does not establish sound reasoning. The initial
cases cover no independent edge, a supported entry, and confirmed thesis invalidation.
They are synthetic behavior probes, not return backtests, and are too few to establish
whether multi-agent research improves live risk-adjusted returns. Keep defaults until
broader repeated cases and later unseen market periods support a change.

The new operating manual seeds new workspaces; existing customized workspace manuals
and prompt histories are preserved. The current decision standard is also injected by
the orchestrator on every research/intraday/wake turn. Legacy strategy prompt v2 is
selected for an empty history; existing version histories keep their selected policy.

## Measuring returns separately from behavior

Unit tests verify accounting and execution rules; better trading returns need
independent market outcomes. Freeze the candidate profiles and evaluation periods
before measuring them. Use development periods for changes, a later untouched
holdout for selection, and forward paper observations for confirmation. Repeatedly
choosing the best backtest creates selection bias; see the authors' paper on
[backtest overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

The offline return scorer evaluates saved decisions against **separate hidden future
bars**. It makes no model calls and never supplies those bars to a research workspace:

```bash
python -m src.evals.returns \
  --experiment research-comparisons/<experiment> \
  --outcomes research-comparisons/private-outcomes.json \
  --baseline opus-legacy-high --baseline-mode single
```

The outcome file is an array matching [outcome-path.schema.json](outcome-path.schema.json).
Each entry names a `scenario_id`, a timezone-aware `as_of` matching the scenario,
`kind` (`synthetic`, `historical`, or `forward`), provenance, per-symbol future OHLC
bars with `open_at`/`close_at`, and a benchmark on the exact same intervals.
Every held/universe symbol needs cutoff prices and complete future bars; missing or
delisted losers cannot silently disappear. Zero-valued terminal bars are supported.
Cash comes from the frozen account fixture. Use audited information available at
the cutoff, including publication times and the universe that existed then.

`cost_bps_per_side` combines commissions, half-spread and slippage as a cash charge
(default 10 basis points each side, a stress assumption to replace with measured
costs). `borrow_apr` and `cash_apr` are explicit. Re-score at higher costs without
spending more model calls. Entry execution starts at the next bar's open; an
unfilled limit earns no imaginary return. Gapped stops fill at the adverse open;
when a bar touches both stop and target, the stop wins. An entry expiring inside
a bar may fill only at the observed open. Closing costs are charged to remaining
positions at the end. Existing protective orders are shared by the candidate and
hold-book baseline. Partial/multiple protection levels are rejected rather than
approximated. Short borrowing is charged through a whole bar when its exit time
is unknown. Splits and dividends require a separate corporate-action-aware replay;
declare them in `corporate_actions`, which this scorer rejects explicitly.
For a limit entry filled inside a bar, a target touch is accepted only if the
close also reaches it: the high/low may have occurred before the entry. Intrabar
short entries incur a full bar of borrowing costs. Adjacent bar intervals are valid.

`returns.json` / `returns.md` report net episode returns, drawdown, turnover, costs,
fills, risk-gate outcomes, cash/hold-book/benchmark comparisons, and paired
differences against the chosen profile/mode. They retain outcome and replay-code
hashes. Model failures remain unscored and suppress comparative confidence intervals.
Repetitions are averaged within each case; they do not increase the market sample
size. Synthetic, overlapping, or fewer than 20 independent real episodes get no
confidence interval. Larger samples receive a paired moving-block bootstrap interval;
20 is only a reporting floor, not a significance guarantee. Multiple comparisons
still need a fresh holdout. No result automatically changes production defaults.

Forward results additionally require an intact decision hash and a recorded model
completion time before the first future bar. Historical results can still be
contaminated by model training knowledge. This is a **single-decision episode
evaluation**, not a continuous portfolio backtest: it excludes later discretionary
rebalancing, queue position, partial fills and market impact. Drawdown is measured
at bar closes, so intrabar losses can be larger. Baseline excess is not a
risk-adjusted alpha estimate. For a complete strategy assessment, also collect
continuous forward paper equity and benchmark equity through the existing
`src.benchmark` pipeline, then compare net returns, drawdown and Sharpe over a
common period. Do not infer annualized Sharpe from a few synthetic episodes.

The historical extractor bounds returned bars at the cutoff and leaves current
theses/lessons out because they may contain later outcomes. Extracted skeletons
retain `TODO_MANUAL` markers and cannot run until reviewed. Reconstruct missing
news/fundamentals from contemporaneous records; an end-of-day skeleton is not an
intraday snapshot.

Model parameter references: [Claude model and effort configuration](https://code.claude.com/docs/en/model-config),
[OpenAI reasoning](https://developers.openai.com/api/docs/guides/reasoning), and
[Responses function calling](https://developers.openai.com/api/docs/guides/function-calling).
