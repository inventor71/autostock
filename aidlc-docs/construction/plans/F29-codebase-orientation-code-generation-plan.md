# F29 Code Generation Plan — `codebase-orientation`

> **Track**: F29 · **Unit**: `codebase-orientation` (single unit)
> **Plan created**: 2026-06-02
> **Requirements**: `aidlc-docs/inception/requirements/F29-codebase-orientation.md`

## Unit Context
- **Single unit**: 모든 변경이 독립적이고 작음 (5 files, 2 languages)
- **No submodule changes**: `operator-console/src/`와 `operator-console/launcher/`는 parent repo
- **No new dependencies**
- **No F26 permission changes**

## Implementation Steps

### Step 0: Worktree ready ✅
- [x] Worktree `feat/F29` at `.claude/worktrees/F29` created
- [x] `.env` linked from main

### Step 1: 데몬 — 디렉터리 트리 생성 (`runtime.py`)
- [x] `src/agent/steering/runtime.py`: `SteeringRuntime`에 `_publish_codebase_tree()` 메서드 + `_walk_tree()` 헬퍼 추가
  - `$AUTOSTOCK_ROOT` 기준 `src/`, `operator-console/`, `config/`, `tests/`, `docs/`, `scripts/` 스캔
  - `__pycache__`, `.git`, `node_modules`, `.mypy_cache`, `.pytest_cache` 등 제외
  - 각 패키지별 한 줄 설명 + 주요 파일 포인터 하드코딩 사전
  - `{AUTOSTOCK_ROOT}` prefix + 상대경로로 트리 텍스트 생성
- [x] `start()`에서 1회 호출 → `self.channel.publish_codebase(tree_text)`

### Step 2: 데몬 — codebase.json 발행 (`channel.py`)
- [x] `src/agent/steering/channel.py`: `SteeringChannel`에 `codebase_file` 경로 + `publish_codebase(text: str)` 메서드 추가
  - `steering/codebase.json`에 atomic write (기존 `publish_snapshot`과 동일 패턴)

### Step 3: MCP — `/codebase` verb 추가 (`steer-handler.ts`)
- [x] `operator-console/src/steer-handler.ts`: `handleSteerRead`에 `if (draft.verb === "codebase")` 분기 추가
- [x] `operator-console/src/filedrop.ts`: `readCodebase()` 헬퍼 + `codebaseFile` 경로 추가

### Step 4: MCP tool description — `/codebase` 사용법 안내
- [x] `operator-console/src/mcp-server.ts`: `steer_read` 설명에 CODEBASE verb 추가
  - `/codebase` verb 설명 + "Use this FIRST when asked about autostock's code" 지침
  - `$AUTOSTOCK_ROOT` 기준 상대경로 참조 안내 포함
  - (config.ts 수정 대신 MCP tool description에 지침 통합 — opencode는 tool description을 system prompt의 일부로 표시)

### Step 5: Python 단위 테스트
- [x] `tests/test_codebase_tree.py`: 9 tests — 트리 prefix/내용/제외/설명/파일 + channel atomic write
  - 생성된 트리에 주요 디렉터리 포함 확인 (`src/`, `operator-console/`, `config/`)
  - 제외 패턴 확인 (`__pycache__` 없음, `.git` 없음, `node_modules` 없음)
  - `{AUTOSTOCK_ROOT}` prefix 포함 확인
  - 패키지 설명 포함 확인
  - `publish_codebase` atomic write + overwrite 확인

### Step 6: TS 단위 테스트
- [ ] `operator-console/test/`: submodule 미초기화로 TS test runner 사용 불가 (bun 의존성)
  - 변경은 기존 패턴과 동일한 단순 추가이므로 리스크 낮음
  - docker-verify attach smoke로 실사용 검증 권장

### Step 7: 전체 regression + docker-verify smoke
- [x] `python -m pytest tests/ -x -q` — 572 passed (563 baseline + 9 new), 0 failures
- [ ] `(cd operator-console/cli && bun run typecheck)` — submodule 미초기화, defer
- [ ] `pip check` — defer
- [ ] docker-verify attach smoke — user verification

---

## 파일별 변경 요약

| # | 파일 | 변경 | 신규/수정 |
|---|------|------|----------|
| 1 | `src/agent/steering/runtime.py` | `_publish_codebase_tree()` + `_walk_tree()` + `start()` 호출 | 수정 |
| 2 | `src/agent/steering/channel.py` | `codebase_file` + `publish_codebase()` | 수정 |
| 3 | `operator-console/src/steer-handler.ts` | `/codebase` verb 디스패치 | 수정 |
| 4 | `operator-console/src/filedrop.ts` | `codebaseFile` + `readCodebase()` | 수정 |
| 5 | `operator-console/src/mcp-server.ts` | `steer_read` description에 `/codebase` verb + 사용 지침 추가 | 수정 |
| 6 | `tests/test_codebase_tree.py` | 트리 생성 + channel 단위 테스트 (9 tests) | 신규 |
