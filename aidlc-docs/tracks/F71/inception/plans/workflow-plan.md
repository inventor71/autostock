# F71 — Workflow Plan

> User Stories(US-1~8) 승인 후 작성. 승인 게이트 전 다음 단계 진행 금지.

## 실행 단계 결정

```text
INCEPTION
  [x] Workspace Detection ........ 완료 (brownfield, codekb)
  [x] Requirements Analysis ...... 완료 (FR-1~10, 승인)
  [x] User Stories ............... 완료 (P1, US-1~8 + AC, 승인)
  [→] Workflow Planning .......... 현재 (ALWAYS)
  [ ] Application Design ......... EXECUTE (Standard) — **첫 작업 = US-8 feasibility**
  [ ] Units Generation ........... EXECUTE — 3 유닛 분해 (아래)

CONSTRUCTION  (유닛별 루프; U1 → U2 → U3 순)
  U1 server-runtime  : Functional SKIP / NFR 경량 / Infra SKIP / Code+Test
  U2 security-gate   : Functional EXECUTE / NFR EXECUTE(보안 핵심) / Infra SKIP / Code+Test
  U3 pwa-client      : Functional EXECUTE(화면·플로우) / NFR 경량 / Infra SKIP / Code+Test
  [ ] Build & Test ............... ALWAYS (+ post-merge-guide — user-facing)
```

## 단계 근거

| 단계 | 결정 | 근거 |
|------|------|------|
| Application Design | **EXECUTE (Standard)** | 신규 컴포넌트 다수(serve 진입점/WebAuthn 게이트/PWA 패널) + **US-8 feasibility 검증**(serve↔TUI 세션 저장소 공유)이 유닛 경계를 좌우 |
| Units Generation | **EXECUTE** | 단일 유닛으로 보기엔 큼 — 런타임(TS/launcher+systemd), 보안 게이트(서버+MCP), PWA(SolidJS)가 서로 다른 기술·검증 경로. 순차 3유닛이 안전 |
| U1 Functional | SKIP | 신규 데이터 모델 없음(기동/wiring/QR 표시) |
| U2 Functional+NFR | EXECUTE | WebAuthn 등록·검증 플로우 + 뮤테이팅 분류 규칙 = 신규 설계 + Security Baseline 핵심 |
| U3 Functional | EXECUTE | 홈 대시보드/트레이스/페어링 화면 플로우 + fallback UI(US-8) |
| Infra Design | SKIP (전 유닛) | 클라우드 리소스 없음. systemd 유닛은 U1 코드 산출물로 취급 |

## 유닛 분해 (Units Generation 선반영 — 승인 시 확정)

| 유닛 | 내용 | 주요 스토리 |
|------|------|------------|
| **U1 server-runtime** | `autostock serve` 서브커맨드(launcher) — TUI와 동일 MCP/STEERING wiring으로 `opencode serve` 기동 + systemd --user 유닛 + QR(URL+비번) 표시 | US-1(서버측), US-6 |
| **U2 security-gate** | WebAuthn 패스키 등록/검증(서버측 라우트) + 뮤테이팅 MCP 도구 서버측 강제(서명 없으면 거부) + 권한 프로파일 안전 기본값 | US-5, US-7 |
| **U3 pwa-client** | `packages/app` 확장 — 홈 대시보드 패널, 트레이스 뷰어, QR 스캔 페어링, WebAuthn confirm UX, 오프라인 표시, (US-8 결과에 따라) 세션 이어보기 or fallback UI | US-1~4, US-7, US-8 |

의존: U2는 U1의 serve 위에, U3는 U1+U2의 API 위에. **U1→U2→U3 순차**.

## US-8 feasibility — Application Design 첫 작업

serve와 TUI가 같은 프로젝트 디렉토리의 세션 저장소(storage/db)를 공유하는지 코드로 검증:
- 공유 ⇒ US-8 구현(세션 목록/열람/이어가기)을 U3에 포함.
- 비공유/위험(동시 접근) ⇒ fallback 확정 + 사용자 보고(US-8 AC3).

## Merge Risk 예고

- `operator-console/` 전반(launcher+cli packages) — **opencode fork 영역**. 다른 활성 트랙과
  겹침 현재 없음(F33 paused). monorepo라 서브모듈 경계 이슈는 없음(post-F35).
- 데몬측 변경 최소(steering 읽기 재사용) — Python 충돌 위험 낮음.

## 산출물 위치

- Application Design → `inception/application-design/` (feasibility 결과 포함)
- Units → `construction/{u1-server-runtime,u2-security-gate,u3-pwa-client}/`
- 코드 → worktree `.claude/worktrees/F71` (feat/F71) — Code Gen 전 생성(게이트)
