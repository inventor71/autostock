# F73 viz-shell — Frontend Components

## 레이아웃 (UAQ 확정: 우측 고정 채팅 + 탭 뷰)

```text
+--------------------------------------------------+-----------------+
| TopBar:  AUTOSTOCK viz-shell      [숨긴 뷰 (2)▾]  | ChatPanel       |
+--------------------------------------------------+  [New chat]     |
| TabBar: [Overview] [PnL by Symbol ×] [Risk ×] +  |  ───────────    |
+--------------------------------------------------+  msg history    |
|                                                  |  ✎ tool line    |
|   <활성 탭 콘텐츠>                                  |  ⚠ denied line |
|   (ErrorBoundary + Suspense 래핑)                  |                |
|                                                  |  ───────────    |
|                                                  |  [input    ⏎]  |
+--------------------------------------------------+-----------------+
```
- ChatPanel 폭 360px, 접기 토글(접으면 콘텐츠 전폭). 다크 테마 기본 (트레이딩 관행).
- 차트 라이브러리: **recharts** (시드+생성 뷰 공용 — LLM 친숙도 최우선 기준).

## 컴포넌트 계층

```text
RootLayout (app/layout.tsx — tRPC/react-query Provider, 다크 테마)
└── DashboardPage (app/page.tsx)
    ├── TopBar
    │   └── HiddenViewsMenu        # localStorage 숨김 목록 복원 드롭다운
    ├── ViewTabs                   # 탭 상태 보유 (activeTab)
    │   ├── TabBar                 # Overview 고정 + GeneratedView별 탭 (× = 숨김)
    │   └── TabContent
    │       ├── OverviewTab        # 시드 (고정, 숨김 불가)
    │       │   ├── AccountCards   # equity/cash/buying_power 카드 3개
    │       │   ├── EquityCurve    # recharts LineChart (sinceDays 셀렉터 7/30/90)
    │       │   └── PositionsTable # 심볼/수량/평단/시가/미실현PL, 행 클릭→ThesisDrawer
    │       │       └── ThesisDrawer  # react-markdown 렌더 + stale ⚠️ 배지
    │       └── GeneratedViewHost  # lazy(import) + ErrorBoundary + Suspense
    └── ChatPanel
        ├── ChatHeader             # New chat 버튼 (확인 다이얼로그)
        ├── MessageList            # text / tool-activity(✎ 회색 1줄) / boundary-denied(⚠️ 황색)
        └── ChatInput              # textarea + 전송. in-flight 중 disabled(409 안내)
```

## 상태 관리
| 상태 | 위치 | 비고 |
|---|---|---|
| 서버 데이터 (snapshot/equity/positions/thesis) | tRPC react-query | refetchInterval 5s, focus refetch |
| activeTab | ViewTabs useState | 새 뷰 생성 감지 시 해당 탭 자동 활성 |
| hidden-views | localStorage (`viz-shell.hidden-views`) | 파일과 분리 — BR-13 |
| chat messages/status | useChat (Vercel AI SDK) | 커스텀 data part 2종 렌더 |
| 채팅 패널 접힘 | localStorage | 사소 — 세션 간 유지 |

## 핵심 인터랙션 플로우
1. **뷰 생성**: 채팅 입력 → 스트림(텍스트+✎ 라인) → SDK가 `generated/x.tsx` 작성 →
   HMR → ViewTabs가 새 키 감지 → 탭 추가 + 자동 활성 → 깨졌으면 그 탭만 fallback
   ("⚠️ 렌더 실패 — 채팅으로 수정 요청" + 오류 요약).
2. **경계 거부**: ⚠️ 라인이 채팅에 표시 (도구/경로/사유) — 에이전트는 보통 사유를 보고
   경계 안에서 재시도.
3. **탭 닫기(×)**: hidden-views에 추가 → 탭 제거. TopBar "숨긴 뷰 (n)▾"에서 복원.
   파일은 무접촉 (BR-13).
4. **New chat**: 확인 후 세션 리셋 — 뷰 파일/탭 상태는 영향 없음.
5. **데몬 산출물 부재**: Overview 각 위젯이 개별 placeholder ("snapshot 없음 — 데몬
   미가동?") — 전체 빈 화면 금지 (fail-honest, BR-8).

## API 연동 매핑
| 컴포넌트 | 엔드포인트 |
|---|---|
| AccountCards / PositionsTable | `portfolio.snapshot` |
| EquityCurve | `portfolio.equity({sinceDays})` |
| ThesisDrawer | `portfolio.thesis({symbol})` |
| ChatPanel | `POST /api/chat`, `POST /api/chat/reset` |
| 생성 뷰 (계약) | tRPC 훅 任意 조합 (BR-11, `_example.tsx` 모범) |

## 폼/검증
- ChatInput: 공백-only 전송 차단, max 4,000자(soft), in-flight 중 disabled.
- sinceDays 셀렉터: 고정 옵션(7/30/90) — 자유 입력 없음 (zod와 이중).
