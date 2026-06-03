# F6 console-sidebar-upgrade · Frontend Components (Functional Design)

> 콘솔(opencode 하드포크, SolidJS + OpenTUI). 변경 파일은 모두 `operator-console/cli/...` + `operator-console/src/...`.

## FC-1 — 폭 시그널/컨텍스트 (신규, FR-1)
- 위치: `routes/session/` (또는 작은 context 모듈). 반응형 `width` 시그널 + `loadWidth()`/`saveWidth()` 헬퍼.
- `sidebarWidth()`(현 정적)를 시그널 읽기로 대체. `index.tsx:243` `contentWidth` 메모가 같은 시그널 구독.

## FC-2 — DragHandle (신규, FR-1/Q4=A)
- 사이드바 좌측 경계의 얇은 수직 핸들 box(│, 1열), **`selectable={false}`**(critic #2 — 텍스트 선택 하이재킹 차단).
  `onMouseDown/onMouseDrag/onMouseDragEnd`.
- 드래그 중 `width = clamp(dims.width − e.x)`; 종료 시 디바운스 저장(FC-1). 활성 시 살짝 강조(theme.borderActive).
- 키보드 대체 없음(Q4=A). 캡처 거동은 라이브 스파이크(R1)로 확정.

## FC-3 — 사이드바 계정/성과 블록 (변경: `feature-plugins/sidebar/autostock.tsx`, FR-2/3/5)
- 상단 **계정 블록**: `eq $123,456 · cash $10,000 · PnL +$320 · 4 pos`. PnL 부호 색(success/error).
- **성과 줄**: `today  W 60% (3/5)  +$210` / 빈 상태 `today  no closed trades`.
- 신규 필드 부재 시 블록 숨김(BR-8). 기존 positions/orders/queued/events 유지.

## FC-4 — 가독성/스타일 (FR-5)
- 섹션 헤더/구분(`textMuted` 라벨), 숫자 우측정렬/강조, 빈 상태 문구. 기존 events 글리프/`wrapMode="word"` 톤 유지.
- 테마 색만 사용(하드코딩 색 지양). default-on/폭 기본값 불변(F5).

## FC-5 — 깊은 모니터링 (FR-4) — UI 아님(명령 경로) — critic #3
- 사이드바 UI 아님. **3-파일 변경**: `mcp-server.ts`(steer_read inputSchema), `parser.ts`(turns/decisions read 동사),
  `filedrop.ts`(monitor.json 리더), `steer-handler.ts`(verb 분기 — 현재 verb 무시·snapshot만 반환 수정). 데몬 발행은 BLM-5.
- 운영자는 NL로 호출 → opencode CORE read 게이트 → 요약 텍스트 반환. 사이드바에 상주시키지 않음.

## 변경 표면 요약 (critic 반영)
| 파일 | 변경 | FR |
|------|------|----|
| `routes/session/sidebar.tsx` | 폭 시그널화 + DragHandle(`selectable=false`) | FR-1 |
| `routes/session/index.tsx` | `contentWidth` 단일 폭 시그널 구독(F5와 공유 계약) | FR-1 |
| (신규) 폭 상태 context | load/save ui.json (sidebarVisible과 독립) | FR-1.1 |
| `feature-plugins/sidebar/autostock.tsx` | 계정/성과 블록 + 스타일 | FR-2/3/5 |
| `operator-console/src/{mcp-server,parser,filedrop,steer-handler}.ts` | `steer_read` view 분기 (4파일) | FR-4 |
| `src/agent/steering/runtime.py` (+ 신규 집계/발행 헬퍼) | snapshot account(=`equity_log.snapshot` 재사용)/round_trip(저빈도 fills) + monitor 발행 | FR-2/3/4 |
| `src/core/trades.py` 재사용 | `match_round_trips` (UTC→ET 변환은 신규 헬퍼) | FR-3 |
| 브로커 `get_fills` (F3 정렬 포트) | 저빈도 fills/activities 소스 | FR-3 |
