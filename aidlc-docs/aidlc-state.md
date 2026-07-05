# AI-DLC State Tracking

> **Concurrent multi-track partition.** This root file is the **Track Registry** (the table
> below) — nothing else. Every track keeps its full state + audit in
> `aidlc-docs/tracks/<id>/{state.md,audit.md}` (single writer per track) — see
> `.aidlc-rule-details/common/concurrent-tracks.md`. **Do not add per-track detail here**; the
> only edits to this file are Registry rows (at track create / merge / close). Pre-partition
> history (F1–F8 + genesis refactor R0) was migrated into the per-track files on 2026-06-04.

## Track Registry
| ID | Title | Status | Branch | Worktree | Submodule branch | Base | Updated |
|----|-------|--------|--------|----------|------------------|------|---------|
| R0 | Genesis structural refactor (S-5/S-3/S-1+S-2/S-4 → U1–U7) | merged | — | — | — | — | 2026-05-28 |
| F1 | Dynamic Intraday Pattern Detection | merged | — | — | — | — | 2026-05-28 |
| F2 | Human-Steering Console (agent mode) | abandoned | feat/human-steering-console | — | — | — | 2026-05-30 |
| F3 | Intraday Loop Redesign | merged | feat/intraday-redesign | — | — | 95f94d1 | 2026-05-30 |
| F4 | Claude-Code-native Steering Console | merged | — | — | feat/* | 1719fcf | 2026-05-30 |
| F5 | Console-native Launcher & Rebrand | merged | — | — | merged→origin | aaf01e2 | 2026-05-30 |
| F6 | Console Sidebar Upgrade | abandoned | feat/console-sidebar-upgrade (deleted) | — | — | — | 2026-06-04 |
| F7 | Trading-native home copy | merged | — | — | merged→main | 631ec6e | 2026-05-31 |
| F8 | Console Sidebar Status Rich | merged | feat/console-sidebar-status-rich | — | merged→fork main 2ac0cda | 77d5ed9 | 2026-05-31 |
| R1 | New-surface refactor review | abandoned | (never branched) | — | — | — | 2026-06-04 |
| M1 | AI-DLC multi-track customization | complete | main (rules/docs) | — | — | 631ec6e | 2026-06-07 |
| F9 | Alpaca-format console orders (limit/stop/TIF) via risk gate | merged | feat/F9 | — | — (parent-repo only; opencode perm keys = follow-up) | e8d99a6→8948e24 | 2026-05-31 |
| F10 | Containerized verification harness (zero prod impact) | merged | feat/docker-verify | — | — | 8ff59c0 | 2026-05-31 |
| F11 | Verify-harness ergonomics (clean worktree + reuse main .env.test) | merged | feat/verify-ergonomics | — | — | 24dc367 | 2026-05-31 |
| F12 | Verify-harness hardening (critic: account pin + fail-closed preflight) | merged | feat/verify-hardening | — | — | 715723e | 2026-05-31 |
| F13 | Sidebar fills date + blank line between sections | merged | feat/F13 | — | merged→fork main aa984da | a7a9ea1 | 2026-05-31 |
| F14 | Daemon wedge self-heal + WakeDetector market-data fetch rigidity | merged | feat/F14 | — | — | d899f83 | 2026-05-31 |
| F15 | docker-verify `attach` mode (full daemon+TUI runtime, TEST account) | merged | feat/F15 | — | — | 98090fa | 2026-05-31 |
| F16 | Broker API adapter — trade the sandbox account farm | merged | feat/F16 → main cd863a0 | — | — (monorepo, post-F35) | cc125e5→rebased 2253029→cd863a0 | 2026-06-03 |
| F17 | docker-verify cleanup — sudo-free teardown (ownership handback) | merged | feat/F17 | — | — | f912999 | 2026-05-31 |
| F18 | docker-verify attach console-MCP env wiring (AUTOSTOCK_ROOT + shared token) | merged | feat/F18 | — | — | 6902612→8f5468c | 2026-05-31 |
| F19 | F9 follow-up: 6 structured-tool opencode permission keys in fork config | merged | feat/F19 | — | merged→fork main bc82b71 | 2f13a7a→a1851e0 | 2026-05-31 |
| F20 | Alpaca-shaped read tools (arbitrary-symbol quote/orders) — fix console read limit | merged | feat/F20 | .claude/worktrees/F20 | feat/F20 (opencode perm keys) | 79df84a→093f11e | 2026-05-31 |
| F21 | Synchronous MCP arg validation (3-layer: zod .refine() → degenerate check → daemon defense-in-depth) | merged | feat/F21 | .claude/worktrees/F21 | — (parent repo: mcp-server.ts + commands.py) | 79df84a→0ed7044→merge | 2026-05-31 |
| F22 | AI 협업 TUI 개선 — AI(research/intraday) 협업 특화 UI/UX | merged | feat/F22 | .claude/worktrees/F22 | feat/F22 | 620eeac→5968d9b→ab6e742 | 2026-06-01 |
| F23 | Multi-Agent Research 교차검증 + 시그널 확장 | merged | feat/F23 | .claude/worktrees/F23 | — | 620eeac→77d7f9e→927627a | 2026-06-01 |
| F24 | Decision Quality Metrics — 에이전트 결정 품질 정량 분석 | merged | feat/F24 | — | — | e0a345b→b4fa955 | 2026-06-01 |
| F25 | 타임라인 바 개선 — market-aware timeline + date nav + human markers | merged | feat/F25 | .claude/worktrees/F25 | feat/F25 → main 4c21687 | 437d57d→02f46cb | 2026-06-01 |
| F26 | Supervisor mode — permission profiles + launcher --supervisor + docker-verify support | merged | feat/F26 | .claude/worktrees/F26 | feat/F26 → main 674bdb5 (opencode) | 572db79→bb2da2d | 2026-06-01 |
| F27 | docker-verify 하네스 non-root 실행 — root-소유 파일 근본 제거 + 우회 코드 정리 | merged | feat/F27 | — | — (parent repo: Dockerfile.verify/compose/verify.sh/verify-run.sh/worktree-setup.sh) | 46c48a9→a22952f | 2026-06-01 |
| F29 | Supervisor-mode codebase orientation — steer_read{command:/codebase} 프로젝트 트리 | merged | feat/F29 | .claude/worktrees/F29 | — (parent repo only; gitlink updated to match main) | bb2da2d→55581d6→merge | 2026-06-02 |
| R2 | Speed/throughput review — behavior-preserving (×3 engine, ×5.6 optimizer, parallel fetch) | merged | feat/R2 | — | — | 46c48a9→dfb8200 | 2026-06-01 |
| F28 | Normal-mode UI self-explanation — steer_read{command:/ui-legend} 정적 TUI 사전(21엔트리, 의미만) | merged | feat/F28 | .claude/worktrees/F28 | feat/F28 → fork main b26a930 | a4b1732→d1f72e6→02d6a41 | 2026-06-03 |
| F30 | KIS OpenAPI 브로커 확장 — 한국주식 페이퍼트레이딩 (KIS 단독 PoC) | merged | feat/F30 → main 1609182 | — | — (monorepo, post-F35) | 2253029→1609182 | 2026-06-05 |
| F31 | TUI Sidebar Orders 색상 깜박임 버그 수정 | merged | feat/F31 | — | feat/F31 (opencode) | 1746d6a→TBD | 2026-06-02 |
| F32 | Timeline Markers 사라짐 버그 수정 | merged | feat/F32 | — | — | a3e67ee | 2026-06-02 |
| F33 | 멀티브로커 동시 운영 — Alpaca(US) + KIS(KR) (F30 후속) | active (paused) | feat/F33 (TBD) | .claude/worktrees/F33 (TBD) | — | TBD | 2026-06-02 |
| F34 | 타임라인 라벨(OPEN/PRE/AFT) z-order 수정 — 라벨을 마커 위로, 가려진 마커도 클릭 유지 | merged | feat/F34 | .claude/worktrees/F34 | feat/F34 → fork main 43423df | 378a98b→a366545 / 66c6edc→43423df | 2026-06-02 |
| F35 | CLI 서브모듈을 autostock 단일 repo로 통합 (de-submodule / monorepo) | merged | feat/F35 → main 2253029 | — | — (서브모듈 제거 완료) | 0f26b48→1ac4879 | 2026-06-03 |
| F36 | 타임라인 과거날짜 마커 클릭 시 'Turn not found' — 오버레이가 라이브 monitor만 조회(과거 세션 미조회) + 마커 깜박임 | merged | feat/F36 → main cb8c9ad | — | N/A (monorepo, F35 이후) | 2253029→e15dd5c→cb8c9ad | 2026-06-03 |
| F37 | `.env` 키 네이밍 정합화 — `ALPACA_SECRET_KEY` → `ALPACA_API_SECRET` | merged | feat/F37 → main f26ab6a | — | N/A (monorepo) | 1553dc0→fd5cd5b→f26ab6a | 2026-06-03 |
| F38 | 운영자 수동 turn 트리거 steering 명령 (research turn 등 on-demand 실행) | merged | feat/F38 → main c395faf | — | — (monorepo) | b0b1275→rebased 7766c6a→c395faf | 2026-06-03 |
| F39 | Normal 모드 코드 질문 차단 — supervisor 아닐 때 소스/내부 구현 질문 거부 (운영 질문은 steering 데이터로 응답) | merged | feat/F39 → main f6569ea | — | — (monorepo) | 72aba01→rebased c49e4fd→f6569ea | 2026-06-03 |
| F40 | autostock 런처 `-h`/`--help` 핸들러 — `--supervisor` 등 런처 고유 옵션 노출 + opencode help loose-fuse | merged | feat/F40 → main 65e65ab | — | — (monorepo) | 72aba01→2a17322→65e65ab | 2026-06-03 |
| F41 | Research turn 마커 오버레이 정보 강화 (multi-agent 평가 노출 + summary 버그 수정) | merged | feat/F41 → main f330370 | — | — (monorepo) | 72aba01→rebased 7c62527→f330370 | 2026-06-03 |
| F42 | F37 리네임 누락 핫픽스 — main.py + scripts의 `alpaca_secret_key` 잔여 참조 제거 (데몬 startup 크래시) | merged | feat/F42 → main b0b1275 | — (제거됨) | — (monorepo) | 72aba01 | 2026-06-03 |
| F43 | 데몬 코드 버전 스큐 자가치유 — autostock 런처가 구버전 데몬(snapshot SHA≠작업트리 HEAD) 감지해 자동 재시작 | merged | feat/F43 → main b0ed183 | — (제거됨) | — (monorepo) | 777cf40 | 2026-06-03 |
| F44 | 진행 중 turn 라벨(TUI) + 동일 type turn이 in-flight면 큐잉 대신 "already in progress" 반환 | merged | feat/F44 → main dc73fcb | — (제거됨) | — (monorepo) | bc25f93 | 2026-06-03 |
| F45 | 타임라인 12h 윈도우 자동 전환(현재시각 포함) + [<]/[>] 12h 네비 (현행 정규장-중심 ±1일 → 로컬 12h 절반) | merged | feat/F45 → main 007aa11 | — (제거됨) | — (monorepo) | 777cf40 | 2026-06-03 |
| F46 | 에이전트 `account` 툴 작동불가 — 스폰된 에이전트의 `python3`에 alpaca-py 없음 (PATH 구멍) | merged | feat/F46 → main fb06517 | — (제거됨) | — (monorepo) | 777cf40 | 2026-06-03 |
| F47 | 급등주 히스토리 기록 및 원인 분석 (Surge Stock History & Root-Cause Analysis) | merged | feat/F47 (3eee516) | — (제거됨) | — (monorepo) | 3eee516 | 2026-06-03 |
| F48 | Operator Console Sidebar Cleanup — 브랜딩/불필요 요소 제거 | merged | feat/F48 (a669761) | — (제거됨) | — (monorepo) | a669761 | 2026-06-03 |
| F49 | synthesis final verdict TUI display bug fix (깨져서 나오는 현상 수정) | merged | feat/F49 (00b3559) | — (제거됨) | — (monorepo) | 00b3559 | 2026-06-03 |
| F50 | TUI Status/타임라인 동일선 배치 | merged | feat/F50 (3f3b725) | — (제거됨) | — (monorepo) | 3f3b725 | 2026-06-03 |
| F51 | 장초반 시그널 기록 및 분석 (Early-Session Signal Detection & Analysis) | merged | feat/F51 → main faec7b7 | — (제거됨) | — (monorepo) | faec7b7 | 2026-06-04 |
| F52 | Research Turn SELL 결정 미실행 근본 원인 분석 + Execution Audit Trail Fix | merged | feat/F52 → main 4e64781 | — (제거됨) | — (monorepo) | 4e64781 | 2026-06-04 |
| F53 | MCP Position Thesis 노출 — TUI에서 agent position thesis 확인 | merged | feat/F53 (621b227) | — (제거됨) | — (monorepo) | a8957ad→621b227 | 2026-06-04 |
| F54 | 숏 포지션 기능 — 시장 균형에 맞춘 숏 매매 + 숏 분석 지원 | merged | feat/F54 → main 5cd2eb4 | — (제거됨) | — (monorepo) | a8957ad→5cd2eb4 | 2026-06-04 |
| F55 | 타임라인에 "데이마켓" 세션 표기 추가 (pre/regular/after 외 누락 세션) | merged | feat/F55 → main 5c9166d | — (제거됨) | — (monorepo) | 6bf1b31→c6df7ba→5c9166d | 2026-06-04 |
| F56 | code-review 후속 버그 수정 — surge prev_close / early-session ET·finalize·retention / executor cursor stall | merged | feat/F56 → main 6b043c6 | — (제거됨) | — (monorepo) | 6bf1b31→6b043c6 | 2026-06-04 |
| F57 | 상단 status + 날짜 nav 바 두줄 깨짐 + research 경과시간 미갱신 버그 수정 (NavRow) | merged | feat/F57 → main f53c4a5 | — (제거됨) | — (monorepo) | 6bf1b31→7eb6ae7→f53c4a5 | 2026-06-04 |
| F58 | 과거 날짜/타임라인 구간 상단바에 턴 토큰사용량(또는 비용) 표시 | merged | feat/F58 → main 0e071e1 | — (제거됨) | — (monorepo) | 03de978→4f9a79f→0e071e1 | 2026-06-04 |
| F59 | 운영자 `/short`·`/cover` shorthand — F54 숏 후속 (verb 대칭 + footgun 해소) | merged | feat/F59 | — | — (opencode fork: parser/schema) | d988a65→88f6edf | 2026-06-04 |
| F60 | 숏 안전 제어 — ETB 게이트 + 마스터 on/off 토글(shorting_enabled, 기본 OFF) (F59 위 분기) | merged | feat/F60 | — | — (parent-repo Python) | d988a65→b4e41be | 2026-06-04 |
| F61 | 리서치 턴 주식 시그널 강화 — 시장 무버/뉴스 catalyst 포착 + 종목 간 read-through 전파 | merged | feat/F61 → main 1437d44 | .claude/worktrees/F61 (제거됨) | — (parent-repo Python) | e8b112b→1437d44 | 2026-06-05 |
| F62 | 귀속/효능 기반 — 레슨/프롬프트버전→결정→결과 링크 + 효능 스코어 (자가학습 에픽 U0) | merged | feat/F62 → main 9342691 | — | — (monorepo) | 43b26d7→9342691 | 2026-06-06 |
| F63 | Health Check Loop — AI-driven 시스템 모니터링 (9차원) | merged | feat/F63 → main 58e1dda | — | — (monorepo) | b89735d→58e1dda | 2026-06-06 |
| F65 | 하이브리드 회상 — 상황 기반 레슨 회상 (태그 사전필터+LLM 재랭크), F62 위 분기 | merged | feat/F65 → main 89927c7 | — | — (monorepo) | 43b26d7→89927c7 | 2026-06-06 |
| F64 | 헌장 경계 자가재작성 — 불변 헌장 안에서 가이던스 프롬프트 자동 진화, F65 위 분기 | merged | feat/F64 → main a383f8d | — | — (monorepo) | 43b26d7→a383f8d | 2026-06-06 |
| F66 | Health Check 발견 이슈 수정 — LLM provider 정합성 + circuit breaker 키 | merged | feat/F66 → main fff3d9e | — | — (monorepo) | f17d595→fff3d9e | 2026-06-06 |
| F67 | 자가학습 스택 code-review 핫픽스 — efficacy ts AttributeError + stamp 인덱스 + 캐시 원자성 + regime 매칭 + 프롬프트 조립 일반화 | merged | feat/F67 → main 4f2b1b2 | — | — (monorepo) | f17d595→4f2b1b2 | 2026-06-06 |
| F68 | F67 follow-up — 자가학습 스택 정리: rollback-rewrite 순서(#7) + collect_outcomes EOD 캐시(#8) + is_meaningful 제거/임계 단일화(#10) | merged | feat/F68 → main 9eaf8a0 | — | — (monorepo) | 58ca6a7→9eaf8a0 | 2026-06-06 |
| F69 | Health Check TUI 통합 — 데몬 발행(steering/health.json) + TUI 글리프/오버레이 (F63 후속) | merged | feat/F69 → main a0025b3 | — | — (monorepo) | ec2875c | 2026-06-07 |
| R3 | Alpaca-shaped broker dedup — extract AlpacaShapedBroker base (alpaca_broker + broker_api_broker) | merged | feat/R3 → main cfd34b0 | — | — (monorepo) | ec2875c | 2026-06-07 |
| R4 | JSONL record read/write helper (src/core/jsonl.py) de-dup | merged | refactor/R4 → main f43366f | — | — (monorepo) | 9e9aec2 | 2026-06-07 |
| R5 | `claude -p` headless runner — investigate shared JSON-envelope parser | abandoned (won't-do, Stage 0) | (never branched) | — | — (monorepo) | ec2875c | 2026-06-07 |
| R6 | ET (market timezone) helper consolidation into core | merged | refactor/R6 → main 230f74d | — | — (monorepo) | 5e5c2a9 | 2026-06-07 |
| R7 | Broker behavior fixes (broker_api short-side bug + fail-closed TIF) — deferred from R3 T3 gate | merged | refactor/R7 → main 3dde03c | — | — (monorepo) | c9669ec→3dde03c | 2026-06-08 |
| F70 | 섀도우 벤치마크 + alpha-vs-baseline — 결정론적 전략(기술적/buy&hold)을 LLM 경쟁자 아닌 측정자로 상시 가동 | merged | feat/F70 → main e4676fc | — | — (monorepo) | 5e786b0 | 2026-06-07 |
| R8 | `src/agent/` 재구조화 — grab-bag 15파일을 logs/·learning/ 서브패키지로 + stutter 해소 (구조점검 #1) | merged | refactor/R8 → main d065ed6 | — | — (monorepo) | 76ff7b6 | 2026-06-12 |
| R9 | config↔settings 용어 통일 — 패키지 로컬 설정 모듈을 settings.py로 (구조점검 #3) | merged | refactor/R9 → main c3c0137 | — | — (monorepo) | 3297de5 | 2026-06-11 |
| R10 | intraday 일원화 — `data/intraday_*.py` → `data/intraday/` 서브패키지 (구조점검 #4) | merged | refactor/R10 → main 2245def | — | — (monorepo) | 0106a8b | 2026-06-11 |
| R11 | strategy 네이밍 일관화 — `_strategy` 접미사 제거 + `llm_strategy` stutter 해소 (구조점검 #5) | merged | refactor/R11 → main 37fc0b2 | — | — (monorepo) | 3297de5 | 2026-06-11 |
| R12 | execution/brokers 네이밍 — `account_farm_broker` 개명 + `simulated_broker` 통일 + `kis/` 서브패키지 (구조점검 #6) | merged | refactor/R12 → main 018c59e | — | — (monorepo) | 0106a8b | 2026-06-11 |
| R13 | tests 네이밍·구조 정비 — 트랙ID 테스트명→행동기반 + `src/` 미러링 (구조점검 #2+#7) | merged | feat/R13 → main 401d1de | — | — (monorepo) | 2a4e02f | 2026-06-13 |
| F71 | autostock 모바일(안드로이드) 앱 — 경로 A (Tailscale + opencode serve + PWA, 대화형 operator) | merged | feat/F71 → main fdfc041 | — | — (monorepo) | 76ff7b6 | 2026-06-12 |
| F72 | research 스크리닝→필터링 결과 로깅 + TUI(steer_read) 노출 | merged | feat/F72 → main 7b4b409 | — | — (monorepo) | 76ff7b6 | 2026-06-12 |
| F73 | viz-shell — 읽기 전용 생성형 대시보드 사이드카 (vibeOS 패턴 방향 A, 장기 브랜치 **do-not-enqueue**: 사용자 안정 선언 시에만 머지) | active | vibeshell (사용자 지정) | .claude/worktrees/F73 | — (신규 viz-shell/) | 5a00442 | 2026-06-13 |
| F74 | Prompt Eval & Regression Framework — promptfoo 기반 합성 시나리오 행동 채점/회귀 게이트 | merged | feat/F74 → main 962b2e1 | — | — (monorepo) | 76ff7b6 | 2026-06-13 |
| F75 | F71 후속 — WebAuthn 게이트 토폴로지 검증·강화 (code-review 5건: 우회/fail-open/챌린지/타이밍/등록통제) | merged | feat/F75 → main 25bcb28 | — | — (monorepo) | cf9869b | 2026-06-13 |
| F76 | thesis torn-read 완화 (filedrop stat-stable read) + write_position 원자화 — lean bugfix (F73 critic 파생) | merged | feat/F76 → main 366a6a8 | — (제거됨) | — (monorepo) | 23212f5→rebased 5c47f46→366a6a8 | 2026-06-22 |
| F77 | StockTwits 리테일 sentiment 신호 — 자가 라벨(Bull/Bear) 집계, 유니버스 스윕+브리프 공급 (F61 소스) | merged | feat/F77 → main e06368e | — | — (monorepo) | bacd341 | 2026-06-13 |
| F78 | 이벤트-레이더 (Tier1, 인지) — Finnhub IPO 캘린더 소스 + brief 'Imminent IPOs/catalysts' 섹션 + Regime nudge (F61 소스) | merged | feat/F78 → main 1d3330c | — (제거됨) | — (monorepo) | 01ced61→1d3330c | 2026-06-13 |
| F79 | 모바일 PWA 실화면(SolidJS 뷰) 완성 — 홈 대시보드 + WebAuthn confirm 시트 배선 + /autostock 셸 (F71/F75 후속; 대시보드 실데이터·세션서명 후속) | merged | feat/F79 → main fbc1bae | — | — (monorepo) | fbc1bae | 2026-06-14 |
| F80 | JSONL/CSV → Parquet 저장 후보 평가 및 전환 (intraday CSV store가 designed swap point) | merged | feat/F80 → main 9e8ae56 | — | — (monorepo) | 01ced61→rebased d8ceda3 | 2026-06-14 |
| F81 | 13F 보유종목 시그널 소스 — Situational Awareness LP(Aschenbrenner) 등 기관 13F를 주기적으로 따와 리서치 브리프에 공급 (F61 소스) | merged | feat/F81 → main 1e2b9b9 | — | — (monorepo) | 1a7645e→1e2b9b9 | 2026-06-14 |
| F82 | Intraday 피처 자동 수집 — 유니버스 갭 백필 + 매 장마감 EOD append (F80 위 스택, intraday store 채우기) | merged | feat/F82 → main 2c9ddad | — | — (monorepo) | dd3c784→rebased 9e8ae56 | 2026-06-14 |
| F83 | 공유 산출물 카탈로그 (SSOT) — 데몬 산출물 공통 read 게이트 | abandoned (critic: 명분 약화 — torn-read 거짓(producer atomic), 실질 TUI 1소비자, 원문제 우회. viz-shell 지표 직접 추가 우선. 설계 문서 보존, 재개 가능) | (never branched) | — | — (monorepo) | d8ceda3 | 2026-06-14 |
| F84 | 모바일 PWA 차트 — Lightweight Charts(+@dschz/solid-lightweight-charts)로 포지션 시세 + 자산 곡선 + 결정 마커 (F79 위 추가형·스택, 단독 머지 불가) | active | feat/F84 (TBD) | .claude/worktrees/F84 (TBD) | — (monorepo) | F79(3cbf2b4) 스택 | 2026-06-14 |
| F85 | Aggressiveness 노브 — 한 개 운영자 다이얼로 매매 공격성 조절 (프롬프트 + 리스크 게이트 + 학습 horizon 동시 구동) | merged | feat/F85 → main 207b8be | — | — (monorepo) | f17a36f→rebased 57f7f82 | 2026-06-16 |
| D1 | 죽은 의존성(transformers/quantstats/plotly/matplotlib/torch/sklearn) + 사전 ML 전략(lstm/rf/base_ml) 폐기 — feature_eng 보존, F70 baseline 경계 (Tier1+2) | merged | deprecate/D1 → main 628a0fc | — | — (monorepo) | 1a7645e→rebased b97a09e | 2026-06-15 |
| F86 | 모바일 대시보드 데이터 엔드포인트 — opencode serve에 autostock read 라우트 추가, 데몬 steering 산출물을 PWA 대시보드에 실데이터 공급 (F79 후속; F84 차트 의존) | merged | feat/F86 → main f3fef72 | — | — (monorepo) | f7b751d→rebased 622bb80 | 2026-06-16 |
| F87 | 13F 브리프 bias 완화 — 숏/풋 방향을 매 턴 push 프롬프트에서 제거하고 on-demand pull 툴로만 노출 (F81 후속) | merged | feat/F87 → main c392f3d | — | — (monorepo) | f7b751d→c392f3d | 2026-06-14 |
| F88 | Agent self-authored long-horizon triggers — agent가 macro/news 조건을 Python predicate로 직접 작성, Docker 샌드박스(src 미마운트/net off) 평가, brokered 데이터 주입, daemon-호스팅 MCP authoring, fire→self-wake | merged | feat/F88 → main a942390 | — (제거됨) | — (monorepo) | 57f7f82→rebased 1f594cc→a942390 | 2026-06-22 |
| F89 | 13F를 참조 데이터화(pull 전용) — 유니버스 자동 편입 OFF + push 브리프 제거, disclosed_holdings 툴로만 (F81/F87 후속) | merged | feat/F89 → main 7d772ff | — | — (monorepo) | f17a36f→7d772ff | 2026-06-16 |
| F90 | Docker prod화 — verify 하네스(F10/F15 attach) 패턴으로 다중 인스턴스 동시 운영(계정·workspace·aggressiveness 분리) + 손쉬운 attach (F85/F16 위) | merged | feat/F90 → main c3b60d6 | — (제거됨) | — (monorepo) | 23212f5→rebased b08e6e0→c3b60d6 | 2026-06-23 |
| F91 | sentiment sweep 영속화 클럭 정합 핫픽스 — `_sweep`가 주입 클럭을 `append_sweep(ts=)`로 스레딩(ET-midnight torn-partition 차단). F88 Build & Test에서 분리된 무관 실패 3건 | merged | feat/F91 → main 5591eca | — (제거됨) | — (monorepo) | 1b5eb40→rebased 1805ae3→5591eca | 2026-06-22 |
| F92 | 브로커 provider 정합성 버그 수정 + 멀티 인스턴스 격리 복구 — agent broker-truth CLI 3곳(tools/__main__.py:_broker, logs/equity.py:main, scripts/status.py)이 provider 무시하고 AlpacaBroker 하드코딩 → 공유 Alpaca 계좌 읽음. create_broker 공유 팩토리 추출 + 격리 전수점검 + prod-run.sh reconcile 헬퍼 | merged | feat/F92 → main 8181f5c | — (monorepo) | 42d0398→rebased e933904→8181f5c | 2026-06-28 |
| F93 | 모바일 실행 경로 배선 fix — autostock API 라우트(webauthn+dashboard)를 실제 리스너에 마운트(R1 블로커: 와이어 너머 /autostock/* → SPA HTML) + serve가 .env WEBAUTHN_ORIGIN 전달(R2) + QR https origin(R3) + 단일 origin runbook(R4) | merged | feat/F93 → main 3ef2670 | — (제거됨) | — (monorepo) | 42d0398→rebased 42770f4→3ef2670 | 2026-06-29 |
| F94 | 콘솔 계좌-truth 읽기 툴 provider 정합성 (F92 TS판 후속) — operator-console mcp-server.ts의 getAccountInfo/getAllPositions/getOpenPosition/getPortfolioHistory/getOrders가 alpaca-data.ts로 Alpaca 직결 → account_farm 인스턴스가 공유 Alpaca 계좌(RTX/TMO) 읽음. account_farm일 때 데몬 snapshot 경유로 수정 | active | feat/F94 | .claude/worktrees/F94 | — (monorepo) | 940a99e | 2026-06-29 |

> Status: `active` / `merged` / `abandoned`. Edit a row only at track **create** / **merge/close**
> (the only cross-track writes — serialize with `git pull --rebase`). Per-track files under
> `tracks/<id>/state.md` are authoritative for each track's detail and status; the historical
> F1–F8 + R0 rows were reconstructed at migration time and may be approximate.
