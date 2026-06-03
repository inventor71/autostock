# F53 Code Generation Plan — MCP Position Thesis 노출

## Unit Context
- **Unit**: `mcp-position-thesis` (단일 유닛)
- **변경 파일**: 2개
- **구현**: MCP 서버(TypeScript) `steer_read` 핸들러에 `/thesis`, `/theses` 서브커맨드 추가
- **데몬 영향**: 없음 (데몬 변경 불필요 — MCP 서버가 `workspace/positions/` 직접 읽기)

## 아키텍처 참고
현재 `steer_read`는 TypeScript `handleSteerRead()`에서 동사(verb)를 디스패치하여 파일을 읽는 구조:
- `/status` → `fd.readSnapshot()` (`steering/snapshot.json`)
- `/turns` → `fd.readMonitor()` (`steering/monitor.json`)
- `/codebase` → `fd.readCodebase()` (`steering/codebase.json`)

동일한 패턴으로 `/thesis <SYMBOL>`, `/theses` 추가:
- `/thesis AAPL` → `workspace/positions/AAPL.md` 읽기
- `/theses` → `workspace/positions/*.md` 목록

## 구현 계획

### Step 1: `FileDrop`에 thesis 읽기 메서드 추가
**파일**: `operator-console/src/filedrop.ts`
- [ ] `readThesis(symbol: string): string | null` — `workspace/positions/<SYMBOL>.md` 읽기
- [ ] `listTheses(): string[]` — `workspace/positions/*.md` glob → symbol 목록
- [ ] workspace 디렉토리 경로 해결 (환경변수 또는 프로젝트 루트 기준)

### Step 2: `steer_read` 핸들러에 `/thesis`, `/theses` 디스패치 추가
**파일**: `operator-console/src/steer-handler.ts`
- [ ] `/thesis <SYMBOL>` — `draft.verb === "thesis"` → `fd.readThesis(symbol)`
- [ ] `/theses` — `draft.verb === "theses"` → `fd.listTheses()`
- [ ] 파일 없음/디렉토리 없음 케이스 처리 (fail-closed, SECURITY-15)

### Step 3: MCP 툴 description 업데이트 (선택적)
**파일**: `operator-console/src/mcp-server.ts`
- [ ] `steer_read` 툴 description에 `/thesis <SYMBOL>`, `/theses` 문서화

### Step 4: 단위 테스트
**파일**: 신규 또는 기존 테스트
- [ ] `/thesis AAPL` — thesis 파일 존재 시 markdown 내용 반환
- [ ] `/thesis UNKNOWN` — thesis 파일 없을 시 명확한 메시지 반환
- [ ] `/theses` — thesis 파일 목록 반환
- [ ] `/theses` — `workspace/positions/` 디렉토리 없을 시 빈 목록 반환

### Step 5: 라이브 검증
- [ ] 실제 데몬 환경에서 `steer_read /thesis AAPL` 실행 확인
- [ ] `steer_read /theses` 실행 확인

### Step 6: 회귀 테스트
- [ ] 기존 Python 테스트 스위트 전체 통과 확인
- [ ] TypeScript 빌드 통과 확인
