# F95 — Post-Merge Guide (실사용 검증)

## prod 브랜치에서 무엇이 바뀌나
- 운영자 콘솔(TUI)에서 **심볼을 클릭하면 floating panel(SymbolOverlay)**이 뜨고, 맨 위에 **실시간 시세가 항상** 표시된다(보유하지 않은 종목도). 그 아래 현행(포지션 수량/진입/PnL · thesis · 최근 결정)은 **있으면** 표시, 없으면 생략.
- 새 클릭 진입점: **intervention 오버레이의 심볼**을 클릭 가능(기존 turn 오버레이 심볼 클릭은 그대로).
- 데몬이 `steering/quotes.json`을 **2초 주기**로 기록(클릭-후보 = 보유 ∪ 미체결 주문 ∪ 최근 결정/개입 심볼, 상한 30).

## 전제조건
- **데몬 재시작 필요**: 새 스케줄 잡(`steering_quotes`)과 `refresh_quotes`는 데몬 부팅 시 등록된다. 머지 후 데몬을 재시작(런처가 코드 스큐 감지해 자동 재시작하거나 `scripts/prod-run.sh down <name> && up <name>`).
- **env/config 변경 없음**: 신규 env 키 없음. 시세 provider는 기존 `settings.data.provider`(기본 `yfinance`; `ALPACA_*` 설정 시 Alpaca 실시간). 새 볼륨/포트/사이드카 없음.

## 실사용 검증 체크리스트
1. **데몬 재시작 후 quotes.json 생성 확인**
   - `steering/quotes.json`이 나타나고 ~2초마다 `published_at`/`updated`가 갱신되는지: 인스턴스 steering 경로에서 `watch -n1 cat steering/quotes.json`(또는 파일 mtime).
   - 보유 종목이 있으면 `quotes`에 그 심볼의 `{"price":..,"ts":..}`가 보여야 함. 조회 실패 심볼은 `{"error":"no_data"}`.
   - **정상 모습**: `{"quotes":{"AAPL":{"price":316.2,"ts":"…"}}, "provider":"YFinanceProvider", "updated":"…", "published_at":"…"}`.
2. **콘솔에서 클릭 → 패널 시세**
   - TUI에서 turn 오버레이를 열고 결정 심볼 클릭, 또는 intervention 오버레이의 심볼 클릭 → SymbolOverlay가 뜨고 헤더 아래 `"$<price> · as of HH:MM:SS"`.
   - 미보유 종목도 시세가 떠야 함(현행 섹션은 비어도 정상).
   - 조회 전/직후 잠깐 `"시세 조회 중…"`, provider 실패 시 `"시세 없음"` — **패널은 항상 열림**.
3. **as-of 신선도**: 표시 시각이 대략 현재(±수초). yfinance는 지연 시세일 수 있음 — as-of가 이를 정직하게 드러냄(허위 실시간 아님).
4. **멀티 인스턴스(운영 시)**: 인스턴스별 `steering/quotes.json`이 각자 격리되는지(교차 오염 없음). 지속 websocket 연결이 없으므로 인스턴스를 여러 개 띄워도 시장데이터 연결 충돌 없음.

## 튜닝 노브
- **갱신 주기**: `src/trading/modes/agent.py`의 `add_seconds_job(self.steering.refresh_quotes, 2, "steering_quotes")` — provider가 레이트리밋되면 값을 키운다(예 3~5s).
- **후보 상한/TTL**: `src/agent/steering/quotes.py`의 `DEFAULT_CANDIDATE_CAP`(30), `DEFAULT_TTL_SEC`(10).
- **실시간성 향상**: `settings.data.provider`를 `alpaca`로(ALPACA_* 데이터 키) 두면 지연 없는 시세.
- **TUI 폴링**: `use-quote.ts`의 `useQuote(..., intervalMs=1500)`.

## 롤백
- 기능 무력화: `steering_quotes` 스케줄 잡 한 줄 제거(또는 주기 0) → `quotes.json` 미생성 → 패널은 `"시세 조회 중…"`만, 나머지(현행/thesis/결정 + 기존 클릭)는 그대로. 기존 오버레이/turn 동작 무영향.
- 완전 되돌리기: 트랙 머지 커밋 revert. env/스키마/외부 상태 변경이 없어 부작용 없음.

## 알려진 한계 / 범위 밖
- **채팅 심볼 클릭**은 미포함(HARD — opaque native markdown 렌더러). 별도 후속.
- **초 이하 스트리밍(공유 사이드카)**은 미채택 — 멀티 인스턴스에서 초이하 신선도가 필요해질 때의 후속 옵션(requirements ADR §9-B).
- 시세 등락(전일 대비)·bid/ask는 v1 미표시(price+as-of만). 데이터 비용 절감.
- 라이브 데몬에서의 주기적 quotes.json 기록 + TUI 실렌더 클릭은 위 체크리스트로 최종 확인(단위/통합/데이터-플레인 스모크는 통과).
