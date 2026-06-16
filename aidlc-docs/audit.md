# AI-DLC Audit Log

## F14 merged
**2026-05-31** — 데몬 wedge 자가복구 + WakeDetector 마켓데이터 fetch 경직성 수정 (commit d899f83, 12 files: +561/−25). A) Alpaca HTTP 타임아웃(connect 3s/read 5s, 3개 클라이언트), B) BarCache.peek(캐시전용)+prefetch 5s job·detect-first 2단계 latch로 WakeDetector 스케줄러-스레드 네트워크 0, C) 런처 self-heal(handleActiveWedge: active+not-fresh 시 3분 patience→restart 1회+fail-closed). pytest 425/0, launcher 35/0, bun typecheck exit 0, paper live-verify 통과.


## F20 Merge — 2026-05-31
16 Alpaca MCP stock-only read tools added to operator console (TS in-process, live Alpaca API). 
24 unit tests, typecheck clean, 92 total 0 regressions. Submodule: perm keys + env vars on feat/F20→main.

**F21 merged 2026-05-31** — Synchronous MCP arg validation (3-layer: L1 zod `.refine()` cross-field → L2 degenerate placeholder check → L3 daemon defense-in-depth).  Alpaca MCP pattern.  10 files (387+/57-), 420 Python + 47 TS tests green.  See `aidlc-docs/tracks/F21/`.

**F24 merged 2026-06-01** — Decision quality metrics: `src/agent/quality/` (direction hit rate, MAE/MFE, stop/target quality, confidence calibration, realized R:R, benchmark excess, exit timing), CLI + auto-save JSON at EOD, `execution_log.jsonl` decision→fill linkage (+30 tests, 461 total, 0 new deps).  See `aidlc-docs/tracks/F24/`.


## [F10 MERGED] 2026-05-31 — Containerized verification harness (zero prod impact)
**Timestamp**: 2026-05-31T01:50:00Z
F10 merged to main (merge commit `8ff59c0`, parent `a0b882d`). Reproducible verify container (`Dockerfile.verify` python3.12+bun+claude CLI+CPU-torch; CODE bind-mounted) driven by `scripts/verify.sh` modes typecheck|unit|smoke via `docker-compose.verify.yml`. Isolation is structural: `AUTOSTOCK_ENV_FILE=/app/.env.test` → a TEST paper account only; prod `.env`/account/systemd daemon never referenced. Real LLM = host `~/.claude` mounted read-only (no stub). Verified: typecheck 19/19, unit 376 (offline), smoke real-claude 2.1.158 + read-only Alpaca on TEST account `PA3F5JU0T43K` (no orders). `worktree-setup.sh --docker-verify` wires it into the worktree workflow; `concurrent-tracks.md` documents it. No submodule source change (no gitlink). Full per-track record: `aidlc-docs/tracks/F10/`. Next iteration TODO: full agent/command-surface smoke (AAPL-limit-order class).


## [F11 MERGED] 2026-05-31 — Verify-harness ergonomics (clean worktree + reuse main .env.test)
**Timestamp**: 2026-05-31T02:15:00Z
F11 merged to main (merge commit `24dc367`, follow-up to F10). Two fixes: (1) the verify container runs as root and was writing pytest/hypothesis/bytecode caches INTO the bind-mounted worktree as `root:root`, so the host couldn't `git worktree remove` without sudo — redirected every writer off `/app` (`PYTHONDONTWRITEBYTECODE=1`, `HYPOTHESIS_STORAGE_DIRECTORY=/tmp/hypothesis`, pytest `-p no:cacheprovider`); verified unit 376 passed with 0 stray cache dirs and the test worktree then removed cleanly with no sudo. (2) `worktree-setup.sh --docker-verify` now COPIES the canonical `${MAIN_ROOT}/.env.test` (TEST paper creds) into new worktrees automatically (copy, not symlink — a symlink dangles inside the container mount), falling back to the example. Per-track record: `aidlc-docs/tracks/F11/`.


## [F12 MERGED] 2026-05-31 — Verify-harness hardening (critic review)
**Timestamp**: 2026-05-31T02:45:00Z
F12 merged to main (merge commit `715723e`, follow-up to F10/F11). Driven by an adversarial `critic` subagent review of the verification setup, which found the "zero prod impact" guarantee rested on conventions. Fixes: (1) **HIGH** — `verify smoke` only checked `paper=True` (a constant), never proving the keys are the intended TEST account; now asserts live `account_number == EXPECTED_ACCOUNT_NUMBER` (new key in `.env.test`, pinned to `PA3F5JU0T43K`) and FAILS CLOSED on mismatch (negative-tested: exit 1). (2) **HIGH** — added `verify.sh` preflight failing closed if `AUTOSTOCK_ENV_FILE` is unset/missing (config.py would else fall back to prod `/app/.env`) or if a prod `/app/.env` is bind-mounted (compose run from main root, not a worktree); negative-tested. (3) **MEDIUM** — dropped redundant compose `env_file: [.env.test]` that made OS env authoritative over the dotenv (pydantic precedence footgun); app reads creds only via Settings. (4) **MEDIUM** — F11 cleanup only covered python writers; the trap now also sweeps bun/turbo/tsgo root-owned output (`.turbo`, nested `packages/*/node_modules`, `*.tsbuildinfo`) → typecheck leaves 0 root-owned files, worktree `rm -rf`'d with no sudo. Verified: typecheck/unit 376/smoke-match all green; 2 negatives fail closed. (Aside: worktrees with an inited submodule can't `git worktree remove` — use `rm -rf` + `git worktree prune`, now sudo-free.) Per-track record: `aidlc-docs/tracks/F12/`.


## [F15 MERGED] 2026-05-31 — docker-verify `attach` mode (full daemon+TUI runtime)
**Timestamp**: 2026-05-31T03:58:00Z
F15 merged to main (merge commit `98090fa`). Adds a fourth docker-verify mode beside typecheck/unit/smoke: **`attach`** runs the **full runtime** — daemon (`main.py --mode agent --steering`) in the background + the operator console TUI in the foreground — both on the **TEST paper account**, so a human can watch the live sidebar. Prod-identical **except the account** (and no systemd; the daemon is a plain bg process): real claude (`~/.claude` mounted **rw**, unlike smoke's `:ro`) + real Alpaca **paper TEST** endpoint. `scripts/verify.sh` gains `run_attach()` (install console deps → daemon bg → wait for first `steering/snapshot.json` with early-death log tail → exec console TUI; trap kills daemon + clears scratch). `docker-compose.verify.yml` gains an `attach` service (tty/stdin, `~/.claude:rw`, named volumes `attach-{steering,workspace,logs}` so daemon writes never land root-owned in the worktree). Keeps F12's fail-closed preflight. Validated: `bash -n` + `docker compose config`; **live probe** booted the daemon on the TEST account and published `snapshot.json` in 9s (real opus research turn started), isolation intact. Finding: the TEST account is currently empty (`recent_fills:0`), so the F13 sidebar date-prefix isn't visible via the live path until the account has fills. Spun off from the F13 sidebar session; built as its own track since it's reusable harness tooling (F10→F12 lineage). Per-track record: `aidlc-docs/tracks/F15/`.


## [F13 MERGED] 2026-05-31 — Sidebar fills date + section spacing
**Timestamp**: 2026-05-31T04:05:00Z
F13 merged: submodule `feat/F13` → fork `main` `aa984da` (pushed to `inventor71/autostock-cli`), parent gitlink bumped on main (`a7a9ea1`). Small presentational change to the operator console trading sidebar (`sidebar/autostock.tsx` + `sidebar-format.ts`): recent **fills now carry a local `MM/DD` date**, shown only when it changes from the previous (newer) row and blank-padded to 6 cols otherwise so the `HH:MM` column stays aligned; **one blank line before each section header** (orders/fills/queued/events via `marginTop=1`; positions stays under the account block). Pure date logic (`mmdd`, `fillDatePrefix`) added to `sidebar-format.ts` with bun unit tests. No snapshot/daemon schema change (`ts` already ISO). Verified: bun sidebar tests 8/8, `bun run typecheck` 19/19 (host + in the F10 docker harness). Driven by explicit UI-format choices (date-on-change; blank line before headers). Per-track record: `aidlc-docs/tracks/F13/`.


## [F17 MERGED] 2026-05-31 — docker-verify sudo-free cleanup (ownership handback)
**Timestamp**: 2026-05-31T05:15:00Z
F17 merged to main (merge commit `f912999`). Fixes the recurring "docker-verify cleanup needs sudo" pain at the root: the container runs as **root**, so anything it writes into the bind-mounted worktree lands `root:root`, and the host can't unlink content inside root-owned dirs (you need write on the parent dir). F11/F12 enumerated known scratch (python caches → turbo/tsgo), but it's whack-a-mole — F15's `attach` added `.opencode/` (measured 3674 root-owned files). Catch-all fix: `cleanup()` (root, via the EXIT trap) now chowns the whole bind mount back to `/app`'s own owner — which equals the host user, since bind mounts preserve numeric uid, so `stat -c %u:%g /app` self-discovers it with **no env**; `-xdev` skips the named volumes (node_modules/steering/…). Applies to all four modes. One-file change (`scripts/verify.sh`, +10). Validated: the **real `cleanup()`** handed a planted root-owned `.opencode/` back to the host (`0:0 → 1000:989`) and host `rm -rf` then worked WITHOUT sudo; a real `verify typecheck` (exit 0, "typecheck OK") left 0 root-owned content files (only the empty `node_modules` volume mountpoint, which is removable). Follows the F10→F11→F12→F15 harness lineage. Note: pre-existing worktrees created before this (e.g. the F15 leftover) still need a one-time `sudo rm`. Per-track record: `aidlc-docs/tracks/F17/`.


## [F9 MERGED] 2026-05-31 — Alpaca-shaped gated console orders
**Timestamp**: 2026-05-31T05:25:00Z
F9 merged: parent-repo `feat/F9` → `main` (`8948e24`, no-ff; base `e8d99a6`). The operator console gains **structured Alpaca-shaped order tools** (`place_stock_order`/`cancel_order_by_id`/`cancel_all_orders`/`replace_order_by_id`/`close_position`/`close_all_positions`) that still pass the daemon **RiskManager→Broker** gate. U-RISK: `Order` trail/extended_hours/client_order_id + `OrderType.TRAILING_STOP`/`OrderClass.OTO`; AlpacaBroker trailing/extras mapping + TIF explicit-reject (no silent DAY downgrade) + native replace/cancel_all; **`RiskManager.receive_human_order`** NEW human-path gate (budget/pool/breaker + clamp + auto-protect + price-sanity + `force`; `evaluate_signal` untouched). U-DAEMON: 6 structured verbs + `PlaceOrderArgs(extra=forbid)`; `_v_place_order` et al route through the gate; **`/buy` shorthand now gated too** (closes the human-BUY bypass critic found); golden contract gains per-verb `command_args` (NFR-3). U-CONSOLE: structured Alpaca-named MCP tools (zod, opencode `ask`-gated) + `handleStructured`; `parser.ts` kept (deterministic shorthand) — structured tools additive (FR-2 hybrid; no submodule source change). Verified: pytest 414, console bun 64, golden contract; live read-only gate smoke + **full docker-attach pty-injection** (NL→AI→`place_stock_order`→ask-confirm→token'd file-drop→daemon `deferred` off-hours) on the TEST paper account. **Follow-ups (NOT merged):** (1) add the 6 `autostock_*` opencode permission keys to the fork/deploy config — tools are denied without them; (2) upstream the attach env fix (`AUTOSTOCK_ROOT`+`STEERING_OPERATOR_TOKEN`) to F15's compose on main; (3) off-hours queue re-emits `deferred` per drain (benign, pre-existing). Per-track record: `aidlc-docs/tracks/F9/`.


## [F18 MERGED] 2026-05-31 — docker-verify attach console-MCP env wiring
**Timestamp**: 2026-05-31T05:45:00Z
F18 merged: parent-repo `feat/F18` → `main` (`8f5468c`, no-ff; base `6902612`). Fixes the F15 `attach` gap found while live-verifying F9: the `attach` service in `docker-compose.verify.yml` lacked `AUTOSTOCK_ROOT` + `STEERING_OPERATOR_TOKEN`, which the opencode console MCP config substitutes (`{env:AUTOSTOCK_ROOT}` = `mcp-server.ts` command path; `{env:STEERING_OPERATOR_TOKEN}` = shared daemon↔console token). Without them the MCP command resolved to `/operator-console/...` (not `/app/...`) → server never started in-container → console order tools absent in `attach`. Added `AUTOSTOCK_ROOT: /app` + `STEERING_OPERATOR_TOKEN: ${STEERING_OPERATOR_TOKEN:-attach-test-token}` (host-overridable, TEST-only default; container is the TEST paper account only). Now `attach` console-MCP connects for ANY track. Validated: `docker compose config -q` + rendered attach env; full attach MCP connection proven live during F9 verify. Per-track record: `aidlc-docs/tracks/F18/`.


## [F19 MERGED] 2026-05-31 — opencode permission keys for F9 structured order tools
**Timestamp**: 2026-05-31T06:10:00Z
F19 merged (F9 follow-up #1): submodule `feat/F19` → fork `main` `bc82b71` (pushed to inventor71/autostock-cli), parent gitlink bumped (aa984da→bc82b71), parent `feat/F19` → `main` `a1851e0`. Adds the 6 `autostock_*` structured-tool permission keys (`place_stock_order`/`cancel_order_by_id`/`cancel_all_orders`/`replace_order_by_id`/`close_position`/`close_all_positions` = `ask`) to `operator-console/cli/{opencode.json,.opencode/opencode.jsonc}`. Root cause (observed live): the fork's default-deny `"*"` was **hiding** the new tools from the console AI, so it fell back to the market-only `/buy` shorthand and reported "지정가 매수 직접 불가". With the keys, opencode surfaces the tools (ask-gated). Main's submodule synced to `bc82b71`. **Operator action: restart the console** so opencode re-reads config + the MCP re-registers → `place_stock_order` becomes available. Per-track record: `aidlc-docs/tracks/F19/`.


## [F8 MERGED] 2026-05-31 — Console Sidebar status.py-rich Data & Color
**Timestamp**: 2026-05-31T09:45:00Z
F8 merged to main (parent `77d5ed9`, submodule fork main `2ac0cda`, both pushed). status.py-rich sidebar: holdings P&L, order role/Δ, recent fills, account invested, green/red+▲▼, width floor 24→36; daemon additive snapshot + PriceBook(12s)/recent_fills(45s) jobs + get_latest_prices broker port. Python 371 green, bun 6 green, 0 new deps. Daemon-side live-verified vs paper. Full per-track record: `aidlc-docs/tracks/F8/`.


## F22 Merged
**Timestamp**: 2026-06-01T05:30:00Z
**Merge commit**: ab6e742
**Summary**: AI-collaborative TUI (timeline bar + turn/symbol overlays), Docker attach MCP fix (alpaca-data.ts .env fallback), runtime.py reason truncation removal, opaque overlay background, colored now-arrow. 489 tests green.


## F23 Merged
**Timestamp**: 2026-06-01T06:00:00Z
**Merge commit**: 927627a
**Summary**: Multi-agent research (Mode B sequential debate + Mode C parallel sub-agents), 5 new signal tools (earnings/insider/analyst_upgrades/institutional/macro), structured lessons.jsonl, configurable via MultiAgentConfig + research.signals. 51 new tests, 482 total, 0 new deps.


## F25 Merged
**Timestamp**: 2026-06-01T09:30:00Z
**Merge commit**: 02f46cb (parent) / 4c21687 (submodule main)
**Summary**: AI-collaborative timeline bar — market-aware 12h view (KST local, IANA-tz DST), 3 market regions + phase badge (● PRE-MARKET/REGULAR/AFTER/CLOSED), date navigation, human intervention markers + overlay, flicker-free monitor polling. Unit A (daemon: et_date sessions, market rule + interventions in monitor.json). verify.sh: re-applied lost F22 fixes (.env copy + operator-console install → fixes MCP -32000) + pointer-only git guard. docker-compose: TZ for correct local time in attach TUI. 556 Python + 21 TS tests, critic 6 findings (2 HIGH + 1 MED applied). Note: submodule git was repeatedly clobbered by docker verify.sh running as root (recovered each time from working tree) → F27 opened to fix root-cause.


## F27 Merged
**Timestamp**: 2026-06-01T12:55:00Z
**Merge commit**: a22952f (parent-only, no submodule change)
**Summary**: docker-verify harness runs as host user (non-root, scripts/verify-run.sh wrapper — fail-loud UID injection) + root-ownership workarounds stripped (cleanup chown handback, .git mv-aside/safe.directory). 4-mode verified non-root (typecheck 19/19, unit 556, smoke+attach OK). Extras found+fixed: missing node-gyp in image, bind-mount mountpoint ownership. Submodule git origin sync pushed (4c21687, F22+F25+timeline unpushed commits). This closes the root-owned-file class of problems (R-1: sudo-free worktree remove, R-2: submodule git corruption) that bit F22/F25.


## F26 Merged
**Timestamp**: 2026-06-01T15:00:00Z
**Merge commit**: bb2da2d (parent) / 674bdb5 (submodule main)
**Summary**: Supervisor mode — `autostock --supervisor` launch flag selects normal (MCP+web+$STEERING_DIR only, source reads blocked) vs supervisor (whole $AUTOSTOCK_ROOT read, secrets excluded) permission profiles. Launcher injects OPENCODE_PERMISSION via env (no opencode engine patch); websearch enabled for all providers (OPENCODE_ENABLE_EXA, keyless Exa). MODE: SUPERVISOR sidebar badge. Two critic passes caught: design matcher anchored-dotall root-level secret leak (../../.env vs .env globs, both now covered), implementation verify-lockdown merged-config modeling. docker-compose: AUTOSTOCK_LOCKDOWN=on added (was missing in attach). verify.sh: supervisor profile build for container. Tests: verify-lockdown 43, launcher 38, registry 16, tsgo 19 — all green. Runtime docker-verify attach confirmed working. Nearby tracks: F28 (UI self-explanation, paused), F29 (codebase orientation, paused).


## R2 merged — speed-review (2026-06-01)
**Timestamp**: 2026-06-01T21:09:00Z
**Summary**: R2 merged (dfb8200). Behavior-preserving speed review: engine ×3.0 (O(n²)→O(n) backtest precompute), optimizer ×5.6 (ProcessPool), parallel price fetch (ThreadPool value-preserving), scoreboard parallel fetch. Full suite + docker verify green.


## F29 merge 2026-06-02 — Supervisor codebase orientation: steer_read{command:/codebase} returns project directory tree (daemon startup scan, depth=2, fnmatch exclusions); 577 tests green, 0 new deps, docker-verify attach verified.


## F32 merge 2026-06-02 — Timeline Markers 사라짐 버그 수정 (_interventions_tail 150-line window → ET-date filter; 566 tests green)


## F31 merge 2026-06-02 — TUI Sidebar Orders 색상 깜박임 버그 수정 (1-line: autostock.tsx side-fallback color when current_price null; submodule feat/F31 → main)


## F34 merged — timeline label z-order (2026-06-02)
**Timestamp**: 2026-06-02T00:00:00Z
**Merge commit**: a366545 (parent, ff) / 43423df (submodule fork main, pushed)
**Summary**: Timeline PRE/OPEN/AFT region labels were occluded by turn/intervention markers (markers painted after the band that embedded the labels). Fix: band → dashes-only; labels rendered as a TOPMOST transparent per-cell overlay (above markers + now-cursor), with clicks on a label cell forwarded to the topmost marker/intervention under that column (hidden marker stays clickable). Per-cell overlay knows its column ⇒ no reliance on screen-global evt.x; `│`/markers/cursor order unchanged (user clarified only the text lifts). New pure `labelCells()` helper + 5 tests (suite 26 pass); tsgo 19/19 (tui-trading covered via opencode). `/critic` feasibility pass confirmed opentui transparent-bg compositing + that click-forwarding is necessary & sufficient. Seed tool `gen_test_timeline.py` gained label-overlap probes (+5/8/11/14m per region boundary) for docker-verify `attach`; user verified visually. Base 378a98b/66c6edc.


## F28 merged — normal-mode UI self-explanation (2026-06-03)
**Timestamp**: 2026-06-03T00:00:00Z
**Merge commit**: d1f72e6 (parent merge) + 02d6a41 (gitlink bump) / b26a930 (submodule fork main, local — not pushed)
**Summary**: Normal-mode console agent couldn't explain its own TUI elements (e.g. timeline topbar `$6.01`) — daemon snapshot had no such field, so it answered "don't know". Added a `steer_read{command:"/ui-legend [element]"}` read verb serving a **static** `operator-console/src/ui-legend.json` (21 entries: topbar/timeline/markers/sidebar/status — **meanings only**, no live values since the user already sees them on screen). Follows the F29 `/codebase` verb pattern: parser READ_VERBS + handleSteerRead branch + `steer_read` description line (the agent-discovery surface — MANDATORY). Scope was deliberately minimized after two `/critic` rounds reversed the original design: dropped live-value `data_source` mapping + TUI startup auto-generation + fallback (the first design wrongly put serving in the python daemon; serving is entirely TS in `operator-console/src/`, daemon uninvolved). Marker meanings authored from `format.ts` (turn-type glyphs ●○◆▲↻✕✚ — the original ◆BUY/○SELL assumption was wrong). Read via `import.meta.url` + try/catch (not top-level import → graceful on malformed). Drift managed by PR convention (`tui-trading/AGENTS.md` + json `_note`), no auto-gen. schema.ts/golden contract untouched; python daemon unchanged; 0 new deps; readOnly verb (order path untouched); F26 permissions unchanged. 131/0 parent tests + runtime handler check (the original `$6.01` question now answered). Integrated over concurrent F34 (z-order) cleanly — submodule main reset to 43423df (F34) before re-merging F28 AGENTS so F34 wasn't lost. Base a4b1732 (worktree off 378a98b).


- 2026-06-03 — **F35 merged** (main 2253029): `operator-console/cli` 서브모듈을 history-preserving git subtree로 본 repo에 흡수(monorepo). 콘솔 43커밋 보존(blame 원저자 추적 OK), 서브모듈 git 상태 정리(.gitmodules/.git/config/.git/modules 제거, .git 127M→72M), 단일repo 툴링·룰·gitleaks pre-commit 훅 추가, 죽은 vendored .github 제거. 검증: 콘솔 typecheck 19/19·py 104·fresh-worktree 자동포함. ⚠️ 후속: F16/F36 등 pre-F35 트랙은 재개 시 cherry-pick(서브모듈 워크플로 금지).


- 2026-06-03 — **F16 merged** (main `cd863a0`): `BrokerApiBroker` — a `BaseBroker` impl over the Broker API sandbox so the bot can run strategies inside the simulated account-farm accounts (per-account via `BrokerClient`/`account_id`), bypassing the Trading API's 3-paper limit. Fail-closed init, masked logging (SECURITY-03), full parity (orders incl. bracket/OCO, positions, fills, ledger, basic-auth market data via `StockHistoricalDataClient`). Provider-selected by `config/settings.yaml` `broker.provider` + `BROKER_*` env; `--fund` action added to `broker_create_accounts.py`. Live-verified **25/25** on a real farm account incl. bracket OCO round-trip; 2 HIGH bugs found & fixed (B1 creds attr on BrokerClient, B2 `get_open_orders` `status=ALL` to surface HELD SL leg). 34 unit + 611 regression green. Per the F35 follow-up note, the stale pre-F35 worktree was recreated and `feat/F16` **rebased onto monorepo main** (`2253029`, clean — F23's config/main.py edits disjoint), then merged `--no-ff`.


- 2026-06-03 — **F36 merged** (main `cb8c9ad`): timeline historical-overlay bug + marker flicker. Past-date turn/intervention markers opened "Turn not found" / silent no-op because overlays resolved from the LIVE monitor payload, not the selected date's session. Fix: overlays render from the same session the timeline read — `readHistoricalSession` reads turns/decisions/human_directives for the date and reconstructs each decision's turn_id (`correlateTurnId` mirrors runtime.py `_correlate_turn`, since decisions.jsonl carries none); overlay state carries the full turn + its decisions (`openTurn(turn,decisions)`), TurnOverlay renders from props (no live re-lookup). During verification a separate **marker flicker** surfaced and was root-caused with the headless `@opentui/core` TestRenderer (composite buffer always correct → live-renderer per-cell damage tracking dropped the N moving `position:absolute` marker boxes on date change). Fixed by rewriting MarkerRow as ONE composed `<text>` of styled spans (the TickRow/band pattern that never flickers) + a single row hit-test (evt.x→column→entity); historical session/layout decoupled from monitor-poll churn; barWidth memoized. Added reusable `scripts/seed_timeline.py` (turns + correlated decisions + interventions, per-date deterministic variation, `--days N`). Verified: tsgo 0 errors, 35 tui-trading tests, headless TestRenderer (paint + click mapping), **live attach (user-confirmed)**, `/critic` pass (evt.x==column SAFE; naive-decision-ts tz handling = project-wide `compute_et_date` convention, consistent co-located; off-window edge collision pre-existing LOW). Worktree off 2253029 (clean — F16's Python-only commits disjoint from the TUI files), merged `--no-ff`.


- 2026-06-03 — **F37 merged** (main `f26ab6a`, code `fd5cd5b`): `.env` 키 컨벤션 정합화 — `ALPACA_SECRET_KEY` → `ALPACA_API_SECRET`. Alpaca만 `<provider>_..._KEY`/`<provider>_..._SECRET` 패턴(BROKER_API_*, KIS_PAPER_APP_*)에서 벗어나 있던 것을 정렬. 하드 리네임(폴백 없음, 단독/로컬). 변경: `config/config.py` Settings 필드 `alpaca_secret_key→alpaca_api_secret`(`env_prefix=""`로 `ALPACA_API_SECRET` 자동 매핑) + Python 사용처 3곳; operator-console `alpaca-data.ts`(env키/const/헤더/가드/401문구)+test; **계획 외 1건** `cli/.opencode/opencode.jsonc` MCP env passthrough `{env:ALPACA_API_SECRET}`(미변경 시 콘솔 MCP 시크릿 silent-break — 잔존 grep으로 포착); docs(`.env.example`/`.env.test.example`/`README`/`settings.yaml` 주석); 로컬 main 트리 `.env` 키명만 갱신(값 유지). 검증: `bun test alpaca-data` 24 pass/0 fail + `Settings()` 스모크(신필드 존재·구필드 제거·env 매핑) + py_compile 4파일 + 잔존 grep 0(역사적 aidlc-docs 문서는 의도적 미변경). 단일 단위 rename, User Stories/App Design/Units Gen 스킵. Base 1553dc0, `--no-ff` 머지.


- 2026-06-03 — **F42 merged** (main `b0b1275`): F37 리네임 escape 핫픽스. F37이 Settings 필드(`alpaca_api_secret`)와 3개 모듈만 고치고 **컴포지션 루트와 운영 스크립트를 누락** → `main.py`(19,42,314, create_data_provider/create_broker[alpaca]), `scripts/verify.sh`(115,121), `scripts/status.py`(180,184)가 제거된 `settings.alpaca_secret_key`를 계속 참조 → 데몬이 Alpaca 경로 **startup에서 `AttributeError` 크래시**(F38 docker-verify `attach`에서 발견). 7곳 `alpaca_secret_key`→`alpaca_api_secret`. 검증: 잔여 grep 0 / py_compile / `Settings().alpaca_api_secret` 존재·구필드 제거 스모크. Base 72aba01, FF 머지. (동시-세션이 F39/F40/F41 선점 → 핫픽스 F42 채번; 최초 F39 시도가 진행 중 트랙 worktree를 건드려 즉시 롤백·복구.) feat/F38은 b0b1275 위로 리베이스해 전파.


- 2026-06-03 — **F40 merged** (main `65e65ab`, code `2a17322`): autostock 런처 `-h`/`--help` 핸들러. 기존 `cli.ts`는 인자 파싱/도움말이 없어 `autostock -h`가 opencode yargs help만 띄우고 런처 고유 옵션 `--supervisor`는 어디에도 노출 안 됨. opencode가 `-h`를 stderr로 깔끔히 출력+정상 종료(`index.ts:195-204`, 무거운 미들웨어 미실행)함을 확인 → **loose-fuse** 채택: 런처 섹션을 먼저 찍고 `-h`를 opencode로 패스스루해 그 아래 전체 yargs help가 이어지게(캡처/파싱 없음). 구현: `classifyArgs()`(순수, export — `--supervisor` strip[opencode `.strict()` 누수 방지]/`-h`·`--help` 감지·유지/나머지 패스스루) + `launcherHelpSection()`(순수, export, 비밀값 미포함) + `runHelp()`(preflight·데몬 **이전** short-circuit, resolveConfig 실패해도 exit 0); `main()` 비-help 경로는 classifyArgs 재사용(동작 보존). 미인식 옵션 경고는 opencode `.strict()`가 이미 거부하므로 런처 측 추가 안 함(검토했던 FR-3 폐기). 검증: `bun test test/launcher.test.ts` 45 pass/0 fail(+7: classifyArgs 5 + launcherHelpSection 2) + 렌더 스모크. minimal depth(User Stories/App Design/Units Gen 스킵, 단일 유닛). Base 72aba01, `--no-ff` 머지.


## /ai-dlc-merge — Stage 0 큐 승인
**Timestamp**: 2026-06-03T00:00:00Z
**User Input**: "지금 doc 커밋으로 분리" / "승인: F41 → F39 → F38"
**AI Response**: merge-awaiting 큐 = F41, F39, F38 (모두 post-F35 base, 사전 게이트 통과). 겹침: F38∩F39 = `operator-console/src/mcp-server.ts` (유일). 승인 순서 F41 → F39 → F38 (독립 먼저, 겹침은 base-age 후반). 머지 전 main 트리의 미커밋 문서 변경(F30/F35 state.md + untracked aidlc-docs)을 단일 doc 커밋으로 분리. 이후 멈춤 조건에서만 정지하며 자율 진행.
**Context**: /ai-dlc-merge Stage 0 — 유일한 승인 게이트 통과.


- 2026-06-03 — **F41 merged** (main `f330370`): research turn 마커 오버레이 정보 강화. multi-agent research turn 오버레이가 빈 summary + agent별 평가 미영속이던 두 근본원인 해결. Unit1 `agent-eval-persistence` — `src/agent/agent_reports.py` 신규(per-turn 평가 리포트 스키마, `_mask_secrets` 준수) + `orchestrator`의 sequential/parallel 두 경로에서 평가 캡처 + `record_turn` summary/turn_id 버그수정(단일 `_run` 경로만 summary 채우던 것). Unit2 `overlay-drilldown` — tui-trading `readAgentReport`/`maskSecrets` + drill-down `turn-overlay.tsx`(runtime.py 무변경, TUI 직접 읽기). `/ai-dlc-merge` 큐 1/3: 큐 진입 시 main(7c62527, 사전 doc 동기 커밋) 위로 rebase(2커밋 clean) → verify 재실행 green(pytest 621/0 regress · tui-trading bun 44 · turbo typecheck 19/19) → `--no-ff` 머지. 겹침 없는 독립 트랙이라 큐 선두 배치.


- 2026-06-03 — **F39 merged** (main `f6569ea`): normal-mode 코드/소스 질문 차단. 운영자 콘솔 에이전트가 supervisor 아닌 normal 모드에서 소스/구현 내부 질문에 코딩 어시스턴트처럼 답(트리 추측 포함)하던 동작을 강화. L1 프롬프트 가드(`operator.md` 페르소나 + `normal-guard.md` 거부규칙을 launcher가 `OPENCODE_CONFIG_CONTENT`로 프로필별 주입) + L2 구조적 차단(`/codebase`를 supervisor 전용 fail-closed 게이팅 — steer-handler supervisor 파라미터 + `cli/.opencode/opencode.jsonc` mcp.environment `AUTOSTOCK_SUPERVISOR` + mcp-server CODEBASE 설명 조건부). 거부 메시지에 supervisor 미언급(Q4=B, 개발자 전용 숨김). 0 new deps; critic AR-1/AR-2 반영. `/ai-dlc-merge` 큐 2/3: main(c49e4fd) 위로 rebase(1커밋 clean, F41 머지와 파일 disjoint) → verify 재실행 green(operator-console own suite 144/0 · verify-lockdown 2-profile PASS · opencode registry 16/0; 전체 재귀 `bun test`의 ws://localhost opencode 통합테스트 실패는 사전존재 env-dependent, F39 스코프 밖) → `--no-ff` 머지. (F38과 `operator-console/src/mcp-server.ts` 겹침 → 다음 F38 rebase에서 해소.)


## /ai-dlc-merge — Stage 0 큐 승인 (2026-06-03)
**Timestamp**: 2026-06-03T22:30:00Z
**User Input**: "응 진행"
**AI Response**: Merge 큐 = F48 → F49 → F50 (모두 merge-awaiting, post-F35, 겹침 0). F47 제외(↑0), F30 제외(Operations 승인 대기). 이후 자율 진행.
**Context**: /ai-dlc-merge Stage 0 승인 게이트 통과.


- 2026-06-03 — **F47 merged** (main `3eee516`): surge stock history detection & root-cause analysis — 급등주 자동 감지·원인 분류·기록. `src/surge/` (records/detector/store/settings) + 2 agent tools (surge-list/surge-analyze). 15 files (+939/-4), 31 new tests, 680 full regression green, 0 new runtime deps. Rebase clean (no file overlap with F48/F49/F50 TS changes).


- 2026-06-03 — **F50 merged** (main `3f3b725`): TUI status+timeline single-line layout — merge StatusRow into NavRow (queue/working items + nav bar on same line). 1 file, 22 insertions, 36 deletions. 69/69 tests, 19/19 typecheck.


- 2026-06-03 — **F49 merged** (main `00b3559`): synthesis verdict drill-down text overlay fix — add `wrapMode="word"` to `<text>` element (preventing Yoga layout overlapping on long synthesis lines, up to 500 chars). 1 file (+1/-1). 69/69 tests, 19/19 typecheck.


- 2026-06-03 — **F48 merged** (main `a669761`): sidebar cleanup — rebrand "OpenCode" → "AutoStock", remove workspace path/LSP sidebar plugin/session ID hash, compact Context tab to single line. 7 files (6 modified + 1 deleted), 6 insertions, 132 deletions. Rebase clean, typecheck 19/19, test failures pre-existing on main (attention.test.ts rebrand remnants).


- 2026-06-03 — **F38 merged** (main `c395faf`): 운영자 수동 turn 트리거 steering 명령. 자동 스케줄(시장오픈/인터벌)을 기다리지 않고 운영자가 research turn을 즉시 트리거(today_count==0인데 자동 트리거 대기 중인 상황 해소). Python: `SteeringVerb /research` + `_v_research` 핸들러; CommandBus 워커 스레드 블록 방지 위해 `coordinator.start_priority_async`로 off-thread 실행(wake/reconcile 양보, 드롭 없음 started/queued), `on_done→bus emit_outcome` 완료 푸시(corr_id, completed/failed). TS: parser/schema/contract + `mcp-server.ts` help(TURN `/research`) 배선. `/ai-dlc-merge` 큐 3/3(겹침 트랙, base-age 후반 배치): main(7766c6a, F39 머지 반영) 위로 rebase — **F39와 `operator-console/src/mcp-server.ts` 겹쳤으나 자동 3-way 병합 clean**(F39 supervisor-gating L29-82 + F38 research verb help L45 서로 다른 영역, 공존 검증) → verify 재실행 green(pytest 638/0 regress · operator-console own TS suite 145/0; F38은 cli 무변경이라 turbo typecheck 19/19는 동일 base의 F41 실행에서 확인됨) → `--no-ff` 머지. 큐 비어 종료.


- 2026-06-03 — **F46 merged** (fb06517): agent account tool down — prepend venv bin to agent PATH (51 lines, 2 files, 54 tests green)


- 2026-06-03 — **F44 merged** (dc73fcb): in-flight turn progress label + same-type turn dedup (584 lines, 14 files, 39+8 tests green)


- 2026-06-03 — **F45 merged** (007aa11): timeline 12h window auto-align + nav buttons (608 lines, 10 files, 43 tests green)


- 2026-06-03 — **F43 merged** (b0ed183): daemon code-version skew self-heal (396 lines, 8 files, 9+6 tests green)


- 2026-06-04 — **F57 merged** (main `f53c4a5`): 상단 status+날짜 nav 동일선 바(F50) 두 버그를 NavRow 한 곳에서 수정. (1) status 칩 내부 `<box>` 가 `flexDirection` 미지정 → opentui 기본 `column` 으로 `"● "`+라벨 세로 적층 → NavRow 2줄 → 부모 `height={3}`(NavRow/TickRow/MarkerRow) 초과로 바 깨짐 → `flexDirection="row"` 부여(line 157 nav-root와 동일). (2) `void props.blinkOn` 이 `<Show>` 자식 본문에서 1회만 실행 → 반응형 `label()`(=`fmtTurnLabel(…, Date.now())`)이 500ms blink 틱 미추적 → research 경과시간 정지 → blinkOn 읽기를 `label()` 내부로 이동(TickRow/MarkerRow now-cursor blink와 동일 패턴) → 실시간 증가. 1 file (+11/-3). base=현재 main HEAD(6bf1b31)라 rebase 불필요·겹침 없음(단독 큐). verify: `bun test progress-label.test.ts` 8/8, `tsgo -p tui-trading` timeline-bar.tsx 오류 0건 → `--no-ff` 머지. 큐 비어 종료.


- 2026-06-04 — **/ai-dlc-merge triage** — 큐 후보: F54, F56 (둘 다 merge-awaiting). 차단신호: foreign `.claude/commands/ai-dlc-merge.md`(수정), 비active 고아문서 F47(merged)/F51(merged) untracked. 사용자 판단 대기.


- 2026-06-04 — **F54 merged** (main `5cd2eb4`): 숏 포지션 기능 — 시장 균형 숏 매매 + 숏 분석. `Position.side`(LONG/SHORT)·`ratchet_stop(position_side=)` 추가, `Signal`/`OrderSide`/`DecisionAction` enum 확장(추가만, 하위호환). 숏 리스크(mandatory stop above entry, squeeze guard)·실행(SimulatedBroker liability-aware equity, auto-flip)·에이전트 분석(short_data 툴). 큐 1/2: main(03de978+cleanup 2커밋) 위로 feat/F54 rebase clean(겹침 없음, 5커밋 replay) → verify 재실행 pytest 773/0 regress → `--no-ff` 머지. F56 다음.


- 2026-06-04 — **F56 merged** (main `6b043c6`): code-review 후속 버그 수정. C-1 surge `prev_close` 해석(중간날짜 매핑/단일바·빈바 None), C-2/4/5/6 early-session ET `monitor_end`·finalize·effective retention=75, C-3 executor cursor stall(supersede 전진·error 앞 정지·terminal 비재실행). 14 신규 테스트(`test_f56_bugfixes.py`). 큐 2/2: F54 반영된 main(5cd2eb4) 위로 feat/F56 rebase — `config/settings.yaml`·`src/agent/executor.py` 겹쳤으나 자동 3-way clean(서로 다른 영역) → verify 재실행 pytest 787/0 regress → `--no-ff` 머지. 큐 비어 종료.


- 2026-06-04 — **/ai-dlc-merge triage+queue**: 작업트리 PASS(foreign 없음 — M1 rules/CLAUDE.md/registry/R0·F1-F7 migration, F30·F55 문서 노이즈는 active 소유). 큐=F58 단독. F55 제외(merge-awaiting 라벨이나 feat/F55 ↑0, 코드 미커밋). F58 rebase onto main d988a65 진행.


- 2026-06-04 — **F58 merged** (main `0e071e1`): 상단바(NavRow) cost 라벨을 isLive 전용(today_cost_usd, ET세션 전체)에서 **현재 뷰 윈도우 합계**로 일반화 — 과거 날짜/구간으로 이동해도 턴 사용량($)이 보이게. `format.ts`에 순수 헬퍼 `windowedCost(turns,start,end)`(ts ∈ [start,end) 합산, 파싱불가·범위밖 제외, NaN-safe) + 단위테스트 8케이스(start inclusive/end exclusive 경계, 멀티날짜, 빈 윈도우, 잘못된 ts, 0/NaN). `timeline-bar.tsx`에 windowCost memo + NavRow isLive 게이트 제거(prop todayCost→windowCost). 데이터: 과거=turns.jsonl, 라이브=monitor.json 둘 다 per-turn cost_usd 보유(Python 데몬 무변경, TS-only). 3 files (+94/-6). base 03de978 → 현재 main d988a65 위로 rebase(충돌 0 — F54/F56는 tui-trading 미변경) → verify 재실행 green(bun test 16/16, tsgo timeline-bar/format 0건) → `--no-ff` 머지. 동작 변경: 라이브 cost 가 ET세션 전체→윈도우 합계(사용자 윈도우 범위 선택). F55 제외(merge-awaiting 라벨이나 코드 미커밋, 같은 파일 수정 중 → 추후 F58 위 rebase로 해소). 큐 비어 종료.


- 2026-06-04 — **F51 merged** (faec7b7): early-session signal detection — 1-min bar circular buffer, ±5%/10min trigger, pre/post window dump, multi-symbol get_bars provider extension (1287 lines, 13 files + 28 new tests + 300 PBT examples, 686 regression green, 0 new deps)


- 2026-06-04 — **F53 merged** (621b227): MCP steer_read /thesis /theses — expose agent position thesis files from workspace/positions/ (141 lines, 8 files TS only, 0 daemon changes, 686+46 tests green)


- 2026-06-04 — **F52 merged** (4e64781): execution audit trail + selective cursor advancement — persist all outcomes to execution_outcomes.jsonl, cursor stops at no_order/error for retry, emit exec_outcome steering events (317 lines, 7 files, 680 tests green)


- 2026-06-04 — **/ai-dlc-merge triage** PASS — foreign 변경 없음; 노이즈는 F30/F59 문서(active)·F55 소유뿐. 큐 후보: F55, F59 (둘 다 merge-awaiting, 겹침 0). 사용자 승인 범위 = **F55만 머지** (F59는 다음 기회).

- 2026-06-04 — **F55 merged** (5c9166d): 타임라인에 "데이마켓"(overnight, after_close→익일 pre_open / 20:00–04:00 ET) 세션 amber 밴드 추가. ET 자정-넘김 대응 — 전날·당일 두 overnight span을 모두 derive·emit하고 뷰 밖은 0폭 clamp(critic HIGH). 4 files(timeline-layout/format/timeline-bar + test), rebase 후 85/0 green.
- 2026-06-05 — **/ai-dlc-merge triage** — PASS. Foreign/unregistered: none. Queue: F59→F60. Noise left untouched: F30/F61/F62 (active docs), F64/F65 (active-paused docs), aidlc-state.md (shared).
- 2026-06-05 — **F59 merged** (88f6edf) — 운영자 /short·/cover shorthand (verb 대칭, /sell 숏-오해 footgun 해소). TS parser/schema + Python steering.
- 2026-06-05 — **F60 merged** (see merge) — 숏 안전 제어: easy-to-borrow 게이트(라이브 브로커 ETB) + 마스터 on/off 토글(risk.shorting_enabled, 기본 OFF/opt-in) + code-review 6건(BrokerApiBroker side/is_shortable, SELL-on-SHORT guard, transient-cache, TUI verbs). 810 green.
- 2026-06-05 — **/ai-dlc-merge triage (scope: F61 only)** — working tree: F30(active, mod)·F61(target, merge-awaiting)·F62(active, merge-awaiting)·F64(active paused)·F65(active paused) 문서 노이즈만; foreign/미등록 없음 → PASS. F62·F65도 merge-awaiting이나 사용자 스코프("이 트랙만")로 제외. main이 F59+F60 머지로 e8b112b→43b26d7 전진 → F61 rebase 필요(겹침 5파일: config/config.py, settings.yaml, main.py, orchestrator.py, prompts.py).
- 2026-06-05 — **F61 merged** (1437d44) — 리서치 턴 시장 시그널: 무버/read-through(정적피어맵+LLM)/실적캘린더(Finnhub), Alpaca뉴스(Benzinga), push+툴; 41 files (+2385/-21), 877 tests; rebase F60(숏토글) 교차통합 無회귀
- 2026-06-05 — **F30 merged** (1609182) — KIS OpenAPI 한국주식 페이퍼트레이딩(KIS 단독 PoC): KisPaperBroker(모의 raw REST, 토큰 lazy/throttle)+KisDataProvider+동적 Universe(KR 시총상위/US S&P100, trading.symbols 전면 대체)+emulated OCO(TP 거래소LIMIT/SL 폴링)+KST 스케줄+always-on reconcile. 라이브 검증(모의 장중 주문 placement 전부 통과)+code-review 4 bugs(OCO leg cancel/journal lock/TP protection/silent errors). rebase 교차통합(config signals+universe 공존, main.py 3-broker, manager.py SHORT+override 병합, F61/F51 universe reads 재배선), 927 tests green.
- 2026-06-06 — **/ai-dlc-merge triage (scope: F62,F64,F65)** — PASS. 작업트리 노이즈: F62/F64/F65 문서(머지 대상)·F63 문서(registry 미등록, 비대상 — 명시경로 스테이징으로 미접촉). foreign 없음. 큐(선형스택): F62→F65→F64 승인.
- 2026-06-06 — **F62 merged** (9342691) — 귀속/효능 base(자가학습 U0): lessons_cited/prompt_version→Decision 부착 + efficacy.py(레슨별 효능 스코어). 7 files (+401/-2), efficacy.py/test_efficacy.py 신규(192-line 테스트). rebase onto F30-merged main 충돌 없음, 941 green. 스택 base — F65/F64 후속.
- 2026-06-06 — **F65 merged** (89927c7) — 하이브리드 레슨 회상(자가학습): recency 절단 → 상황(태그 사전필터)+효능(F62 스코어) 랭킹. recall.py/test_recall.py 신규 + orchestrator/prompts 배선. 4 files (+442/-8), 955 green. F62 위 스택(rebase 시 F62 커밋 자동 skip).
- 2026-06-06 — **F64 merged** (a383f8d) — 헌장 경계 자가재작성(자가학습 스택 최상위): 불변 CONSTITUTION 안에서 가이던스 프롬프트 자동 진화 + compliance-check + rollback. constitution.py/self_rewrite.py 신규 + test_constitution_pin/test_self_rewrite. 8 files (+687/-17), code-review 15건 반영. rebase orchestrator.py 충돌 1건(F61 signal_brief + F64 guidance_preamble 병합), 975 green. F62→F65→F64 스택 머지 완료.
- 2026-06-06 — **/ai-dlc-merge triage (scope: all merge-awaiting)** — PASS. 작업트리: F63/F66/F67 문서(머지 대상)+aidlc-state.md(공유), foreign 없음. 큐 F66→F67→F63 승인(3트랙 상호 파일 겹침 0; F63은 base 30e3609로 최신 main 위 rebase 필요).
- 2026-06-06 — **F66 merged** (fff3d9e) — Health check 발견 config 불일치 수정: settings.yaml llm.provider claude → claude_code(실제 런타임 provider 일치). 1줄, config 로드 검증.
- 2026-06-06 — **F67 merged** (4f2b1b2) — 자가학습 스택(F62/F65/F64) code-review 핫픽스 6건: collector ts AttributeError(효능 귀속 전멸 수정), _run stamp 인덱스 불일치, date 미import(F821) [명확버그]; efficacy 캐시 튜플 원자화, regime 전체텍스트+substring, 프롬프트 _assemble_turn 단일레이어+sequential synthesis signal_brief [UAQ 판단]. 6 files (+83/-30), 회귀테스트 3. 977 green. follow-up: #7/#8/#10(latent/cleanup).
- 2026-06-06 — **F63 merged** (58e1dda) — Health Check Loop: 9차원 시스템 모니터링 모듈(account/broker/config_env/data_pipeline/llm/logs/process/resources/risk) + scripts/health.py CLI(--root cross-checkout). circuit breaker yfinance fast_info camelCase+info 폴백, env var는 settings 속성 기반. 14 files 신규, base 30e3609에서 최신 main 위 rebase 무충돌, 977 green + 모듈 import 클린.
- 2026-06-06 — **/ai-dlc-merge triage (재확인)** — PASS. 직전 foreign(룰파일/.github/codekb)은 af2cbca M1 CodeKB 커밋으로 반영 완료 → 작업트리는 F68 문서 + aidlc-state.md(공유)만. 큐: F68 단독.
- 2026-06-06 — **F68 merged** (9eaf8a0) — F67 follow-up 자가학습 정리: #10 is_meaningful/persists dead code 삭제 + MIN_EFFICACY_SAMPLE 상수 단일화(임계 3곳 drift 제거), #8 collect_outcomes per-day outcomes 캐시 공유(recall+EOD self-rewrite 1회/일), #7 롤백 시 같은 EOD rewrite 건너뛰기+cur/sample 롤백후 읽기. 6 files(+135/-92), +4 orchestrator 테스트, 978 green. base 58ca6a7→af2cbca(M1 CodeKB) rebase 무충돌.

## /ai-dlc-merge — Stage 0a triage (scope: R3, R4)
**Timestamp**: 2026-06-07
**Result**: PASS. Working-tree noise = R5 docs only (tracks/R5/state.md modified + untracked 0-investigation.md); R5 per-track state.md = `active (Stage 0 investigation)` → normal noise, left untouched. No foreign/non-active changes. R3 & R4 both `merge-awaiting`, clean worktrees, 1 commit each, post-F35 base, zero file overlap.

## /ai-dlc-merge — Stage 0b queue approval
**Timestamp**: 2026-06-07
**User Input**: "승인 (R3 → R4)"
**Queue**: 1. R3 (refactor/R3, ↑1, no overlap) → 2. R4 (refactor/R4, ↑1, no overlap). Excluded: none. Left as noise: R5 docs (active).

- 2026-06-07 — **R3 merged** → main cfd34b0 (refactor/R3, ↑1). AlpacaShapedBroker base extracted; full suite 1022 passed. Worktree+branch cleaned.

- 2026-06-07 — **R4 merged** → main f43366f (refactor/R4, ↑1, rebased onto post-R3 main). JSONL read/write consolidated into src/core/jsonl.py; full suite 1028 passed. Worktree+branch cleaned.

- 2026-06-07 — **R5 closed (won't-do)** at Stage 0 investigation. Real overlap ~12 lines (claude -p JSON-envelope) in hot agent brain; agent retry couples to exact exception text → shared helper relocates not simplifies; strategy-only use = no dedup. No code change. Registry → abandoned (won't-do).

## /ai-dlc-merge — Stage 0a triage + 0b approval (scope: all merge-awaiting)
**Timestamp**: 2026-06-07
**Triage**: PASS — working tree clean (no foreign/non-active changes).
**Candidates**: R6 (refactor/R6 ↑2), F70 (feat/F70 ↑1), F69 (feat/F69 ↑3) — all merge-awaiting, post-F35 base.
**Overlap**: R6∩F69=runtime.py (mechanical import block); F69∩F70=config/config.py (non-conflicting hunks); R6∩F70=none.
**User Input**: "승인 (R6 → F70 → F69)"
**Queue**: 1. R6 → 2. F70 → 3. F69 (independents first; F69 central → last, absorbs both overlaps on rebase). Excluded: none.

- 2026-06-07 — **R6 merged** → main 230f74d (refactor/R6, ↑2, rebase no-op base=main). ET market-tz consolidated into src/core/markettime (ET/et_now/et_today); 7 dup constants + today_et→et_today + agent_trace.py folded in; full suite 1033 passed. Worktree+branch cleaned.

- 2026-06-07 — **F70 merged** → main e4676fc (feat/F70, ↑1, rebased onto post-R6 main, 충돌 없음). 섀도우 벤치마크(결정론 baseline 측정자) — src/benchmark/* + buy_and_hold; full suite 1063 passed. Worktree+branch cleaned.

- 2026-06-07 — **F69 merged** → main a0025b3 (feat/F69, ↑3, rebased onto post-R6+F70 main). Health Check TUI 통합 (daemon steering/health.json publish + TUI glyph/overlay). runtime.py R6와 자동병합(검증: ET 전환+health imports 공존, stragglers 0), config.py F70와 자동병합. verify green (pytest 1071 + tsgo 19/19). Worktree+branch cleaned. Post-merge guide 존재(user-facing TUI).

- 2026-06-08 — **/ai-dlc-merge triage** — 작업트리 노이즈=공유 aidlc-state.md(R7 active 행)만, foreign 없음 → 통과. 큐: R7 단독(merge-awaiting, post-F35, 겹침 없음).
- 2026-06-08 — **/ai-dlc-merge 승인** — 큐: R7 단독. rebase→verify→merge→close 자율 진행.
- 2026-06-08 — **R7 merged** (3dde03c) — BrokerApiBroker side/TIF 교정: BUY_TO_COVER→BUY(short-cover 버그), 미지원 TIF fail-closed(opg→raise, ioc/fok 지원). Alpaca/Broker API 동작 통일. 전체 1073 passed.
- 2026-06-11 — **/ai-dlc-merge 시작** (큐: R9→R11→R12→R10, 사용자 지정+선제 critic 검토). Triage: 노이즈 = tracks/F71/**(타 세션 active inception, registry lag) → 보존·통과. 예상 충돌: aidlc-state.md만(해소=ours; prep e7d14cb).
- 2026-06-11 — **R9 merged** → main c3c0137 (config↔settings 모듈명 통일; 1073 passed; registry-only rebase conflict→ours)
- 2026-06-11 — **R11 merged** → main 37fc0b2 (strategy 접미사 제거 5모듈; 1073 passed; registry-only conflict→ours)
- 2026-06-11 — **R12 merged** → main 018c59e (brokers 네이밍 + provider account_farm 클린브레이크 + fails-loud; 1073 passed; registry-only conflict→ours)
- 2026-06-11 — **R10 merged** → main 2245def (data/intraday 서브패키지 + -m 클린브레이크; 1073 passed + -m smoke; rebase clean)
- 2026-06-12 — **/ai-dlc-merge 시작** (큐: R8→F71→F72, 사용자 승인 — F72는 rebase 시 screening_log→logs/screening 동일방향 정돈 포함). Triage: 공유 registry 노이즈(F72 행) + tracks/F71/inception/(active) → 통과.
- 2026-06-12 — **R8 merged** → main d065ed6 (agent logs/·learning/ 재구조화; main verify 1073 passed) ※ 1차 merge가 registry 노이즈에 막혀 실패→복구(stash-merge-pop); close 커밋에 F72 등록행 동승
- 2026-06-12 — **F71 merged** → main fdfc041 (모바일 기반: opencode serve+WebAuthn+PWA addon; typecheck 19/19 + 테스트 38 green; UI는 후속 트랙)
- 2026-06-12 — **F72 merged** → main 7b4b409 (스크리닝 퍼널 로깅+/screening 뷰; 1087 passed; 머지 시 R8 구조 정합 fixup: logs/screening + turn_log 참조 3곳)

## /ai-dlc-merge — triage + queue (2026-06-13)
- Triage PASS: work-tree noise = shared `aidlc-state.md` (M) + untracked `tracks/F73/`,`tracks/F76/` (both active-owned). No foreign/non-active paths.
- Merge queue (merge-awaiting): R13 (feat/R13 ↑2, pure tests/ reorg, post-F35, no registry touch), F75 (feat/F75 ↑1, opencode WebAuthn hardening, post-F35, self-registers row). No file overlap → independent. Excluded: none. Left as noise: F73/F76/F74 active docs.
- 사용자 승인 (2026-06-13): 큐 [R13, F75] 제안 순서·근거 승인 ("승인"). 이후 자율 진행 — 멈춤 조건에서만 정지.
- 2026-06-13 — **R13 merged** → main 401d1de (feat/R13, tests/ 네이밍·구조 정비; verify 1087 pass green).
- 2026-06-13 — **F75 merged** → main 25bcb28 (feat/F75, WebAuthn 게이트 강화 F71 후속; verify 33 pass green). 라이브 스모크는 post-merge-guide 참조.
- 2026-06-13 — **/ai-dlc-merge** (큐: F74 단독, 사용자 승인; F75는 타 세션이 기머지). Triage: F73/F76/F77 docs+F77 registry행 노이즈 → 통과.
- 2026-06-13 — **F74 merged** → main 962b2e1 (promptfoo evals 프레임워크; 1214 passed; rebase 후 R8 stale-import 1건 fixup — sweep의 zsh 변수분리 버그도 교정)
- 2026-06-13 — **/ai-dlc-merge** (큐: F77 단독, 사용자 승인). Triage: foreign 0바이트 깨진이름 파일 1개 → 사용자 승인 삭제; F76/F78 docs+registry행 노이즈 → 통과.
- 2026-06-13 — **F77 merged** → main e06368e (StockTwits 리테일 sentiment — 시간당 스윕+baseline z-outlier+브리프; 1212 passed; critic 2라운드 5건 반영). 라이브 검증은 post-merge-guide 참조 (데몬 재시작 + 베이스라인 ~12h 필요).
- 2026-06-13 — **/ai-dlc-merge** (큐: F78 단독, 사용자 승인). Triage: F76/F79 docs(active)+aidlc-state.md 노이즈 → 통과. base==main(01ced61)이라 rebase no-op.
- 2026-06-13 — **F78 merged** → main 1d3330c (이벤트-레이더 Tier1: Finnhub IPO 캘린더 소스+brief 'Imminent IPOs/catalysts' push 섹션+ipo_calendar pull 도구+research Regime nudge[단일+멀티에이전트]; 인지 전용, universe 비필터·day-1 직매수 제외. 246 signals/evals passed; code-review 1건[FR-5 nudge 활성경로 누락] 수정+회귀가드. 사전존재 F77 sweep 3건 실패는 무관/별도). 라이브 검증·튜닝은 post-merge-guide 참조.

## /ai-dlc-merge — F80, F82
- 2026-06-14 — **merge run start** — triage PASS (working tree: shared aidlc-state.md + active-track docs F76/F81/F83 noise only; no foreign/non-active). Queue: F80 (↑1, base 01ced61) → F82 (↑2, stacked on F80). main now d8ceda3. User: "/ai-dlc-merge로 머지하고, 머지후에 main에서 한번 돌려서 채워줘." Rebase onto d8ceda3; expected minor conflicts in pyproject.toml (F80) / settings.yaml (F82) vs main's relicense + F78.
- 2026-06-14 — **F80 merged** (9e8ae56) — intraday feature store CSV→Parquet (designed swap point) + pyarrow; rebased onto d8ceda3 clean, 23/23 store tests green.
- 2026-06-14 — **F82 merged** (2c9ddad) — intraday feature auto-collection (universe gap-backfill thread on start + EOD append, config-gated default ON); stacked on F80, rebased onto 9e8ae56 clean (F80 commit dropped as applied), 36 intraday tests green. Merge run complete (F80→F82).

## /ai-dlc-merge — F81
- 2026-06-14 — **merge run start** — triage PASS (working tree: active-track docs F76/F83/F85 noise only; no foreign/non-active). Queue scoped to **F81** per user intent (F79 also merge-awaiting but separate track, left for its own run). main 18eb146.
- 2026-06-14 — **F81 merged** (1e2b9b9) — 13F disclosed-holdings signal source: source-agnostic HoldingsProvider abstraction + SEC 13F first impl; daemon refresh→workspace/holdings/ cache, turn/universe read-only; put→SHORT direction-gate (shorting_enabled comply, F54/F60); shipped enabled:false. Rebased 1a7645e→onto 18eb146 clean (no conflicts), 40 holdings tests green, live SEC smoke re-verified. Merge run complete.

- 2026-06-14 — **F79 merged** (fbc1bae) — 모바일 PWA 실화면: WebAuthn 패스키-게이트 승인 흐름 + S1 원격 prompt 게이트 + /autostock 셸 + 리치 대시보드/상세 뷰(라이트·다크). 대시보드 실데이터·세션서명은 후속(read 엔드포인트 부재). code-review 5건 반영.

## /ai-dlc-merge — F87 (F81 follow-up)
- 2026-06-14 — **F87 merged** (c392f3d) — 13F brief bias mitigation: every-turn push brief now LONG-only + neutral framing ("ONE manager's view, NOT consensus/recommendation, independently judge"); bearish/put SHORT side moved to on-demand `disclosed_holdings` pull tool (market.py + __main__ subcommand + prompts entry). render_push_line(long-only) added, render_line(full) kept for pull. Addresses user concern that SA LP's mostly-put 13F repeated every turn anchors the agent. 45 tests green; brief/push/tools regression 18 green. Base f7b751d→c392f3d.

## /ai-dlc-merge — D1
- 2026-06-15 — **merge run start** — triage: untracked tracks F76/F85/F86(active, OK noise) + F83(abandoned, docs intentionally preserved per its row — isolated, D1 close-commit stages only tracks/D1/+shared); no foreign paths. Queue: D1 only (deprecate/D1, ↑1 bff76e1, base 1a7645e). main now b97a09e (F79/F81/F87 merged since). No file intersection with D1 → clean rebase expected.
- 2026-06-15 — **D1 merged** (628a0fc) — deprecate Tier1+2: removed dead deps (transformers/quantstats/plotly/matplotlib) + torch/scikit-learn + pre-agent ML strategies (lstm/rf/base_ml); kept feature_eng + F70 baseline. Rebased onto b97a09e clean, full suite 1329 passed (4 pre-existing unrelated). 435 deletions.

## /ai-dlc-merge — F89 (F81/F87 follow-up)
- 2026-06-16 — **F89 merged** (7d772ff) — 13F를 참조 데이터화(pull 전용): 단일 기관 자동 유니버스 편입이 자의적·단일소스 bias라는 사용자 판단 반영. SA LP provider overlay:false(유니버스 미편입) + to_prompt_text의 disclosed_holdings push 섹션 제거(매 턴 프롬프트 미주입) + render_push_line(F87) 제거. 데이터 파이프(데몬 refresh→캐시→collector→brief.disclosed_holdings)와 market.disclosed_holdings 풀 툴은 유지 → 에이전트 on-demand 참조만. 봇 매매 영향 0. 54 tests green. Base f17a36f→7d772ff.
