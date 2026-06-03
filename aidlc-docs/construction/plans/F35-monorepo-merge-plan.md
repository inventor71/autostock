# F35 실행 계획 — CLI 서브모듈 → autostock 단일 repo 통합 (history-preserving)

> Track F35. 동작 보존 repo 구조 변경. 단일 작업이라 User Stories / Application Design /
> Units Generation은 skip. 본 문서가 Requirements 확정 + Workflow Planning + Code-Gen Plan을 겸한다.
> 승인 후 자율 실행([[feedback-autonomy-construction]]).

## 확정된 결정 (사용자 답변 2026-06-03)
1. **상류 opencode 추적**: 이제 안 끌어옴 — 완전 독립. → 서브모듈 완전 흡수, pull 경로 보존 불필요.
2. **히스토리**: 보존 (subtree merge). 콘솔 43커밋을 `operator-console/cli/` 경로로 유지.
3. **autostock-cli repo**: 외부 의존 없음 → 통합 후 GitHub에서 archive(read-only).
4. **방향**: monorepo 통합 진행.

## 가져올 대상 (검증 완료)
- 임포트 커밋 = **b26a930** (= 부모 gitlink = 포크 main tip, 43커밋).
- 미머지 콘솔 작업 없음. 서브모듈 uncommitted 변경 없음. → 손실 없는 클린 임포트.

## 통합 방법 — git subtree merge (히스토리 보존)
서브모듈 객체는 이미 부모의 `.git/modules/operator-console/cli`에 전부 있으므로 재클론 불필요.
파일이 이미 `operator-console/cli/` 경로에 있으니, 먼저 서브모듈을 제거한 뒤 같은 경로로 subtree add.

## 실행 위치 (worktree 게이트)
repo 구조 변경이지만 worktree로 격리 가능(객체 저장소 공유). 전용 worktree에서 수행:
`git worktree add .claude/worktrees/F35 -b feat/F35` (base=main 6dd91ab). main 트리는 건드리지 않음.
서브모듈 흡수가 목적이므로 별도 서브모듈 브랜치 없음.

## 단계별 체크리스트

### A. 준비
- [x] A1. main 최신화 확인, `git worktree add .claude/worktrees/F35 -b feat/F35`
- [x] A2. 콘솔 객체를 **메인 repo** ref로 확보(critic #6: worktree에서 `./.git/modules/...` 상대경로 미해석):
      `git -C <MAIN_ROOT> fetch /home/jihoonpark/Project/autostock/.git/modules/operator-console/cli b26a930:refs/F35/cli-import`
      (절대경로 사용; worktree는 객체 저장소 공유하므로 이후 worktree에서 `refs/F35/cli-import` 참조 가능)
- [x] A3. 임포트 전 **전체 히스토리** 시크릿 스캔(critic #1: subtree는 현재 트리뿐 아니라 43커밋 전체를 가져옴):
      `git -C operator-console/cli log --all --full-history -- .env` 빈지 확인 + `gitleaks detect` (히스토리 모드).
      ※ 검증 결과: `.env`는 0커밋, 히트는 upstream opencode 테스트 픽스처뿐(AKIA…EXAMPLE 등) — 현재로선 clean.
      그래도 임포트 직전 재실행해 차단 게이트 유지 (SECURITY-03)

### B. 서브모듈 제거
- [x] B1. `git rm -r operator-console/cli` — gitlink + working tree **완전 제거**
      (critic #1: `subtree add`는 prefix가 비어 있어야 동작. `--cached`로 트리를 남기면 C1이 'prefix already exists'로 실패.
      제거 후 `ls operator-console/cli` 가 없음을 확인하고 C1 진행)
- [x] B2. `.gitmodules`에서 `[submodule "operator-console/cli"]` 블록 제거 (파일이 비면 파일 삭제)
- [x] B3. `.git/config`의 submodule 엔트리 정리 (worktree-local), `.git/modules/...`는 임포트 후 정리
- [x] B4. 커밋: "refactor(F35): drop operator-console/cli submodule (pre-merge)"

### C. 히스토리 보존 임포트
- [x] C1. (working tree에 `operator-console/cli/` 없음 확인 후) `git subtree add --prefix=operator-console/cli refs/F35/cli-import`
      (43커밋 히스토리가 머지로 들어옴; 파일이 같은 경로로 생성됨)
- [x] C2. 임포트 결과 검증: `git log -- operator-console/cli/` 에 콘솔 히스토리 보이는지,
      `operator-console/cli/package.json` 등 핵심 파일 존재 확인
- [x] C3. **중첩 `.gitignore`는 load-bearing — 루트로 통합 금지**(critic #2): 콘솔 `operator-console/cli/.gitignore`는
      tracked이며 `.sst`(SST 배포 상태)·`.env`·`.codex`·`.direnv`·`.serena`·`.turbo`·`ts-dist` 등을 무시하는데
      **루트 `.gitignore`엔 대부분 없음**. 이 파일을 그대로 둔다(merge로 tracked 유입됨). 주석으로 "load-bearing,
      루트로 합치지 말 것" 명시. `.opencode/`는 `agent/*.md`만 tracked·나머지는 ignore인 혼합 상태 유지.

### D. 참조 갱신 (단일 컨텍스트 반영)
- [x] D1. `scripts/worktree-setup.sh` (L67~) — `--ts` 경로의 `submodule update --init` + `switch -c`(L70,74)는
      통합 후 깨짐(critic #5). **단순 삭제 말고 `.gitmodules` 엔트리 유무로 분기**: 서브모듈이면 기존 로직, 아니면
      monorepo 가정(서브모듈 init/branch skip)으로 하위호환. → 머지 전 생성된 worktree(F16 등)도 안전.
- [x] D2. `scripts/verify.sh`, `scripts/verify-run.sh`(L35 `mkdir -p .../node_modules`), `docker-compose.verify.yml` — 서브모듈 경로/마운트 갱신
- [x] D3. `src/agent/steering/runtime.py` (L368,399-429) — 단순 경로 문자열 참조뿐, **무변경**(critic 확인)
- [x] D4. **AI-DLC 룰 갱신** (M1 영역과 겹침 주의):
      `.aidlc-rule-details/common/concurrent-tracks.md`의 "MANDATORY worktree gate (repo + submodule)"
      에서 서브모듈 브랜치/gitlink 댄스 조항을 monorepo 현실로 개정;
      `.aidlc-rule-details/construction/code-generation.md`, `CLAUDE.md`의 `operator-console/cli` 서브모듈 언급 갱신
- [x] D5. **(보안, 사용자 결정 = 신설)** 루트 **gitleaks pre-commit hook 신설** — monorepo 전체(Python+콘솔 서브트리)
      커밋 시점 시크릿 스캔. 구현: `.pre-commit-config.yaml`에 gitleaks 훅 추가 또는 `.git/hooks/pre-commit` 스크립트.
      죽은 콘솔 `.gitleaksignore`(SHA `afa57ac` invalid)는 제거하고, 필요한 false-positive(upstream 테스트 픽스처
      AKIA…EXAMPLE 등)는 루트 gitleaks 설정의 allowlist로 이관. 콘솔 `.husky`는 untracked라 무시(영향 없음).
- [x] D6. **(사용자 결정 = 제거)** 콘솔 `operator-console/cli/.github/`(deploy/publish 등 26개 워크플로,
      상류 opencode의 CLOUDFLARE/STRIPE_PROD/Azure 시크릿 참조) → `git rm -r operator-console/cli/.github` (비활성·무해이나
      혼동 방지·위생). 콘솔 고유 비-워크플로(예: ISSUE_TEMPLATE)가 있으면 보존 여부 개별 판단.

### E. 검증 (Build & Test)
- [x] E1. 콘솔 typecheck: `(cd operator-console/cli && PATH=~/.bun/bin:$PATH bun install --frozen-lockfile && bun run typecheck)`
- [x] E2. Python 단위 테스트: 메인 venv로 영향 받은 테스트 (steering/runtime 등)
- [ ] E3. verify 하네스 단일 컨텍스트 동작: `docker compose -f docker-compose.verify.yml run --rm verify typecheck` (또는 in-place)
- [x] E4. 새 worktree 시뮬레이션: 통합 후 `git worktree add`가 콘솔 트리를 자동 포함하는지(서브모듈 init 불필요) 확인 — 이 트랙의 핵심 목표 검증
- [x] E5. **(보안 게이트)** 머지된 HEAD에 대해 `git status --porcelain operator-console/cli/` + `gitleaks detect`
      재실행(critic #2): 통합 결과물에 새로 추적되는 시크릿/배포 상태(.sst 등)·빌드 산출물 없음을 확인. A3는 소스만 봤음 — 이건 결과물 검증.

### F. 마무리 / 머지
- [ ] F1. critic 서브에이전트로 구조 변경 리뷰 (히스토리 보존/시크릿/참조 누락 점검)
- [ ] F2. feat/F35 → main 머지 (gitlink 커밋 불필요 — 서브모듈 없음)
- [ ] F3. GitHub `inventor71/autostock-cli` archive (사용자 수동 또는 gh CLI 안내).
      ※ 주의(critic #4): GitHub `origin/main`=43423df 로 임포트 tip b26a930보다 **2커밋 뒤**(F28 미push). 임포트는
      로컬 b26a930 기준이라 손실 없음 — archive는 read-only 보관용이며 monorepo가 이제 source of truth임을 명시.
- [ ] F4. 레지스트리 행 merged 플립 + 루트 audit.md 한 줄 요약 + 트랙 state.md 마감.
- [ ] F4a. **(code-review ① — 머지 직후에만 안전)** 서브모듈 잔여 git 상태 정리. ⚠️ **F35가 main에 머지되기
      전에는 실행 금지** — main 작업트리가 아직 서브모듈(gitlink 160000 + `operator-console/cli/.git`
      → `.git/modules/...`)을 사용 중이라, 미리 지우면 main 체크아웃이 깨진다. 머지 후 main의 트리 엔트리가
      normal dir이 된 뒤:
      `git config --remove-section submodule.operator-console/cli` +
      `rm -rf .git/modules/operator-console` (콘솔 객체 b26a930은 subtree로 메인 object store에 이미 복제됨 — 확인됨, 손실 없음).
      ※ code-review ③(중복 `AKIAIOSFODNN7EXAMPLE` allowlist 정규식 제거)은 완료 — 커밋 1ac4879에 amend.

#### F16 보류 → F35 이후 재개 절차 (정밀화)
- **보류 안전성 (실측 확인 2026-06-03)**: F16 worktree working tree 깨끗(uncommitted 0), `feat/F16` 브랜치에
  `b2be961`(BrokerApiBroker) + `0c2db20`(get_open_orders status=ALL) **2커밋 보존**, F16은 `operator-console/cli`를
  전혀 안 건드림. 진행 기록은 `tracks/F16/{state.md,audit.md}`(main 트리, F35 무관)에 남음 → 잃는 것 없음.
- **⛔ naive merge 금지**: F16 base가 서브모듈 있던 구버전이라 `feat/F16 → post-F35 main` 직머지는
  `.gitmodules`/`operator-console/cli` gitlink↔tree 충돌을 일으킴.
- **✅ 재개 = cherry-pick**: F35 머지 후 `post-F35 main`에서 새 worktree 생성
  (`scripts/worktree-setup.sh F16 --py` — D1으로 monorepo-aware) → `git cherry-pick b2be961 0c2db20`
  (additive·서브모듈 무관 → clean) → 남은 **Build & Test** 스테이지 → 머지.
- F16 등록 상태는 그대로 두고(재개 시 그 트랙 세션이 자기 `tracks/F16/state.md`에 갱신), F35는 F16 파일을 건드리지 않음(single-writer 준수).

## 보안 노트 (critic 검토 결과 — "이 변경으로 새로 생기는 보안 리스크")
**결론**: 콘솔 트리/히스토리 자체엔 실제 시크릿 없음(검증됨). 새 리스크는 *content*가 아니라 *구조*에서 옴 —
1. **중첩 `.gitignore` 의존성**(C3): 통합 후 `operator-console/cli/.gitignore`가 SST 배포 상태 등 민감 산출물의
   유일한 방어선. 누군가 ignore를 루트로 "정리"하면 시크릿/배포 상태가 추적되기 시작 → 절대 합치지 말 것 + E5 결과 스캔.
2. **커밋 시점 시크릿 방어 부재**(D5): 루트 `.git/hooks` 없음, 콘솔 `.husky` untracked, `.gitleaksignore` SHA invalid →
   monorepo는 commit-time gitleaks 방어가 **0**. (콘솔도 원래 tracked hook 없어 *회귀*는 아니나, 노출면이 넓어진 만큼
   루트 pre-commit gitleaks hook 신설을 **권장**. ← 사용자 결정 필요: 신설 / 보류.)
3. **죽은 배포 워크플로**(D6): 상류 opencode의 CLOUDFLARE/STRIPE_PROD/Azure 시크릿 참조 워크플로가 서브경로로 유입.
   GitHub Actions는 루트 `.github`만 실행하므로 비활성·무해이나, 혼동 방지 위해 제거 권장(선택).

## 리스크 / 주의
- **R1 (시크릿)**: ✅ 검증 — 히스토리에 실제 시크릿 없음. A3(소스)+E5(머지 결과) 이중 게이트.
- **R2 (룰 동시편집)**: D4는 M1(멀티트랙 룰 커스터마이즈, active)과 같은 파일을 건드림 → 충돌 주의, 머지 시 재확인.
- **R3 (repo 비대)**: +~56M 히스토리. 수용 가능(사용자 보존 선택). working tree 101M은 node_modules 제외 실제 소스+다국어 README+assets.
- **R4 (다른 active 트랙)**: F6/F16/F30/F33. **F16은 라이브 worktree** → 머지 후 재생성 필요(F4). D1을 `.gitmodules` 분기로
   하위호환 → 머지 전 worktree도 안전. 재개 트랙엔 안내.
- **R5 (.git/modules 잔존)**: 임포트 후 `.git/modules/operator-console/cli` 정리(객체는 subtree로 복제됨).
