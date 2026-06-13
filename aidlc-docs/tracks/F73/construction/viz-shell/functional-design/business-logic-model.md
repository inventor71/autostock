# F73 viz-shell — Business Logic Model

## L1. 경계 검사 알고리즘 (`checkBoundary` — 보안 핵심)

```text
입력: toolName, toolInput
출력: {behavior:"allow"} | {behavior:"deny", message}

1. toolName 분류:
   WRITE_TOOLS = {Write, Edit, NotebookEdit, MultiEdit(존재 시)}
   READ_TOOLS  = {Read, Glob, Grep}
   기타        → deny("tool not permitted in viz-shell")   # Bash, WebFetch, Task 등 전부

2. 대상 경로 추출: toolInput.file_path | .path | .pattern의 base dir
   경로가 없으면(예: Glob pattern만) → cwd 기준으로 간주

3. 정규화: abs = path.resolve(VIZ_SHELL_DIR, raw)
   존재하는 최근접 조상 디렉토리에 fs.realpathSync 적용 후 재조합
   (심볼릭 링크로 경계 밖 탈출 차단)

4. 판정:
   WRITE_TOOLS: abs가 GENERATED_DIR(= VIZ_SHELL_DIR/src/generated) 이하 → allow
                아니면 → deny("writes are restricted to src/generated/ — create the view file there")
   READ_TOOLS:  abs가 VIZ_SHELL_DIR 이하 → allow
                아니면 → deny("reads are restricted to the viz-shell directory")

5. 모든 deny: 스트림에 boundary-denied 이벤트 발행 (UI ⚠️) + 사유를 SDK에 반환
   (에이전트가 경계 안에서 재시도하도록 — fail-closed지만 회복 가능)
```

불변식: **deny-by-default** — 분류 불가 도구/경로는 전부 거부. 검사 로직에 예외
화이트리스트를 추가할 때는 반드시 테스트 케이스 동반(성공 기준 ③의 경계 거부 테스트).

## L2. 표면별 안전 읽기 (SafeRead)

### L2a. snapshot (생산자 원자적)
```text
readJsonFile(path, schema):
  raw = fs.readFile(path)          # ENOENT → null
  json = JSON.parse(raw)           # 실패 → null + warn 로그 (원자적 생산자라 정상 경로에선 미발생)
  return schema.parse(json)        # zod 실패 → null + warn (스키마 드리프트 신호)
```

### L2b. equity.jsonl (append-only)
```text
tailJsonl(path, schema, maxLines):
  buf = 파일 끝에서 청크 역방향 읽기 (전체 로드 회피; 파일 작으면 통읽기)
  lines = buf.split('\n')
  마지막 원소가 ''이 아니면(개행 미종결) → 미완성 라인으로 폐기   # torn-line 처리
  각 라인 JSON.parse + schema.parse — 실패 라인은 skip + 카운트
  return 최근 maxLines개
```

### L2c. positions/*.md (비원자 생산자 — stat-stable)
```text
readFileStable(path, retries=3):
  loop i in 1..retries:
    s1 = fs.stat(path)             # ENOENT → null
    content = fs.readFile(path)
    s2 = fs.stat(path)
    if s1.mtimeMs == s2.mtimeMs and s1.size == s2.size and s2.size == byteLength(content):
        return {content, mtimeMs: s2.mtimeMs, stale: false}
    sleep(50ms * i)                # 백오프
  return {content(마지막), mtimeMs, stale: true}   # fail-honest: 포기하되 표시는 함
```

## L3. 채팅 턴 라이프사이클 (명시적 단일 세션)

```text
POST /api/chat:
  1. session = SessionStore.load()            # viz-shell/.cache/session.json
  2. options = {
       cwd: VIZ_SHELL_DIR,
       permissionMode: "default",
       canUseTool: checkBoundary,
       resume: session.id ?? undefined,        # 첫 턴이면 새 세션
       env: sanitizeEnv(process.env),          # 스티어링 토큰류 제거
       appendSystemPrompt: VIEW_GENERATOR_CONTRACT (BR-7)
     }
  3. for await msg of query({prompt, options}):
       system/init   → session.id 미보유 시 msg.session_id 저장
       assistant 텍스트 → text-delta 스트림
       tool_use      → tool-activity 요약 스트림 (도구명 + 대상 상대경로)
       (denied는 L1에서 boundary-denied 발행)
  4. 스트림 종료. (HMR은 별개 채널 — 파일이 쓰였다면 dev 서버가 자동 반영)

New chat: SessionStore.reset() → 다음 턴은 resume 없이 시작.
동시성: 채팅 턴 in-flight 중 새 POST → 409 반환 (단일 운영자 전제, 큐잉 불필요).
```

## L4. 생성 뷰 발견·마운트 (자동 레지스트리)

```text
view-host:
  ctx = require.context('@/generated', false, /\.tsx$/)
  views = ctx.keys()
            .filter(k => !basename(k).startsWith('_'))     # _example.tsx 등 제외
            .map(k => ({ name: kebab→Title, mod: lazy(() => import(k)) }))
  렌더: 뷰당 탭. 탭 콘텐츠 = <ErrorBoundary><Suspense><View/></Suspense></ErrorBoundary>
  ErrorBoundary fallback: 뷰 이름 + 오류 요약 + "채팅으로 수정을 요청하세요" 안내
  (깨진 생성물 = 해당 탭만 죽음, 셸/다른 탭 무사)

표시 상태 (UAQ 결정 ③ — 파일과 분리):
  visibleState = localStorage["viz-shell.hidden-views"] = string[] (숨긴 파일명)
  탭 닫기(x) → 목록에 추가 (파일 무접촉)
  "숨긴 뷰 (n)" 메뉴 → 복원(목록에서 제거)
  파일 삭제 자체는 채팅 지시(SDK가 generated/ 내에서 수행)로만
```

## L5. 폴링/갱신
- 시드 Overview: tRPC react-query `refetchInterval: 5_000`.
- 생성 뷰: `_example.tsx`가 5s 폴링을 모범으로 제시 — 뷰가 자체 결정.
- 폴링은 로컬 파일 읽기라 데몬 무영향 (NFR-6). 윈도우 비활성 시 react-query 기본
  동작(focus 시 refetch)으로 자연 절전.
