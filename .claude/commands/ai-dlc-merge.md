---
description: 완료된 트랙들을 한 곳에서 순차 머지 — merge-awaiting 큐를 main 위로 차례로 rebase·verify·merge·cleanup (꼬임 방지)
argument-hint: "[선택: 트랙 ID 필터(F38 등, 쉼표 구분) — 비우면 모든 merge-awaiting 트랙을 큐로]"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash(git status:*), Bash(git worktree list:*), Bash(git worktree remove:*), Bash(git log:*), Bash(git diff:*), Bash(git merge-base:*), Bash(git rev-list:*), Bash(git branch:*), Bash(git rebase:*), Bash(git merge:*), Bash(git -C:*), Bash(git pull --rebase:*), Bash(scripts/worktree-setup.sh:*), Bash(scripts/verify.sh:*), Bash(docker compose:*), Bash(bun test:*), Bash(pytest:*)
---

# /ai-dlc-merge — 완료 트랙 순차 머지 오케스트레이터

여러 트랙을 worktree로 **동시에** 개발하다 각자 main으로 머지하면 서로 겹쳐 꼬인다
(stale base 위 브랜치, 공유 파일 registry/audit 경합, 교차-통합 깨짐 — 예: F37 머지 후
잔존 참조 크래시를 F42 핫픽스로 수습). 이 명령은 **단 한 곳(main 작업 트리)에서만** 실행되어
**merge-awaiting 트랙 전체를 하나의 큐로 보고 차례로** 머지한다. 단일 실행 지점이므로 공유 파일
경합이 락 없이 자연 직렬화되고, 각 트랙은 **직전 머지가 반영된 main 위로 다시 rebase**되어
꼬임이 머지 전에 그 자리에서 드러나 해결된다.

스코프 필터: $ARGUMENTS (비어 있으면 모든 merge-awaiting 트랙)

## 실행 전제 (blocking)
- **main 작업 트리에서, 단일 인스턴스로만 실행.** worktree 안이거나 `/ai-dlc-merge`가 이미
  돌고 있으면 중단. (동시성 가드는 "한 곳에서만 돈다"는 이 전제 자체다 — 별도 락 없음.)
- main 작업 트리에 **미커밋 변경이 있으면 중단**(머지/문서 커밋이 섞이지 않게).
- 문서는 한국어 기본. 애플리케이션 코드는 워크스페이스 루트, 문서는 `aidlc-docs/`에만.
- 사용자 입력/승인은 글로벌 `aidlc-docs/audit.md`에 **append**(덮어쓰기 금지).

---

## 단계 0 — Merge 큐 구성 + 사용자 확인 (🛑 유일한 승인 게이트)

1. **후보 수집.** 루트 `aidlc-docs/aidlc-state.md`의 Track Registry에서 `active` 행을 읽고,
   각 트랙에 대해:
   - **merge-ready 신호**(우선): `aidlc-docs/tracks/<id>/state.md`의 `**Status**:`가
     `merge-awaiting`이면 명시적 머지 대기. (트랙이 자기 파일에만 찍으므로 경합 없음.)
   - **휴리스틱 폴백**: 명시 신호가 없으면 — worktree 존재 + feat 브랜치가 main보다 앞선
     커밋 보유(`git rev-list main..feat/<id>` ≥ 1) + state.md의 Stage Progress가 전부 `[x]`
     (특히 Build & Test) → **후보**로 올리되 "추정"으로 표시.
2. **트랙별 준비 증거**를 모은다: 앞선 커밋 수, base commit, `git merge-base feat/<id> main`,
   변경 파일 목록, state.md의 verification 섹션 요약.
   **또한 각 후보 트랙의 `state.md`에서 `## Merge Risk Notes` 섹션을 읽는다**:
   - 공유 파일, API/시그니처 변경, 알려진 동시 변경 트랙 정보가 있으면 큐 구성에 반영.
   - 이 정보는 트랙 작성자가 직접 기록한 것으로, `git diff --name-only` 자동 겹침 분석을
     **보완**한다(자동 분석은 파일 레벨이지만 Risk Notes는 함수/시그니처 레벨 위험을 포착).
   - Risk Notes가 비어 있어도 무방 — 자동 diff 분석만으로 충분한 경우가 대부분.
3. **사전 게이트(자동 제외)** — 다음은 큐에서 빼고 사유를 함께 보고:
   - base가 **F35 monorepo 통합(2253029) 이전**이면 제외 → 서브모듈 경계를 넘는 자동 rebase는
     위험(메모리 [[submodule-merge-workflow]] / F16 후속 노트). 수동 cherry-pick 필요로 안내.
   - 앞선 커밋이 0이거나 worktree가 없으면 "머지할 게 없음"으로 제외.
4. **교차-겹침 분석.** 큐 후보 쌍마다 변경 파일 교집합을 계산(`git diff --name-only main...feat/<id>`).
   겹치는 트랙 쌍과 파일을 표로 표면화한다.
5. **순서 자동 결정(의존/겹침 기반).** 독립적인(다른 후보와 파일 겹침 0) 트랙을 먼저,
   겹치는 트랙은 base-age(오래된 base 먼저)로 뒤에 배치해 충돌을 큐 후반으로 몰아 최소화한다.
   결정한 순서와 **근거**(왜 이 순서인지)를 제시한다.
6. **사용자에게 큐 전체를 제시하고 1회 승인**을 받는다:
   ```
   Merge 큐 (제안 순서):
     1. F40  [clean]         feat/F40  ↑3  겹침 없음
     2. F38  [추정]          feat/F38  ↑5  겹침: F41 (config/main.py)
     3. F41  [merge-awaiting] feat/F41 ↑7  겹침: F38 (config/main.py)
   제외: F30 (base가 F35 이전 — 수동 cherry-pick)
   ```
   - 사용자가 승인하면 **이후는 자율 진행**(아래 멈춤 조건에서만 정지).
   - 승인/선택을 `aidlc-docs/audit.md`에 append.
   - merge-awaiting 트랙이 없으면 "머지할 트랙 없음"으로 종료.

---

## 단계 1..N — 트랙별 순차 머지 루프 (승인된 순서대로)

각 트랙 `T`(worktree `W`, 브랜치 `feat/T`)에 대해 순서대로:

### 1) 최신 main 위로 rebase (꼬임 차단의 핵심)
- `git -C W rebase main` — **직전 트랙 머지가 반영된** 현재 main 위로 feat/T를 올린다.
- **충돌 시**: 충돌 파일/헝크를 분석한다.
  - 기계적/명백한 충돌(import 정렬, 직전 머지가 만든 rename·시그니처 변경에 대한 동일 방향
    수정 등)은 직접 해결하고 `git -C W rebase --continue`.
  - **의미적 충돌**(두 트랙이 같은 로직을 서로 다른 의도로 바꿈)은 **멈춤** → 사용자에게
    충돌 내용을 제시하고 판단을 받는다.
- **⚠️ 충돌 해결 후 교차-로직 검증 (MANDATORY, 충돌 발생 시에만):**
  충돌이 발생한 모든 파일에 대해, rebase를 계속하기 **전에** 다음을 수행한다:
  1. **충돌 해결된 파일을 전체 읽고**, rebase된 트랙이 추가한 모든 새 코드(함수 호출, 변수
     참조, prop 전달, import 사용)에서 참조하는 **식별자(identifier)를 목록화**한다.
  2. **각 식별자가 병합 결과 파일에서 실제로 정의/import 되었는지 확인**한다:
     - 함수/변수: 파일 내에 정의가 존재하는가?
     - import: import 문에 포함되어 있는가?
     - prop: 전달 대상 컴포넌트의 인터페이스에 존재하는가?
     - 타입/인터페이스 필드: 정의를 찾을 수 있는가?
  3. **특히 주의할 패턴** — 직전 트랙(main 쪽)이 리팩토링(rename, 시그니처 변경, 함수 분할)을
     가한 파일에서 충돌이 났다면, rebase 트랙의 코드가 **리팩토링된 API에 맞게 조정되었는지**
     확인한다. 예: main에서 `pinnedDate()`→`pinnedStart()`로 rename → rebase 트랙의
     `isToday()` 정의가 `pinnedDate()`를 참조하고 있다면 `pinnedStart()` 기반으로 재작성 필요.
  4. 위 검증을 통과하지 못한 식별자가 하나라도 있으면 → 파일에서 수정 후 재확인.
     **절대 "git이 충돌 마커만 제거했으니 됐다"고 가정하지 말 것.**
     git은 양쪽 변경을 텍스트로 합칠 뿐, **로직 정합성은 검증하지 않는다**.

### 2) verify 재실행 (실패 시 원인 분석·수정)
- W에서 트랙의 검증을 **실제로 다시** 돌린다(rebase로 코드가 바뀌었을 수 있으므로 필수):
  - 컨테이너 검증 가능 트랙: `scripts/worktree-setup.sh T --docker-verify` 후
    `docker compose ... run --rm verify {typecheck,unit,smoke}` (메모리 [[worktree-live-verification]]).
  - 아니면 트랙 유형에 맞는 `bun test` / `pytest`.
- **실패 시**: 원인을 분석한다. 직전 머지가 유발한 **교차-통합 깨짐**(stale 참조·rename 누락 등,
  F42류)이면 W에서 직접 고치고 fixup 커밋 후 verify 재실행. 트랙 로직 자체의 회귀처럼 **판단이
  필요한 실패**면 멈춤 → 사용자에게 보고.

### 3) main으로 머지
- rebase로 feat/T가 main 위에 선형으로 올라가 있으므로 충돌 없이 머지된다.
- main 작업 트리에서 `git merge --no-ff feat/T` (추적성 위해 `--no-ff` 기본; merge 커밋 메시지에
  트랙 ID/요약).

### 4) 문서 마감 (이 시점에만 공유 파일 1회 쓰기)
- 루트 `aidlc-state.md` Track Registry 행: `active` → `merged`, Branch/Updated에 머지 sha 기록.
- `aidlc-docs/tracks/T/state.md`의 `**Status**:` → `merged → main <sha> (날짜)`.
- 글로벌 `aidlc-docs/audit.md`에 **한 줄 요약** append(기존 `- YYYY-MM-DD — **Tn merged** …` 포맷).
- 위 문서 변경을 별도 커밋(`docs(Tn): close track — merged (<sha>) …`).

### 5) 정리 (전체 cleanup)
- `git worktree remove W` (트리 clean 확인 후).
- `git branch -d feat/T` (머지 완료이므로 `-d` 성공). 서브모듈 era 잔재 없음(post-F35 monorepo).
- `.claude/worktrees/T` 잔존 산출물(__pycache__ 등) 정리.

### 6) 다음 트랙으로
- 다음 트랙의 rebase는 방금 들어간 T의 머지를 포함한 main 위로 올라간다 → 겹침/꼬임이 거기서
  드러나 동일 절차로 해결. 큐가 빌 때까지 반복.

---

## 멈춤 조건 (자율 진행 중 사람에게 넘길 때)
- rebase의 **의미적 충돌**(기계적으로 해소 불가).
- verify 실패가 **교차-통합 깨짐이 아니라** 트랙 로직 회귀로 판단될 때.
- base가 F35 이전 등 사전 게이트에 걸린 트랙(자동 제외했으나 사용자가 강행 요청 시 안내).
- worktree/브랜치 상태가 예상과 다를 때(예: feat/T에 미커밋 변경, detached HEAD).

각 멈춤은 **현재 트랙만** 보류하고, 나머지 큐는 사용자 결정 후 이어서 진행한다(이미 머지된
트랙은 롤백하지 않는다).

## 최종 보고
- 머지된 트랙(+sha), 보류된 트랙(+사유), 제외된 트랙(+사유)을 표로 요약.
- 정리된 worktree/브랜치, 갱신된 registry 행, append된 audit 라인 목록.

## 운영 규칙
- **단일 writer.** 각 트랙 state.md는 그 트랙만 쓴다. 루트 registry/audit는 이 명령이 머지
  시점에만 직렬로 쓴다(여기가 유일한 동시-쓰기 지점이고, 단일 실행이므로 안전).
- audit.md는 **append만**(전체 덮어쓰기 금지 — 중복 유발).
- 이미 머지된 트랙은 절대 되돌리지 않는다. 실패는 **현재 트랙에서** 멈추고 보고한다.
- 새 트랙 상태값 `merge-awaiting` 컨벤션: 트랙은 Build & Test 완료 후 자기 state.md의 Status를
  `merge-awaiting`으로 찍어 이 큐에 등록한다(레지스트리는 머지 전까지 `active` 유지).
