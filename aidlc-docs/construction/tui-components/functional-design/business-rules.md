# Business Rules — Unit B: tui-components (TypeScript)

## BR-1: 타임라인 바 높이 제약

- 타임라인 바는 **최대 2줄** (시간 눈금 1줄 + 마커 1줄)
- 채팅 영역 높이를 최소한으로 줄임
- `session_top` 슬롯이 비어있으면 높이 0

## BR-2: 마커 클릭 상호작용 (Q1=A)

- 마커 클릭 → 해당 턴의 오버레이 토글
- 같은 마커 재클릭 → 오버레이 닫기
- 다른 마커 클릭 → 기존 오버레이 닫고 새 오버레이 열기
- 오버레이 밖 클릭 또는 ESC → 오버레이 닫기
- 마우스 호버는 v1에서 미지원 (OpenTUI 호환성 확인 후 추가 가능)

## BR-3: 오버레이 배치 (Q3=A 플로팅 패널)

- `position="absolute"`, `zIndex=2000` (Dialog의 3000 아래)
- 앵커 위치: 클릭한 마커의 x좌표 기준
- 화면 경계 처리:
  - 오른쪽 넘침 → 왼쪽으로 이동
  - 아래쪽 넘침 → 위로 이동
- 최대 크기: 너비 60cols, 높이 15줄 (초과 시 내부 스크롤)
- 배경: `theme.backgroundPanel` + 테두리

## BR-4: 턴 오버레이 내용

| 영역 | 내용 |
|------|------|
| 헤더 | `[R1] Research · 09:30 · 45s · $1.20 · 3 decisions` |
| 요약 | `Research: BUY AAPL(0.8), BUY MSFT(0.6), HOLD GOOGL(0.5)` |
| 결정 목록 | 각 줄: `▲ BUY AAPL (0.8) Strong momentum...` (색상 코딩) |

- 결정의 심볼 텍스트는 클릭 가능 → 심볼 오버레이로 전환
- 결정 색상: BUY=green, SELL=red, HOLD=muted, ADJUST_STOP=yellow

## BR-5: 심볼 오버레이 내용

| 영역 | 내용 |
|------|------|
| 헤더 | `AAPL · $185.30 · +2.3%` |
| 포지션 | `Qty: 10 · Entry: $180.50 · P&L: +$48.00` |
| Thesis | `positions/AAPL.md` 내용 (일반 텍스트, 최대 10줄) |
| 최근 결정 | 마지막 3개 결정 (간략 포맷) |

- 파일 없으면 `"No thesis file"` 표시
- 포지션 없으면 (snapshot에 없음) 포지션 섹션 생략

## BR-6: 데이터 폴링 간격

- monitor.json: 1.5초 (기존 사이드바와 동일)
- snapshot.json: 필요 시에만 읽기 (심볼 오버레이 열 때, 매번 최신)
- thesis 파일: 오버레이 열 때 1회 읽기 (열려있는 동안 캐시)

## BR-7: 진행 중 턴 표시

- `current_turn`이 null이 아닌 경우:
  - 타임라인 바에 ◎ 마커 추가 (현재 시각 위치)
  - 색상: green, 0.5초 간격 깜빡임 (opentui 타이머)
  - 클릭 시 오버레이: "진행 중..." + 턴 타입 + 시작 시각만 표시

## BR-8: 타임라인 비어있을 때

- 오늘 턴이 없으면: `"No turns today"` 텍스트 표시
- daemon이 연결되지 않은 경우 (monitor.json 없음): `"Monitor disconnected"` 표시
- 시간축만 표시하고 마커 없음

## BR-9: 심볼 감지 범위 (v1)

- 턴 오버레이 내 결정의 심볼 → 클릭 가능
- 사이드바, 채팅 영역 → v1에서는 미지원 (향후 확장)

## BR-10: Security Baseline 준수

- **SECURITY-03**: thesis 파일 읽기 시 경로 검증 — `workspace/positions/` 하위만 허용 (path traversal 방지)
- **SECURITY-11**: 데이터 폴링은 읽기 전용, 어떤 파일도 쓰지 않음
- **SECURITY-15**: 파일 읽기 실패 시 graceful fallback (빈 데이터, 에러 표시), 크래시 안 함

## BR-11: 수정 파일 범위 (opencode 포크)

### 신규 (packages/tui-trading/)
- `package.json`, `tsconfig.json`
- `src/` 하위 전체 (hooks, components, utils, types)

### 수정 (packages/opencode/)
- `routes/session/index.tsx` — `session_top` 슬롯 추가 (1줄)
- `plugin/slots.tsx` 또는 `plugin/internal.ts` — 슬롯 등록
- `package.json` — tui-trading 의존성 추가

### 미수정
- 기존 `feature-plugins/sidebar/autostock.tsx` — v1에서는 건드리지 않음
- MCP 서버 (`mcp/index.ts`) — 변경 없음
- 기존 Dialog/Toast 시스템 — 그대로 사용
