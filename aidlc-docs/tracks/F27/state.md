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
- [~] Requirements Analysis — Standard depth, 요구사항 문서 작성 완료, 승인 대기
- [ ] User Stories — SKIP 예정 (개발 인프라, 사용자 대면 없음)
- [ ] Workflow Planning
- [ ] Application Design — SKIP 예정
- [ ] Units Generation — SKIP 예정 (단일 유닛: verify-harness)
- [ ] Construction (per-unit Code Generation)
- [ ] Build & Test
