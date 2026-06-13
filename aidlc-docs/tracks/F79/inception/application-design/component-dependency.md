# F79 Application Design — Component Dependencies & Data Flow

## 의존 매트릭스 (→ = "uses")
| From | → To | 목적 |
|---|---|---|
| MobileShell(C10) | C1,C4,C6,C8,C9 | 내비/배지/잠금 |
| DashboardView(C6) | C2 | DashboardModel 구독 |
| SnapshotController(C2) | C1, SDK reads, health verb, C4 | 스냅샷 조립 |
| ApprovalQueueController(C4) | `@/context/permission`, server-sync | 승인 스트림 |
| ConfirmSheet(C5) | C3, C4 | 서명 전송 / 큐 |
| SessionEntry(C8) | `pages/session.tsx`(기존), C3 | 뷰 재사용 / 서명 입력 |
| C3 SignedMutationGateway | `webauthn-client.ts`, `serverSDK.client.{permission,session}` | 서명+전송 |
| LockController(C9) | C3 | 잠금 시 fail-closed |
| DetailViews(C7) | SDK steer_read(thesis/health) | 읽기전용 |
| **server S1 gate** | `verifyAssertionHeader`,`isRemoteOrigin`(F75) | 원격 prompt 게이트 |

## 핵심 데이터 흐름

### 흐름 A — mutating 승인 (FR-3/FR-6) ★
```
서버 permission ask
  → server-sync 이벤트 → ApprovalQueueController(C4) [배지++, 큐]
  → ConfirmSheet(C5) 자동 팝업
  → (운영자 "승인" 탭) → SignedMutationGateway(C3):
        POST /autostock/webauthn/assert-options  → challenge
        navigator.credentials.get(...)           → assertion
        permission.respond({reply, headers:{x-autostock-webauthn: base64(json)}})
  → 서버 permission gate(F75) verifyAssertionHeader → 승인 통과
  실패/취소 → WebAuthnError → C5 한국어 사유, 미전송(fail-closed)
```

### 흐름 B — 세션 입력 (FR-4, 게이트) ★신규 서버 경로
```
SessionEntry(C8) 입력 → SignedMutationGateway.signedPrompt
  → session.prompt({..., headers:{x-autostock-webauthn: sig}})
  → 서버 S1: isRemoteOrigin? → verifyAssertionHeader → 통과 / 401 deny
  읽기(이어보기 스크롤)는 무서명
```

### 흐름 C — 대시보드 (FR-2/FR-7/FR-8/NFR-7)
```
ConnectionStore(C1) online
  → SnapshotController(C2) 폴링(+pull-to-refresh) → assemble → toDashboard
  → DashboardView(C6) 렌더 (+stale 배지)
  탭: 포지션→PositionThesisView, 건강→HealthOverlay (읽기전용)
  연결 끊김 → C1 reconnecting/offline → C6 offline 표시
```

### 흐름 D — 잠금 (NFR-6)
```
LockController(C9) 비활성 타이머 만료 → 클라 잠금(서버 연결 유지)
  → 셸 가림, mutating(C3) fail-closed
  → 재접근: 패스키/비번 재인증 → unlock
```

## 통신 패턴
- 읽기: SDK read / steer_read verbs (무서명, 폴링 + 이벤트 스트림).
- mutating: SDK + per-call `x-autostock-webauthn` 헤더(단일 관문 C3). 서버가 최종 강제.
- 신규 외부 의존성: 없음(기존 SDK/브라우저 WebAuthn API). fast-check만 devDependency 추가(PBT).
