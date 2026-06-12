# Track F75 — F71 후속: WebAuthn 게이트 토폴로지 검증·강화

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F75
- **Title**: F71 모바일 보안 게이트 후속 — code-review 5건 (토폴로지 우회·fail-open·챌린지·타이밍·등록통제)
- **Type**: feature (security hardening)
- **Status**: merged → main 25bcb28 (2026-06-13)  <!-- B&T green; 라이브 스모크는 post-merge-guide -->
- **Branch**: feat/F75
- **Worktree**: .claude/worktrees/F75
- **Submodule branch**: — (monorepo; opencode fork 코드)
- **Base commit**: cf9869b (pull 후 main)
- **Start Date**: 2026-06-12

## Extension Configuration
- **Security Baseline**: **Enabled** — 본 트랙 자체가 보안 강화. 게이트 의미 변경(loopback 신뢰 제거)은
  fail-closed 방향만 허용; 키/시크릿 저장 방식 불변(공개키만 저장 유지).
- **Property-Based Testing**: N/A (결정적 게이트 로직 — 단위테스트로 충분).

## Scope (F71 머지 후 /code-review 발견 5건 — 2026-06-12)

대상: `operator-console/cli/packages/opencode/src/server/autostock/webauthn.ts` (+ permission/session 핸들러)

1. **[HIGH] 토폴로지 우회/불능**: 게이트가 raw 소켓 주소의 loopback 여부로 판정하는데, 권장 배포
   (`tailscale serve` TLS 프론트)에서 프록시 dial 소스가 127.0.0.1이면 **폰 mutating 승인이 무서명 통과**.
   반대로 serve가 localhost 타깃만 지원하면 tailnet-IP-only 바인드와 충돌해 접속 불능.
2. **[MED] fail-open 기본값**: `remoteAddress=undefined`(Option.none) → 무조건 신뢰. in-process(데스크톱
   TUI) 식별 수단이 이것뿐이라는 단정에 의존.
3. **[LOW] 챌린지 전역 1슬롯**: kind별 단일 챌린지 — 동시 assert가 서로 무효화.
4. **[LOW] basic-auth 비교 non-constant-time**.
5. **[LOW] 등록 통제**: 서버 비밀번호만으로 새 패스키 등록 가능(비밀번호 = 서명권한 발급권한).

+ **라이브 토폴로지 스모크**: 실제 `tailscale serve` 구성에서 백엔드가 보는 소스 IP 확인 +
  폰(또는 `aidlc-docs/research/mobile-ai-debugging.md`의 adb+CDP 하네스)으로 mutating 승인 거부 확인.
  F71 post-merge-guide 스모크 체크리스트 보강.

## 설계 방향 (Requirements=위 5건; 정책 결정은 게이트에서)
- #1+#2 통합 근본해: **소켓 = 전부 게이트 대상**(loopback 신뢰 제거), in-process(Option.none)만 bypass
  → 토폴로지 무관(deep fix). 단, loopback 소켓으로 승인하는 정당한 클라이언트가 없는지 전수 확인 필요
  (의미 변경 = 사용자 승인 게이트).
- #3: 챌린지 Map을 값-키(+TTL)로 → 동시 다건 안전.
- #4: `crypto.timingSafeEqual`.
- #5: 정책 결정 — 패스키 ≥1 존재 시 신규 등록에 기존 패스키 서명 요구 vs env 잠금 플래그.

## Merge Risk Notes
- **공유 파일 (주의)**: `webauthn.ts`, `permission.ts`/`session.ts` 핸들러, `launcher/serve.ts`(스모크 문서),
  F71 post-merge-guide. 다른 active 트랙(F73/F74)과 겹침 미상 — 머지 시 확인.
- **API/시그니처 변경**: 게이트 의미 변경(loopback 소켓 신뢰 제거) 시 외부 관측 동작 변화 — 승인 필요.
- **알려진 동시 변경**: F73/F74(타 세션) — opencode fork를 건드리면 조정.

## Stage Progress
- [x] Workspace Detection — brownfield, F71 머지 직후 후속
- [x] Requirements Analysis — minimal (code-review 5건 = 요구사항; 본 state Scope 절)
- [ ] User Stories — skip (보안 수정, 단일 운영자)
- [x] Workflow Planning — 단일 유닛 직행
- [ ] Application Design — skip (기존 모듈 내 수정)
- [x] Construction — 게이트 정제(isRemoteOrigin: 신원헤더 판정) + 챌린지 값-키 + timingSafeEqual + 등록잠금 + 핸들러 2곳 배선 + 테스트 9건 추가
- [x] Build & Test — webauthn 32 pass·typecheck 19/19·addon 15·pytest 1087; 라이브 토폴로지 스모크는 post-merge-guide(데몬 호스트 필요)
- [x] post-merge-guide — 스모크 체크리스트(헤더 확인이 핵심)
