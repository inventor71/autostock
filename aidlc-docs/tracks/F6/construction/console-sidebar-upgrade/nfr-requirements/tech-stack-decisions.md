# F6 console-sidebar-upgrade · Tech Stack Decisions

| 영역 | 결정 | 신규 의존성 |
|------|------|------------|
| 마우스 드래그 | OpenTUI `onMouseDown/Drag/DragEnd` (absolute `MouseEvent.x`) | 없음 (이미 사용) |
| 폭 영속화 | Node stdlib `fs` + XDG `~/.local/state/autostock-console/ui.json`, 원자적 쓰기(temp+rename) | 없음 |
| 반응형 폭 | SolidJS signal/context (이미 사용) | 없음 |
| FR-4 read | 기존 MCP 서버 `steer_read`에 `view` 인자 — `@modelcontextprotocol/sdk`/`zod`(핀됨) | 없음 |
| 계정/라운드트립 발행 | `runtime.publish_snapshot` 확장 + `match_round_trips` 재사용 | 없음 |
| monitor 발행 잡 | 기존 `scheduler.add_seconds_job` 패턴 | 없음 |
| 테스트 | bun(TS 헬퍼/파서) + tsgo 타입체크 + pytest(Python) + Hypothesis(dev, 순수함수) | 없음 |

**총평**: TS·Python 양측 **0 new runtime deps**. F4/F5 기조(신규 deps 최소)와 일관.
