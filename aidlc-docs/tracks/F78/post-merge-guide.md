# F78 — Post-Merge Guide (이벤트-레이더 Tier1)

## 무엇이 바뀌나 (prod main 기준)
research 턴이 **임박 IPO + 매크로 촉매를 인지**한다. 이전엔 movers/earnings/sentiment(전부
universe 심볼 기반)만 봐서 SPCX 같은 신규 상장에 둔감했음.

1. **자동 push**: research 프롬프트 상단의 "Market signal brief"에 **"Imminent IPOs /
   catalysts"** 섹션이 추가됨(임박 US IPO, 규모순, 캡 8). universe 필터 없음 — 신규 종목도 노출.
2. **프롬프트 nudge**: Regime(step 2)에서 에이전트가 IPO 캘린더 + M&A/규제/매크로를 web으로
   top-down 스캔하고 영향·read-through를 `regime.md`에 기록하도록 지시. **"거래는 universe만"** 가드 포함.
3. **새 도구**: `python -m src.agent.tools ipo_calendar [--days N]`.

## 전제조건
- **`FINNHUB_API_KEY`** (기존 earnings와 동일 키 재사용). 없으면 IPO 섹션만 조용히 빠지고
  brief degraded에 `ipo:disabled` 표기 — 턴은 정상.
- **데몬 재시작** 필요(프롬프트·collector 코드 변경 반영).
- config 기본값 동작(추가 설정 불필요). 끄려면 `settings.yaml signals.sources.ipo_provider: none`.

## 실사용 검증 체크리스트
1. **도구 단독**: `python -m src.agent.tools ipo_calendar --days 30`
   → `{"imminent_ipos":[...], "degraded_sources":[...]}`. 정상이면 임박 IPO 배열(없으면 빈 배열 +
   degraded 비어있음). 키 없으면 `degraded_sources:["ipo:disabled"]`.
   - *주의*: 이 CLI는 `settings.trading.symbols` 설정로딩이 정상인 prod 데몬 env에서 실행할 것
     (worktree 단독 실행 시 기존 quirk으로 실패 — F61 `earnings_calendar`도 동일).
2. **brief에 노출**: 다음 research 턴 후 turn 로그/agent-trace에서 프롬프트 상단에
   "Imminent IPOs / catalysts" 섹션 확인. "정상"의 모습: `- SYM (회사명) YYYY-MM-DD EXCH ~$X.XB [status]`.
3. **regime.md 반영**: research 턴 후 `regime.md`에 임박 IPO/매크로 촉매에 대한 한 줄 이상의
   언급(섹터·심리·read-through). 없으면 nudge가 약한 것 — 문구 강화 검토.
4. **행동 가드**: 에이전트가 universe 밖 종목(IPO 티커)에 BUY를 쓰지 않는지 확인(여전히 universe만).

## 튜닝 노브 (`config/settings.yaml` → `signals:`)
- `ipo_horizon_days` (기본 5): 며칠 앞 IPO까지 볼지.
- `max_ipos` (기본 8): brief 섹션 최대 행 수(비대화 방지).
- `sources.ipo_provider`: `finnhub` | `none`(완전 비활성).

## 롤백
- 빠른 비활성: `signals.sources.ipo_provider: none` → 데몬 재시작(코드 롤백 불필요, 섹션·도구 무력화).
- 완전 되돌림: feat/F78 머지 커밋 revert. 순수 additive라 충돌 위험 낮음.

## 알려진 한계 / 비범위
- **인지 전용**: 에이전트는 IPO를 *못 산다*(universe 미포함). day-1 IPO 직접 매수는 의도적 제외
  (가격 이력 없어 ATR 기반 손절 불가). universe 동적 승급은 Tier2(별도 결정).
- **매크로 촉매는 프롬프트+web 의존**: IPO만 결정론적 push, M&A/규제/매크로는 에이전트의 web 스캔에 의존.
- Finnhub free tier `/calendar/ipo` 데이터 품질·커버리지에 종속(규모 미상 행은 후순위로 유지).
- MCP 도구화는 별도 병렬 트랙(F79 예정) — 본 트랙은 기존 CLI/brief 패턴 유지.
