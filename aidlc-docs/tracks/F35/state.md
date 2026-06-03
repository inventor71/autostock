# Track F35 — CLI 서브모듈을 autostock 단일 repo로 통합 (de-submodule / monorepo)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F35
- **Title**: `operator-console/cli` 서브모듈을 autostock 본 repo로 통합 (monorepo)
- **Type**: refactor (repo 구조 변경, 동작 보존) — `/ai-dlc-request`로 진입했으나 본질은 구조 리팩토링
- **Status**: merged (main 2253029, 2026-06-03)
- **Branch**: feat/F35 (TBD)
- **Worktree**: — (구조 변경이라 worktree 격리 모델과 충돌; 아래 "실행 위치" 참고)
- **Submodule branch**: — (이 트랙은 서브모듈 자체를 제거하는 것이 목적)
- **Base commit**: 6dd91ab (main @ 트랙 생성 시점)
- **Start Date**: 2026-06-03T00:40:15Z

## Extension Configuration
- **Security Baseline**: Enabled — 통합 시 `.env`/`.gitleaksignore`/시크릿이 새 위치로 이동.
  SECURITY-03(로그 시크릿 금지)/시크릿 파일 .gitignore 유지가 적용 대상.
- **Property-Based Testing**: TBD (Requirements에서 결정)

## Scope
현재 TUI 콘솔(`operator-console/cli`)은 별도 GitHub repo `inventor71/autostock-cli`
(opencode 포크)로 분리된 git 서브모듈이다. 테스트/검증 시 git 컨텍스트가 분리되어
worktree에 서브모듈 working tree가 자동 포함되지 않고, 트랙마다 서브모듈 브랜치를 따로 따고
머지 시점에 부모 gitlink를 커밋해야 하는 반복 비용이 있다 (F4/F8/F13/F19/F31/F34에서 반복).
이 트랙은 서브모듈을 본 repo로 흡수해 단일 git 컨텍스트로 만든다.

관련 메모: [[submodule-merge-workflow]] (이 워크플로를 없애는 것이 목적),
[[aidlc-multitrack-partition]] (worktree 게이트가 서브모듈을 별도 처리), [[console-native-launcher]].

## 핵심 사실 (조사 결과)
- 서브모듈 = opencode 포크, 별도 repo `git@github.com:inventor71/autostock-cli.git`, branch=main.
- 포크 히스토리는 squash 임포트로 **43 커밋** (.git/modules ≈ 56M) — 상류 opencode 전체
  히스토리는 없음. → 히스토리 보존 subtree 머지가 현실적.
- working tree ≈ 101M (README 다국어/assets/.opencode/.hypothesis 포함; node_modules는 gitignore).
- 서브모듈 참조 위치: `docker-compose.verify.yml`, `scripts/worktree-setup.sh`,
  `scripts/verify.sh`, `scripts/verify-run.sh`, `src/agent/steering/runtime.py`,
  AI-DLC 룰(`concurrent-tracks.md`, `code-generation.md`), `CLAUDE.md`, `.gitmodules`.

## 실행 위치 주의 (worktree 게이트 예외)
서브모듈 제거는 `.gitmodules`/gitlink/repo 루트 트리를 바꾸는 **repo 구조 변경**이라
일반 worktree 격리(서브모듈 전제) 모델에 들어맞지 않는다. 전용 브랜치(feat/F35)에서
수행하되 worktree 격리 방식은 Requirements/Plan에서 확정한다.

## 확정된 결정 (사용자 답변 2026-06-03)
1. 상류 opencode 추적: **이제 안 끌어옴(완전 독립)** → 서브모듈 완전 흡수.
2. 히스토리: **보존(subtree merge)** — 43커밋을 `operator-console/cli/` 경로로 유지.
3. autostock-cli repo: **외부 의존 없음 → archive**.
4. 방향: **monorepo 통합 진행**.
가져올 커밋 = b26a930 (부모 gitlink = 포크 main tip, 미머지 작업 없음, 검증 완료).

## Stage Progress
- [x] Workspace Detection — brownfield, 기존 트랙 다수 active(아래 주의). 새 요청으로 진행.
- [x] Requirements Analysis — standard. 명확화 4문 답변 완료(위 결정). 토폴로지 검증 완료.
- [x] User Stories — skip (사용자 대면 기능 아님; 개발자/AI 워크플로 개선).
- [~] Workflow Planning — 실행 계획 작성 완료(`construction/plans/F35-monorepo-merge-plan.md`), **승인 대기**.
- [x] Application Design — skip (새 컴포넌트 없음).
- [x] Units Generation — skip (단일 작업).
- [x] Construction (repo 구조 변경 + 툴링/룰 갱신) — 계획 A~D 완료 (feat/F35)
- [x] Build & Test — E1 typecheck 19/19, E2 py 104 pass, E4 fresh-worktree 자동포함, E5 시크릿 clean
- [x] F. 마무리 — F2 `--no-ff` 머지(main 2253029, 서브모듈 안전 전이: deinit→merge→runtime 복원),
  F4a 잔여 git 상태 정리(.git/config 섹션 + .git/modules 56M 제거, b26a930 보존 확인), F4 레지스트리 merged·
  글로벌 audit·worktree 제거·temp ref 삭제. **F1 critic 재검토는 code-review high로 대체**(③ 반영/① F4a 완료).
  **F3 archive(GitHub autostock-cli)는 외부 작업 — 사용자에게 안내만, 미실행.**

## 머지 후 후속 (다른 트랙 영향)
- **F16**(paused, 라이브 worktree 잔존) + **F36**(동시 신규 등록, 서브모듈 가정 base b26a930): 둘 다 pre-F35라
  재개 시 **새 worktree + cherry-pick**으로 진행(naive merge 금지 — `.gitmodules`/gitlink 충돌). 각 트랙 세션이
  자기 state에 반영. F35는 해당 트랙 파일 미수정(single-writer).
- 머지 중 라이브 트레이딩 데몬(main.py --mode agent + 콘솔 launcher/mcp) 동작 중이었으나 F35는 그 경로(main.py,
  operator-console/{launcher,src})를 안 건드려 무중단. operator-console/cli runtime(node_modules/.env/.opencode) 복원 완료.

## 실행 결과 (feat/F35, base 0f26b48)
커밋 3개 (콘솔 43커밋 히스토리 보존 위):
- `405ce90` 서브모듈 gitlink + .gitmodules 제거 (pre-merge)
- `c9371af` subtree add — operator-console/cli 히스토리 보존 임포트 (merge: 405ce90 + b26a930)
- `bc7ff6e` 단일repo 툴링/룰 정리 + 시크릿 스캔 훅 + 죽은 .github 제거

**사용자 피드백 반영**: "처음부터 monorepo였던 것처럼" — 서브모듈 가정 코드/코멘트 전부 제거
(worktree-setup/verify/verify-run, concurrent-tracks/code-generation/CLAUDE.md, ai-dlc-request/status,
Dockerfile.verify, 레지스트리 테이블 컬럼). monorepo 강조/마이그레이션 코멘트는 in-tree에 넣지 않음
(커밋 메시지에만). 잔여 submodule 참조 0 (git grep 확인). [[feedback-monorepo-refactor-as-native]]

**검증**: E1 콘솔 typecheck 19/19 ✓ · E2 steering/runtime import + 104 pass ✓ · E4 detached probe
worktree에서 operator-console/cli/package.json 즉시 존재(mode 100644, gitlink 아님), .gitmodules 없음 ✓ ·
E5 .env/.sst/node_modules 등 미추적, .env.example 템플릿만 ✓. E3 docker-verify는 E1과 동등 → defer.

## D5 시크릿 방어 (신규)
`.pre-commit-config.yaml`(gitleaks v8.18.4) + `.gitleaks.toml`(allowlist: .env.example,
opencode http-recorder/llm 테스트 픽스처, AKIA…EXAMPLE/xoxb placeholder) + pyproject dev에 pre-commit.
1회 `pre-commit install` 필요(README/안내).

## 활성 트랙 주의 (Workspace Detection)
레지스트리에 active 트랙 다수: F6, R1, M1, F16, F28, F30, F33(paused). F35는 이들의
서브모듈 브랜치/gitlink 작업과 충돌할 수 있으므로, 통합 시점에 미머지 서브모듈 브랜치
(feat/F22, feat/F25, feat/console-native-launcher 등 로컬, origin feat/F26 등) 처리 방침을 정해야 함.
