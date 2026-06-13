# F73 — Application Design (통합)

> 상세는 분할 문서 참조: [components.md](components.md) ·
> [component-methods.md](component-methods.md) · [services.md](services.md) ·
> [component-dependency.md](component-dependency.md)

## 설계 요약

`viz-shell/`은 단일 Next.js(App Router) 앱이며 내부 6컴포넌트로 구획된다:

| ID | 컴포넌트 | 한 줄 책임 |
|---|---|---|
| C1 | Paths | repo 경로 해석 + 읽기 대상 **화이트리스트** (임의 경로 API 부재) |
| C2 | SafeRead | 표면별 안전 읽기 — snapshot(단순)/equity(torn-line tail)/positions(stat-stable) |
| C3 | Schemas | zod 미러 (passthrough, parse-don't-validate; thesis는 opaque) |
| C4 | PortfolioRouter | 읽기 전용 tRPC — **mutation 0개가 구조적 보장** |
| C5 | ChatEngine | SDK `query()` 래퍼 + **경계 콜백(canUseTool)** + 단일 세션 관리 |
| C6 | ShellUI | 채팅 패널 + `generated/` 자동 레지스트리 + ErrorBoundary 뷰 호스트 |

핵심 구조 결정:
1. **두 플로우의 완전 분리** — 데이터 조회(S1: C6→C4→C2→fs)와 뷰 생성(S2: C6→C5→SDK
   →generated/)은 공유 상태 없음. 접점은 생성된 코드가 런타임에 C4 훅을 부르는 것뿐.
2. **경계는 코드로** — C5b `checkBoundary`가 유일한 쓰기 게이트: Write/Edit는
   `generated/` 이하만, Read류는 `viz-shell/` 이하만(workspace/ 직접 읽기 차단 =
   thesis 경유 prompt injection 벡터 차단), 기타 도구 deny. 거부는 사유와 함께 SDK
   반환 + 채팅에 ⚠️ 표시 (UAQ 결정 ②).
3. **명시적 단일 세션** — sessionId 파일 영속 + resume, "New chat" 리셋 (UAQ 결정 ①).
4. **단일 파일 프로토콜** — 에이전트는 뷰 파일 1개만 작성; require.context 자동
   레지스트리가 픽업 (2-파일 조용한 실패 모드 제거). lazy + ErrorBoundary로 깨진
   생성물 격리.
5. **데몬 무접점** — IPC 없음, 파일 스냅숏 단방향 소비. 데몬 다운 시에도 fail-honest
   렌더.

## Security Baseline 컴플라이언스 (이 단계 적용분)
| 룰 | 판정 | 근거 |
|---|---|---|
| SECURITY-05 입력 검증 | 설계 반영 | C4 전 procedure zod + symbol 화이트리스트, 임의 경로 API 부재 (C1) |
| SECURITY-06 최소 권한 | 설계 반영 | C5b 도구/경로 allowlist, sanitizeEnv 토큰 제거 |
| SECURITY-07 네트워크 | 설계 반영 | dev 서버 127.0.0.1 바인딩 (Code Gen에서 스크립트 고정) |
| SECURITY-08 접근 제어 | 설계 반영 | 쓰기 게이트 단일점(checkBoundary) + mutation 부재 |
| SECURITY-11 시큐어 설계 | 설계 반영 | 경계를 프롬프트가 아닌 콜백 코드로 강제, fail-closed deny |
| SECURITY-15 예외 처리 | 설계 반영 | fail-honest null 반환, ErrorBoundary 격리, deny-by-default |
| SECURITY-01/02/04/09/10/12/13/14 | N/A 또는 후속 단계 | 저장소 암호화·중간자 로깅 등은 로컬 단일 사용자 dev 도구 특성상 N/A; 03(로깅)·04(헤더)·09(하드닝)는 Code Gen에서 구현 수준 점검 |

## 미결(다음 단계로 이월)
- **Functional Design**: 대시보드 레이아웃·채팅 패널 UX 상세, 생성 뷰 명명/메타 규약,
  `_example.tsx` 내용, 시드 기본 뷰 구성, 시스템 프롬프트 전문.
- **Code Generation**: require.context의 Turbopack 호환 확인(비호환 시 webpack 모드
  고정), SDK `canUseTool` 시그니처 실버전 대조, 포트 번호(가안 3210).
