# F79 Application Design (consolidated)

> 모바일 PWA 실화면 완성. 본 문서는 components.md / component-methods.md / services.md /
> component-dependency.md를 한곳에 요약한다. 상세 비즈니스 규칙은 Construction의 Functional
> Design에서.

## 설계 목표 & 해소한 통합 공백 (요구사항 단계 지적분)
1. **WebAuthn 헤더 주입 경로 (FR-3 블로커) — 해소**: SDK(`@hey-api/openapi-ts`)는 per-call
   `headers` 옵션(`sdk/.../core/types.gen.ts:37`) + request 인터셉터(`sdk/.../client.ts:54` 기존
   사용) 지원. → **per-call headers** 방식의 단일 관문 `SignedMutationGateway(C3)` 채택.
2. **대시보드 스냅샷 출처 — 해소**: 서버 신규 엔드포인트 대신 **클라이언트 조립**
   (`SnapshotController(C2)` → 기존 `toDashboard`). 부분/누락 never-throw 활용.
3. **세션 입력 경계 (FR-4) — 결정**: "입력 허용 + WebAuthn 게이트". 결과로 **서버 게이트 S1
   확장**(원격 `session.prompt` 서명 강제)이 신규 in-scope가 됨. ⚠️ 승인 게이트에서 확인 대상.
4. **자동잠금 범위 (NFR-6) — 결정**: **클라이언트 잠금만**(서버 연결/스트림 유지, 재접근 재인증).

## 컴포넌트 요약
- 클라이언트: C1 ConnectionStore · C2 SnapshotController · **C3 SignedMutationGateway(★단일
  서명 관문)** · C4 ApprovalQueueController · C5 ConfirmSheet · C6 DashboardView · C7 DetailViews
  (thesis/health) · C8 SessionEntry · C9 LockController · C10 MobileShell.
- 서버(신규): **S1 WebAuthnGate 확장 — 원격 session.prompt 게이트**(F75 `verifyAssertionHeader`/
  `isRemoteOrigin` 재사용).
- **재사용(무변경 로직)**: `dashboard.ts`, `pairing.ts`, `webauthn-client.ts`, 기존
  `@/context/permission`·`server-sync`·`pages/session.tsx`, 서버 F75 게이트.

## 보안 설계 (Security Baseline)
- **SECURITY-08/11 (접근제어·secure design)**: mutating은 단일 관문(C3)→서버 최종 강제. 클라이언트
  우회로 금지. 보안 핵심 로직(서명 의식)은 C3/webauthn-client에 격리.
- **SECURITY-12 (세션/자격)**: 비활성 잠금+재인증. 비번/패스키 코드·로그 비노출.
- **SECURITY-15 (fail-safe)**: 서명 취소·오류·오프라인·잠금 모두 mutating fail-closed. 외부
  호출 try/catch. stale를 신선한 척 안 함.
- **SECURITY-04**: HTML 보안헤더는 serve(서버) 책임 → 이 트랙 N/A. 신규 외부 CDN 미도입(self-host)
  → SRI 불필요.
- N/A: SECURITY-01/02/06/07(인프라), 10(의존성 lockfile 고정으로 충족), 14(전용 알림 인프라 없음).

## 테스트 설계 (PBT — PBT-01 속성 식별)
- **라운드트립(PBT-02)**: `b64urlToBuf`↔`bufToB64url`; 페어링 build↔`parsePairingPayload`.
- **불변식(PBT-03)**: `toDashboard` never-throw + `positionCount===유효심볼수` + offline 일관;
  `dashboardSummary` 전사상 안전; `isMutatingAutostockPermission` 분류 안정.
- **오라클/상태(PBT-05/06)**: ApprovalQueue 순차 처리(모델 대조) — 필요 시.
- **예시기반(PBT-10)**: 서명통과/취소/거부/오프라인/잠금 핵심 시나리오 컴포넌트 테스트로 고정.
- **프레임워크(PBT-09)**: fast-check(Vitest). 시드 로깅/shrink 유지(PBT-08).

## 검증 설계
- 트랙 내: 단위·컴포넌트·PBT + tsgo typecheck + **데스크톱 가짜 패스키 e2e 시뮬**(주입형
  fetcher/credentialsGet로 흐름 A·B 헤드리스 검증).
- post-merge(사용자): 실 tailscale serve + 실기기 패스키 토폴로지 스모크 1회.

## 단위(Units) 제안 — Units Generation 입력
- **U1 — 데이터·연결 기반**: C1, C2, SnapshotService, DetailViews 읽기 경로 + dashboard PBT.
- **U2 — 보안 mutating 경로 (핵심)**: C3 SignedMutationGateway + C4/C5 승인 큐·시트 + S1 서버
  게이트 확장 + C9 잠금. (흐름 A·B·D)
- **U3 — 셸·세션·다듬기**: C10 MobileShell + C8 SessionEntry(입력 게이트) + FR-8 pull-to-refresh
  + 모바일 우선 스타일.
> 셸 통합상 단일 유닛으로 처리할 수도 있음(트랙 규모 작음) — Units Generation에서 확정.
