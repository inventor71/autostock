---
description: 완료된 트랙들을 한 곳에서 순차 머지 — merge-awaiting 큐를 main 위로 차례로 rebase·verify·merge·cleanup (꼬임 방지)
argument-hint: "[선택: 트랙 ID 필터(F38 등, 쉼표 구분) — 비우면 모든 merge-awaiting 트랙을 큐로]"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash(git status:*), Bash(git worktree list:*), Bash(git worktree remove:*), Bash(git log:*), Bash(git diff:*), Bash(git merge-base:*), Bash(git rev-list:*), Bash(git branch:*), Bash(git rebase:*), Bash(git merge:*), Bash(git -C:*), Bash(git pull --rebase:*), Bash(git checkout:*), Bash(git clean:*), Bash(git stash:*), Bash(scripts/worktree-setup.sh:*), Bash(scripts/verify.sh:*), Bash(docker compose:*), Bash(bun test:*), Bash(pytest:*)
---

# /ai-dlc-merge — 완료 트랙 순차 머지 오케스트레이터

여러 트랙을 worktree로 **동시에** 개발하다 각자 main으로 머지하면 서로 겹쳐 꼬인다
(stale base 위 브랜치, 공유 파일 registry/audit 경합, 교차-통합 깨짐 — 예: F37 머지 후
잔존 참조 크래시를 F42 핫픽스로 수습). 이 명령은 **단 한 곳(main 작업 트리)에서만** 실행되어
**merge-awaiting 트랙 전체를 하나의 큐로 보고 차례로** 머지한다. 단일 실행 지점이므로 공유 파일
경합이 락 없이 자연 직렬화되고, 각 트랙은 **직전 머지가 반영된 main 위로 다시 rebase**되어
꼬임이 머지 전에 그 자리에서 드러나 해결된다.

스코프 필터: $ARGUMENTS (비어 있으면 모든 merge-awaiting 트랙)

## 핵심 전제: main 작업 트리는 "깨끗"하지 않고 "정상 노이즈만"이면 된다

여러 트랙을 동시에 돌리면 main 작업 트리에는 **active 트랙들의 문서 변경**이 항상 떠 있다
(`aidlc-docs/tracks/<id>/` 아래 미커밋/untracked 문서, 공유 레지스트리 편집 등). 이건 정상이며
**하드 클린의 대상이 아니다**. 머지는 이 노이즈를 통째로 비우길 요구하지 않는다 — 대신 변경을
**소유 트랙**으로 분류해서, 정체불명(미등록·비active) 변경만 차단하고, active 트랙의 변경은
**그 트랙을 머지할 때 반영**한다. (이전 버전은 "미커밋 변경이 있으면 무조건 중단"이었으나,
동시-트랙 환경에서는 항상 걸려서 쓸 수 없었다 — 그 규칙을 아래 triage로 대체한다.)

## 실행 전제 (blocking)
- **main 작업 트리에서, 단일 인스턴스로만 실행.** worktree 안이거나 `/ai-dlc-merge`가 이미
  돌고 있으면 중단. (동시성 가드는 "한 곳에서만 돈다"는 이 전제 자체다 — 별도 락 없음.)
- 미커밋 변경은 **단계 0a triage로 분류**한다. 정체불명 변경이 없으면 진행(하드 클린 불필요).
- 문서는 한국어 기본. 애플리케이션 코드는 워크스페이스 루트, 문서는 `aidlc-docs/`에만.
- 사용자 입력/승인은 글로벌 `aidlc-docs/audit.md`에 **append**(덮어쓰기 금지).

---

## 단계 0a — 작업 트리 Triage (정체불명 변경만 차단)

머지를 시작하기 전에 main 작업 트리의 미커밋 상태를 **소유자별로 분류**한다.

1. `git status --porcelain`로 변경/untracked 경로 전체를 수집한다.
2. 각 경로를 소유자로 매핑한다:
   - `aidlc-docs/tracks/<id>/**` → **트랙 `<id>` 소유**.
   - 공유 루트 파일(`aidlc-docs/aidlc-state.md`, `aidlc-docs/audit.md`) → **공유**.
   - 그 외 전부(워크스페이스 루트 애플리케이션 코드, `aidlc-docs/` 밖의 무엇이든,
     트랙 디렉터리 밖의 파일) → **미상(foreign)**.
3. 레지스트리(루트 `aidlc-docs/aidlc-state.md`)와 대조해 판정한다:
   - **미상(foreign) 경로가 하나라도 있으면 → 중단.** 목록을 제시하고 사용자에게 처리(커밋/되돌리기/
     트랙 귀속)를 요청한다. 머지 오케스트레이터는 출처 불명 변경을 절대 삼키지 않는다.
   - 소유 트랙이 **레지스트리에 없거나**, 있더라도 **Status가 `active`가 아니면**(merged·abandoned·
     paused 등) → **중단**하고 보고. ("active하지 않은 트랙의 변경점"은 곧 작업 트리 오염 신호다.)
   - 남은 변경이 **공유 파일 + active 트랙 문서뿐**이면 → **통과**. 이 노이즈는 정상이며
     비우지 않는다. 각 active 트랙의 변경은 그 트랙을 머지하는 단계에서 반영된다(단계 1·4).
4. triage 결과(통과/차단 사유 포함)를 `aidlc-docs/audit.md`에 한 줄 append한다.

> 한 줄 요약: **active 트랙·공유 파일의 노이즈는 OK, 정체불명·비active 변경은 STOP.**

---

## 단계 0b — Merge 큐 구성 + 사용자 확인 (🛑 유일한 승인 게이트)

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
   작업 트리 노이즈(머지 대상 아님, 그대로 둠): F58 문서(active), F33 문서(active)
   ```
   - 사용자가 승인하면 **이후는 자율 진행**(아래 멈춤 조건에서만 정지).
   - 승인/선택을 `aidlc-docs/audit.md`에 append.
   - merge-awaiting 트랙이 없으면 "머지할 트랙 없음"으로 종료.

---

## 단계 1..N — 트랙별 순차 머지 루프 (승인된 순서대로)

각 트랙 `T`(worktree `W`, 브랜치 `feat/T`)에 대해 순서대로:

### 0) 트랙 T 소유 작업-트리 노이즈 정돈 (머지 직전)
- 트랙 T의 **권위본(authoritative) 문서는 feat/T**다(worktree W의 단일 writer가 작성한 것).
  main 작업 트리에 떠 있는 T 소유의 미커밋/untracked 문서는 feat/T 머지로 들어올 내용으로
  **갈음된다** — 이게 "머지할 때 해당 트랙을 반영한다"의 실제 메커니즘이다.
- `git merge feat/T`가 untracked 파일과 부딪히지 않도록, **T 소유 경로(`aidlc-docs/tracks/T/`)의
  main-tree 잔여물만** 비운다(예: tracked는 `git checkout -- <path>`, untracked는
  `git clean -fd aidlc-docs/tracks/T/`). **다른 트랙의 노이즈는 절대 건드리지 않는다.**
- ⚠️ **정보 손실 방지(judgment)**: 비우기 전에, main-tree 잔여물에만 있고 feat/T에는 없는 내용이
  있는지 확인한다(`git -C W show feat/T:<path>` 비교 또는 diff). feat/T가 권위본이면 그대로 비우고,
  잔여물 쪽에 누락 내용이 있으면 **멈춤** → 사용자에게 어느 쪽을 채택할지 묻는다.

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
  트랙 ID/요약). 단계 1-0에서 T 소유 노이즈를 정돈했으므로 untracked 충돌 없이 진행된다.

### 4) 문서 마감 + 공유 파일 반영 (이 시점에만 공유 파일 1회 쓰기)
- 루트 `aidlc-state.md` Track Registry에서 **T 행만** `active` → `merged`로 바꾸고 Branch/Updated에
  머지 sha를 기록한다. **다른 active 트랙의 행·등록은 그대로 보존**한다(작업 트리에 그들의
  미커밋 레지스트리 편집이 떠 있어도 건드리지 않음 — 그건 그 트랙들 소유다).
- `aidlc-docs/tracks/T/state.md`의 `**Status**:` → `merged → main <sha> (날짜)`.
- 글로벌 `aidlc-docs/audit.md`에 **한 줄 요약** append(기존 `- YYYY-MM-DD — **Tn merged** …` 포맷).
- **close 커밋**: 위 변경을 하나의 커밋(`docs(Tn): close track — merged (<sha>) …`)에 담되,
  **스테이징 범위를 T 관련 + 공유 파일로 한정**한다 — 즉 `aidlc-docs/tracks/T/`, 그리고 공유
  `aidlc-state.md`/`audit.md`만 stage(`git add`로 명시 경로). 다른 트랙의 미커밋 노이즈가
  이 커밋에 섞이지 않게 한다. (요구사항: 공통 파일은 머지가 끝난 뒤 `merged`로 갱신해 커밋에 포함.)

### 5) 정리 (전체 cleanup)
- `git worktree remove W` (트리 clean 확인 후).
- `git branch -d feat/T` (머지 완료이므로 `-d` 성공). 서브모듈 era 잔재 없음(post-F35 monorepo).
- `.claude/worktrees/T` 잔존 산출물(__pycache__ 등) 정리.

### 6) 다음 트랙으로
- 다음 트랙의 rebase는 방금 들어간 T의 머지를 포함한 main 위로 올라간다 → 겹침/꼬임이 거기서
  드러나 동일 절차로 해결. 큐가 빌 때까지 반복.

---

## 멈춤 조건 (자율 진행 중 사람에게 넘길 때)
- 단계 0a triage에서 **정체불명(foreign) 변경** 또는 **비active/미등록 트랙 변경** 발견.
- 단계 1-0에서 main-tree 잔여물이 feat/T에 없는 내용을 담고 있어 **권위본 판단이 필요**할 때.
- rebase의 **의미적 충돌**(기계적으로 해소 불가).
- verify 실패가 **교차-통합 깨짐이 아니라** 트랙 로직 회귀로 판단될 때.
- base가 F35 이전 등 사전 게이트에 걸린 트랙(자동 제외했으나 사용자가 강행 요청 시 안내).
- worktree/브랜치 상태가 예상과 다를 때(예: feat/T에 미커밋 변경, detached HEAD).

각 멈춤은 **현재 트랙만** 보류하고, 나머지 큐는 사용자 결정 후 이어서 진행한다(이미 머지된
트랙은 롤백하지 않는다).

## 최종 보고
- 머지된 트랙(+sha), 보류된 트랙(+사유), 제외된 트랙(+사유)을 표로 요약.
- 정리된 worktree/브랜치, 갱신된 registry 행, append된 audit 라인 목록.
- **그대로 남겨둔 작업-트리 노이즈**(아직 active인 다른 트랙들의 미커밋 문서)도 명시 — 의도된
  잔여물임을 분명히 한다.

## 운영 규칙
- **작업 트리는 "정상 노이즈만"이면 OK.** active 트랙·공유 파일의 미커밋 변경은 비우지 않는다.
  정체불명·비active 변경만 차단(단계 0a). 하드 클린 요구는 폐기됐다.
- **단일 writer.** 각 트랙 state.md는 그 트랙만 쓴다. 루트 registry/audit는 이 명령이 머지
  시점에만 직렬로 쓴다(여기가 유일한 동시-쓰기 지점이고, 단일 실행이므로 안전).
- **공유 파일은 머지 후 반영.** T를 머지한 뒤에만 `aidlc-state.md`의 T 행을 `merged`로 바꿔
  close 커밋에 포함한다. 다른 active 트랙의 행/노이즈는 보존하고, close 커밋 스테이징은
  T 관련 + 공유 파일로 한정한다.
- audit.md는 **append만**(전체 덮어쓰기 금지 — 중복 유발).
- 이미 머지된 트랙은 절대 되돌리지 않는다. 실패는 **현재 트랙에서** 멈추고 보고한다.
- 새 트랙 상태값 `merge-awaiting` 컨벤션: 트랙은 Build & Test 완료 후 자기 state.md의 Status를
  `merge-awaiting`으로 찍어 이 큐에 등록한다(레지스트리는 머지 전까지 `active` 유지).
