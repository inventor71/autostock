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
| M1 | AI-DLC multi-track customization | active | main (rules/docs) | — | — | 631ec6e | 2026-05-31 |
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
| F30 | KIS OpenAPI 브로커 확장 — 한국주식 페이퍼트레이딩 (KIS 단독 PoC) | active | feat/F30 | .claude/worktrees/F30 | — (monorepo, post-F35) | 2253029 | 2026-06-03 |
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
| F62 | 귀속/효능 기반 — 레슨/프롬프트버전→결정→결과 링크 + 효능 스코어 (자가학습 에픽 U0) | active | feat/F62 (TBD) | .claude/worktrees/F62 (TBD) | — (monorepo) | e8b112b | 2026-06-05 |
| F65 | 하이브리드 회상 — 상황 기반 레슨 회상 (태그 사전필터+LLM 재랭크), F62 위 분기 | active (paused) | feat/F65 (TBD) | .claude/worktrees/F65 (TBD) | — (monorepo) | F62 merge (TBD) | 2026-06-05 |
| F64 | 헌장 경계 자가재작성 — 불변 헌장 안에서 가이던스 프롬프트 자동 진화, F65 위 분기 | active (paused) | feat/F64 (TBD) | .claude/worktrees/F64 (TBD) | — (monorepo) | F65 merge (TBD) | 2026-06-05 |

> Status: `active` / `merged` / `abandoned`. Edit a row only at track **create** / **merge/close**
> (the only cross-track writes — serialize with `git pull --rebase`). Per-track files under
> `tracks/<id>/state.md` are authoritative for each track's detail and status; the historical
> F1–F8 + R0 rows were reconstructed at migration time and may be approximate.
