# F25 타임라인 바 개선 — Requirements

> 질문 답변 반영 완료 (2026-06-01). 답변: Q1=B, Q2=B, Q3=C+D, Q4=C, Q5=A, Q6=A, Q7=A, Q8=A, Q9=A, Q10=A.
> **후속 결정 (12h 뷰)**: 24h → **12h 뷰**로 변경. 정규장 중심 12h 창(pre/after 각 일부 포함). 장 마감 KST 낮 시간에 열면 기본 = **다가올 세션**(오늘 밤, 빈 바).

## 1. Market-Aware 시간대 + 로컬 시간 표시 (FR-1)

**현재**: `timeline-layout.ts`에 `MARKET_OPEN_MIN = 9*60+30`, `MARKET_CLOSE_MIN = 16*60`로 US Eastern 하드코딩.
한국 트레이더가 미장을 거래하므로 한국 시간 기준으로 타임라인이 잘못 표시됨.

**요구사항** (Q1=B, Q2=B, Q9=A):
- **시간 표시 기준 = 사용자 로컬 시간 (Q1=B)**: 모든 턴 마커·tick 라벨·현재시간 indicator를 사용자 로컬 시간대(KST 등)로 변환해 표시. 9:30 ET → 23:30 KST.
- **마켓 시간 데이터**: daemon이 마켓 현지 시간(US Eastern)의 pre-market/정규장/after-hours 경계를 UTC 또는 ISO 기준으로 monitor.json에 전달. TS는 이를 로컬 시간으로 변환.
- **세 구간 시각 구분 (Q2=B)**: pre-market(4:00-9:30 ET), 정규장(9:30-16:00 ET), after-hours(16:00-20:00 ET)를 각각 다른 배경색/밝기로 표시.
- **마켓 경계선 (Q9=A)**: market open/close 시각에 세로 경계선 또는 색상 변경으로 경계 강조.
- **DST 처리**: 미국 서머타임에 따라 ET↔UTC 오프셋이 바뀌므로 daemon이 권위 있는 마켓 시각(zoneinfo America/New_York)을 계산해 전달. TS는 시간대 산술을 하지 않고 수신값만 로컬 변환.

> **⚠️ 자정 넘김 (FD에서 구체화)**: 로컬 시간(KST) 기준이면 정규장(23:30~06:00 KST)과 after-hours(~10:00 익일 KST)가 자정을 넘어 이틀에 걸침. "거래 세션" = 한 거래일(ET date)의 마커들을 어떻게 24시간 바에 배치할지(ET date 기준 묶음 + 로컬 라벨)는 Functional Design에서 확정.

## 2. 24시간 뷰 + 날짜 네비게이션 (FR-2)

**현재**: 현재시간 ± 여유분만큼의 range를 계산해 표시. 하루 전체를 보지 못하고, 이전 날짜 조회 불가.

**요구사항** (Q3=C+D, Q4=C, Q6=A, Q7=A, Q8=A, + 12h 뷰 후속 결정):
- **12시간 뷰 (정규장 중심)**: 24h가 아니라 **정규장(9:30~16:00 ET = 23:30~06:00 KST 서머타임)을 중심에 둔 12h 창**. pre-market·after-hours 각 일부를 포함. KST 낮 시간(미장 0 활동)의 빈 공간을 없애고 마커 해상도 2배 확보.
  - 12h 창의 정확한 경계(예: 18:00~06:00 KST vs 정규장±여유)는 DST를 고려해 daemon이 계산한 세션 경계 기준으로 Functional Design에서 확정.
- **기본 세션 (장 마감 시)**: 미장이 안 열린 KST 낮 시간(예: 14:00)에 타임라인을 열면 기본으로 **다가올 세션**(오늘 밤, 아직 빈 바)을 표시. 장중에는 현재 진행 세션을 표시.
- **날짜 네비게이션 (Q3=C+D)**:
  - 키보드: `←` `→` 로 이전/다음 날짜, `T`로 Today
  - 마우스: 타임라인 바 안에 `<` `Today` `>` 텍스트 버튼
  - 채팅 명령어: `/timeline 2026-05-30` slash command로 특정 날짜 이동
- **히스토리 범위 (Q4=C)**: 무제한 — turns.jsonl이 존재하는 모든 ET date 조회 가능. 용량 관리는 사용자 책임.
- **날짜 변경 데이터 흐름**: 날짜 변경 시 해당 ET date의 턴/intervention 데이터를 turns.jsonl·human_directives.jsonl에서 date 필터링해 제공. monitor.json은 현재 보고 있는 날짜의 데이터를 담거나, 별도 조회 경로 제공 (FD에서 확정).
- **마커 밀집 (Q6=A)**: 겹쳐도 개별 문자로 표시 (현재 방식 유지).
- **키보드 단축키 (Q7=A)**: 날짜 이동(`←` `→` `T`)만. 마커 점프·필터 토글 없음.
- **주말/공휴일 (Q8=A)**: 빈 24시간 바 + "No trading activity" 표시. 자동 건너뛰기·캘린더 조회 없음.

## 3. Human Intervention 마커 (FR-3)

**현재**: agent turn(research, intraday, wake, eod, reconcile)만 마커로 표시됨.
Human steering 명령(수동 매매, pause, flatten 등)은 `human_directives.jsonl`에 기록되지만 타임라인에 안 보임.

**요구사항** (Q5=A):
- **표시 범위 = 거래만 (Q5=A)**: human buy/sell/flatten/cancel 주문만 타임라인 마커로 표시. pause/resume/halt/kill·note/directive/approve/reject 등은 제외.
- `human_directives.jsonl`(또는 intervention 기록)에서 거래성 명령을 필터링해 마커로 표시.
- Human 마커는 agent turn 마커와 시각적으로 구분 (다른 glyph/색상).
- 마커 클릭 시 intervention 상세(command verb, symbol, 결과)를 overlay로 표시.
- monitor.json에 `interventions` 블록 추가 (timestamp, verb, symbol, result) — 거래성 명령만.

## 데이터 흐름

```
daemon (Python)
  ├── turns.jsonl → monitor.json { turns: { recent: [...] } }         # FR-1, FR-2
  ├── human_directives.jsonl → monitor.json { interventions: [...] }   # FR-3
  ├── config/settings.yaml → monitor.json { market: { open, close } }  # FR-1
  └── date param → monitor.json date-filtered turns                    # FR-2

console TUI (TypeScript)
  ├── useMonitorData() → polling monitor.json
  ├── TimelineBar: 24h layout + market-hours highlight
  ├── intervention markers (new glyph: ✚ or ✎)
  └── date nav controls (< Today >)
```

## 관련 파일

| Layer | File | Change |
|-------|------|--------|
| TS | `timeline-layout.ts` | MARKET_OPEN/MARKET_CLOSE → monitor.json에서 동적 수신, 24h layout |
| TS | `timeline-bar.tsx` | 24h layout, 3-구간 배경 + 마켓 경계선, intervention markers, 날짜 네비 UI(`< Today >`) + 키보드(`← → T`) |
| TS | `types.ts` | `InterventionRecord`, `MarketHours`(pre/regular/after 경계, 로컬 변환용 ISO) 타입 추가 |
| TS | `format.ts` | intervention glyph/color, 로컬 시간 변환 헬퍼 |
| TS | session/index.tsx | `/timeline <date>` slash command 등록, 키보드 핸들러 바인딩 |
| Python | `runtime.py` | `_turns_summary` date 필터(임의 ET date), interventions 블록(거래만), market hours(zoneinfo ET) 추가 |
| Python | `modes/agent.py` | market hours(zoneinfo America/New_York, DST-aware)를 runtime에 주입 |
| Python | `commands.py` | 거래성 intervention 발생 시 기록 (runtime이 human_directives.jsonl polling) |

## 미해결 (Functional Design에서 확정)
- **12h 창 경계 + 자정 넘김 세션 모델**: 정규장 중심 12h 창의 정확한 시작/끝(DST별), "ET date 거래 세션"을 12h 바에 어떻게 배치하고 날짜 라벨을 어떻게 붙일지. after-hours 06:00~10:00 KST 일부가 창 밖으로 나가는 처리.
- **과거 날짜 조회 경로**: monitor.json에 현재 날짜 데이터만 담을지, 날짜 파라미터로 조회할지, 별도 read 채널을 둘지.
- **Human intervention 데이터 소스**: `human_directives.jsonl`에 거래 명령이 충분한 필드(verb/symbol/result/ts)로 기록되는지 확인 — 부족하면 기록 확장 필요.
