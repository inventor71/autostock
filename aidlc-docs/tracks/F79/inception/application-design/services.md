# F79 Application Design — Services / Orchestration

> 클라이언트 SPA라 "서비스"는 컨트롤러/스토어 오케스트레이션 계층. 백엔드 서비스 신규 없음
> (S1 게이트 확장 제외). 모든 mutating은 단일 관문(C3)으로 직렬화.

## SVC-1. AuthGateService (보안 핵심)
- **오케스트레이션**: ConfirmSheet(C5)·SessionEntry(C8)의 모든 mutating 의도를 C3
  (SignedMutationGateway) **단일 경로**로 모은다 → obtainAssertionHeader → 서명 헤더 첨부 전송.
- LockController(C9)와 협조: 잠금 상태면 서명 의식 진입 거부(fail-closed).
- **SECURITY-08/11**: 클라이언트는 서명을 "첨부"만 하고, 통과 여부의 최종 판정은 서버(S1)에서.
  클라이언트는 우회로(무서명 mutating 경로)를 만들지 않는다.

## SVC-2. SnapshotService
- ConnectionStore(C1) online일 때 주기 폴링으로 SnapshotController(C2) 갱신 →
  DashboardView(C6)·배지(C4) 구독 갱신. offline/stale 전이를 일원화(NFR-7).
- pull-to-refresh(FR-8)는 즉시 1회 폴 트리거.

## SVC-3. ApprovalService
- permission 이벤트 스트림(기존 server-sync) → ApprovalQueueController(C4) → ConfirmSheet 자동
  팝업(FR-6). 여러 건은 큐로 순차(서버 F75 챌린지는 값-키라 동시성 안전).

## SVC-4. SessionService
- 기존 session.tsx 뷰를 폰 라이브로 연결(FR-4). 입력 전송은 SVC-1(AuthGate) 경유.

## 오케스트레이션 원칙
- **읽기(대시보드/thesis/health/세션 스크롤)**: 무서명, 서버 trusted-read 경로.
- **mutating(승인/세션 입력)**: 반드시 SVC-1 → C3 → 서버 게이트(permission gate 기존 + S1 신규).
- **fail-closed 일관**: 어떤 오류·잠금·오프라인에서도 mutating은 "통과한 척" 하지 않는다.
