# Track F27 — docker-verify를 호스트 사용자로 실행 (root-소유 문제 근본 제거)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F27
- **Title**: docker-verify 하네스 non-root 실행 — root-소유 파일 근본 제거 + 우회 코드 정리
- **Type**: feature (인프라 BUG fix/refactor)
- **Status**: active
- **Branch**: feat/F27 (TBD — Code Gen Part 2에서 worktree 생성)
- **Worktree**: .claude/worktrees/F27 (TBD)
- **Submodule branch**: — (parent repo only: Dockerfile.verify / docker-compose.verify.yml / scripts/verify.sh)
- **Base commit**: TBD
- **Start Date**: 2026-06-01

## Extension Configuration
- **Security Baseline**: Enabled. 적용: SECURITY-15(fail-safe). 대부분 N/A(앱 로직 아님, 검증 하네스 인프라).
- **Property-Based Testing**: N/A (셸/도커 설정, 순수함수 없음).

## Scope
docker-verify 컨테이너를 호스트 사용자(UID:GID)로 실행해 bind-mount에 쓰는 파일이
처음부터 호스트 소유가 되게 한다. 그 결과 불필요해지는 verify.sh 우회 코드(F17 chown
handback, .git 비파괴 백업, safe.directory, 일부 named-volume 마스킹)를 제거한다.
검증 필수: typecheck/unit/smoke/attach 4모드 + claude CLI + bun + 데몬이 non-root에서 동작.
관련: [[submodule-merge-workflow]] (이 문제로 F22/F25 서브모듈 git 두 번 파괴됨).

## Stage Progress
- [x] Workspace Detection — Brownfield, RE 아티팩트 존재 → Requirements Analysis로
- [x] Requirements Analysis — Standard depth, `docker-verify-nonroot.md` 승인됨 (2026-06-01)
- [x] User Stories — SKIP (개발 인프라, 사용자 대면 없음)
- [x] Workflow Planning — 실행 계획 승인됨 (`inception/plans/docker-verify-nonroot-execution-plan.md`, 2026-06-01)
- [ ] Application Design — SKIP (새 컴포넌트/메서드 없음)
- [ ] Units Generation — SKIP (단일 유닛: verify-harness)
- [ ] Functional Design / NFR Requirements / NFR Design — SKIP (비즈니스 로직·신규 NFR 없음)
- [x] Infrastructure Design — 승인됨 (`construction/verify-harness/infrastructure-design/`). 확정: D-1 래퍼(verify-run.sh), D-2 볼륨 구조 유지, D-3 HOME=/tmp. critic 5건 반영(G-7 init-perms 1차안, G-1 verify-first, MED-4 git 근거 교정 등)
- [x] Construction (Code Generation) — worktree `.claude/worktrees/F27`(feat/F27, base 46c48a9) 생성. 4 parent 파일 변경 +90/−78 + 신규 verify-run.sh. 비실행검증(bash -n, compose config, fail-loud) 통과. 코드요약: `construction/verify-harness/code/code-summary.md`
- [x] Build & Test — **4모드 전부 PASS**: typecheck 19/19, unit 556, smoke OK, attach OK(⭐G-1 인증 verify-first 적중, ⭐MED-4 git 에러 없음). `find -user root` 공백 + sudo-free 제거 실증. 테스트 중 2건 픽스: Dockerfile `npm i -g node-gyp`, verify-run.sh 마운트포인트 호스트소유 선생성. 선행 블로커(서브모듈 origin 미동기화)도 push로 해결.
- [ ] 커밋 → main 머지 (parent-only, 서브모듈 변경 없음)
