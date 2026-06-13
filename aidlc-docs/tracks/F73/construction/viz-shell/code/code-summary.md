# F73 viz-shell — Code Generation Summary

생성일: 2026-06-13 · 브랜치 `vibeshell` · base 5a00442 · 전부 신규 파일 (기존 코드 무변경)

## 생성 파일 ↔ 설계 대응

### 스캐폴드 (Phase 1)
| 파일 | 비고 |
|---|---|
| `viz-shell/package.json` | dev = `next dev -H 127.0.0.1 -p 3210` (BR-5, webpack 모드 — Turbopack 미사용) |
| `viz-shell/tsconfig.json` / `next.config.ts` / `postcss.config.mjs` / `.gitignore` | Next 15.5 + TS 5.9 + Tailwind v4 |
| `viz-shell/vitest.config.ts` | vitest 4 + oxc jsx automatic (tsconfig preserve 우회) |
| `viz-shell/src/app/globals.css` | 다크 단일 토큰 세트 (surface/edge/ink/up/down/accent/warn) |

### 데이터 계층 (C1·C2·C3)
| 파일 | 설계 |
|---|---|
| `src/server/paths.ts` | C1 — 읽기 화이트리스트 상수, AUTOSTOCK_ROOT override |
| `src/server/schemas.ts` | C3 — zod v4 `looseObject` 미러. **실파일 대조로 E1 수정**: snapshot은 `account.{equity,cash,invested,open_pnl}` 중첩 + `positions`는 심볼 키 dict (설계 초안의 배열/buying_power 아님) |
| `src/server/safe-read.ts` | C2 — L2a/b/c 3종 (torn-line tail, stat-stable retry, warn dedupe) |

### API (C4)
| 파일 | 설계 |
|---|---|
| `src/server/trpc.ts`, `src/server/routers/{_app,portfolio}.ts` | 4 procedure 전부 query (mutation 0 — 테스트로 강제), symbol 이중 화이트리스트 |
| `src/app/api/trpc/[trpc]/route.ts` | fetch adapter |

### 채팅 엔진 (C5)
| 파일 | 설계 |
|---|---|
| `src/server/chat/boundary.ts` | L1 checkBoundary — deny-by-default, realpath(최근접 존재 조상) 심링크 차단 |
| `src/server/chat/sanitize-env.ts` | BR-4 — 실 .env 키명 대조(2026-06-13), CLAUDE_CODE_OAUTH_TOKEN만 예외 보존, ANTHROPIC_API_KEY 제거(구독 강제) |
| `src/server/chat/session-store.ts` | BR-14 — `.cache/session.json` 원자 영속 |
| `src/server/chat/view-contract.ts` | BR-12 시스템 프롬프트 (경계 사전 고지 + 뷰 계약 + recharts/토큰) |
| `src/server/chat/claude-runner.ts` | L3 — Agent SDK 0.3 `query()` (시그니처 d.ts 실측), resume/canUseTool/sanitizeEnv/preset+append, includePartialMessages로 text-delta |
| `src/server/chat/turn-lock.ts` | BR-15 단일 in-flight (409) |
| `src/app/api/chat/route.ts` (+`reset/`) | UIMessageStream — text-start/delta/end + `data-tool-activity`/`data-boundary-denied` (BR-16), BR-17 로그 |
| `src/lib/chat-types.ts` | E6 커스텀 data part 타입 |

### 셸 UI (C6)
| 파일 | 설계 |
|---|---|
| `src/app/{layout,page}.tsx`, `src/components/providers.tsx` | 탭 + 우측 채팅(360px, 접기), 5s 폴링 기본 |
| `src/components/view-host.tsx` | L4 자동 레지스트리 — require.context + lazy(평가를 탭 내부로 지연) + 뷰 식별자 캐시(리렌더 remount 방지, HMR 시 자연 리셋) |
| `src/components/error-boundary.tsx` | 깨진 뷰 탭 단위 격리 + 복구 안내 |
| `src/components/{tab-bar,top-bar}.tsx` | 탭 ×=숨김(BR-13), 숨긴 뷰 복원 메뉴 |
| `src/components/overview/*` (5파일) | 시드 위젯 — 카드/equity curve(7·30·90d)/포지션 테이블/thesis drawer(stale ⚠️), 위젯별 fail-honest placeholder |
| `src/components/chat/chat-panel.tsx` | useChat(AI SDK v6) + ✎/⚠️ 파트 렌더, 409 안내, New chat 확인 |
| `src/lib/{view-utils,format}.ts` | 순수 로직 (테스트 대상) |
| `src/generated/_example.tsx` | BR-11 계약 모범 (탭 비노출) |

### 테스트 (9파일, 100 pass)
- `tests/server/boundary.test.ts` — **경계 거부 전수** (탈출/절대경로/심링크 파일·디렉토리/도구 deny/이벤트) — blocking 게이트 ✅
- `tests/server/safe-read.test.ts` — torn-line·skip·ENOENT + **PBT** 임의 바이트 절단 무crash (fast-check)
- `tests/server/schemas.test.ts` — 실데이터 형상 + passthrough + **PBT** 직렬화 라운드트립
- `tests/server/portfolio-router.test.ts` — **mutation 0 구조 검증**, 이중 화이트리스트, zod 경계
- `tests/server/{sanitize-env,session-store}.test.ts` — BR-4/BR-14
- `tests/ui/{view-utils,format}.test.ts`, `tests/ui/error-boundary.test.tsx` — 숨김 로직·포맷·탭 격리

## 검증 결과 (Step 7.3)
- `tsc --noEmit` ✅ · `vitest run` **100/100** ✅
- **라이브 스모크** (dev 서버 + 실데이터, AUTOSTOCK_ROOT=메인 체크아웃):
  - `/` 200, snapshot/equity/listPositions/thesis 전부 실데이터 반환, 비정상 symbol 400 ✅
  - HMR 자동 레지스트리: 파일 추가→탭 노출(1), 삭제→제거(0) SSR HTML로 실증 ✅
  - **라이브 채팅 턴**: 에이전트가 `_example.tsx` 참조 후 `hello-smoke.tsx`를 계약대로 생성 (10.4s), 스트림 이벤트(text-delta/tool-activity) 정상, **세션 resume** 2턴째 동일 id 확인 ✅
  - 경계 라이브: workspace 직접 읽기 요청 → 에이전트가 계약 인지 후 거부(tRPC 경유 제안) — 프롬프트 1차 방어 작동, 코드 2차 방어는 단위 테스트로 증명 ✅
- 스모크 산출물(hello-smoke.tsx, session.json) 정리 완료

## Security Baseline 컴플라이언스 (Code Gen 단계)
| 룰 | 판정 | 증빙 |
|---|---|---|
| SECURITY-03 로깅 | 준수 | BR-17 구조화 로그, 민감값 비기록 (claude-runner/route/boundary) |
| SECURITY-05 입력 검증 | 준수 | zod 전 procedure + symbol 이중 화이트리스트 + 경로 입력 부재 (router 테스트) |
| SECURITY-06 최소 권한 | 준수 | boundary deny-by-default + disallowedTools + sanitizeEnv (테스트) |
| SECURITY-07 네트워크 | 준수 | 127.0.0.1:3210 스크립트 하드코딩 + README 경고 |
| SECURITY-08 접근 제어 | 준수 | 쓰기 게이트 단일점 checkBoundary, mutation 0 구조 검증 |
| SECURITY-11 시큐어 설계 | 준수 | 경계=코드(canUseTool), fail-closed, 프롬프트는 보조 |
| SECURITY-15 예외 처리 | 준수 | fail-honest null/[], ErrorBoundary 탭 격리, throw 없는 reader |
| SECURITY-04 헤더 / 09 하드닝 | N/A | 로컬 루프백 단일 사용자 dev 도구 (외부 표면 없음 — README 명시) |
| SECURITY-01/02/10/12/13/14 | N/A | 저장암호화/세션관리/중간자 등 — 해당 표면 부재 |

비준수 0건 — blocking 없음.

## 설계 대비 의도적 차이 (기록)
1. **E1 스키마 실데이터 정정** (위 표) — Domain Entities 문서의 1차 추정을 실파일로 교정.
2. AccountCards: `buying_power` 부재 → Equity/Cash/Invested/Open P&L 4카드.
3. zod v3→v4 (Agent SDK peer 요구) — `.passthrough()` 대신 `z.looseObject`.
4. Next 16 대신 15.5 핀 — Turbopack 기본화로 require.context 리스크 회피.
