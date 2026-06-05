# F61 Post-Merge Guide — 머지 후 prod에서 기대할 것 & 실사용 확인 체크리스트

> 대상: `feat/F61` → `main` 머지 직후. 이 트랙이 prod(데몬)에서 무엇을 바꾸고, 실사용에서
> 무엇을 눈으로 확인해야 하는지. (설계/검증 상세는 같은 디렉터리의 functional-design/,
> build-and-test/ 참조.)

---

## 0. 한 줄 요약
리서치 턴이 시작될 때 **"시장에서 방금 무엇이 움직였고 그게 어떤 종목으로 번지는지"**(무버 +
종목 간 read-through + 임박 실적)를 담은 **브리프를 자동으로 먼저 보게** 되고, 에이전트가
필요 시 직접 부를 수 있는 **툴 3종**(`movers` / `readthrough` / `earnings_calendar`)이 생긴다.

## 1. 전제 (머지 시점 상태)
- **FINNHUB_API_KEY**: prod `.env`에 이미 존재 ✅ (실적 캘린더용). 없어도 크래시 없이 그 섹션만 비활성.
- **ALPACA 키**: 기존 보유 ✅ (뉴스=Benzinga). 실패 시 yfinance 폴백.
- **데몬 코드/설정 반영**: 머지 후 데몬이 **새 코드+`config/settings.yaml`의 `signals:` 블록**을
  로드해야 한다. 버전 스큐 자가치유(F43)로 자동 재시작되거나, 운영자가 데몬을 재기동.
- **prod 멀티에이전트 구성**: 현재 `multi_agent: enabled=true, mode=sequential, n_agents=3`.
  → sequential은 단일 연속 세션이라 **브리프가 라운드1에 주입돼 debate/synthesis까지 전파**된다(정상).
  (mode를 `parallel`로 바꿔도 discovery 서브에이전트까지 브리프가 가도록 F61에서 배선됨.)

## 2. 머지 후 prod에서 기대할 동작
1. **리서치 턴 프롬프트 앞단에 "## Market signal brief"가 붙는다** — 그날의 무버(유니버스+
   bellwether ETF), read-through 경고(예: `AVGO -15% (guidance miss) → NVDA, AMD, MRVL`),
   임박 실적 목록. 신호가 하나도 없는 조용한 날엔 브리프가 비어 prepend가 생략된다.
2. **신규 툴 3종**(에이전트/운영자가 `python -m src.agent.tools <name>`):
   - `movers` — 임계 초과 무버 + read-through 경고(JSON)
   - `readthrough <SYM>` — 그 종목이 번질 유니버스 피어(정적 피어맵, 네트워크 불필요)
   - `earnings_calendar [--days N]` — 유니버스/보유 임박 실적
3. **새 config 섹션** `signals:` — 임계·피어맵·bellwether·소스 토글·캐시/타임아웃(아래 §5).
4. **성능**: 리서치 턴 시작 시 1회 가격 스캔(유니버스+bellwether ≈ 150종목, 30s 바운드, 결과
   300s 캐시). 인트라데이/웨이크 등 latency-critical 경로는 **영향 없음**(리서치 턴에만 작동).
5. **무해한 기본**: `signals.enabled=false`로 두면 브리프 push가 꺼진다(툴은 계속 동작).

## 3. 실사용 확인 체크리스트 (머지 직후 권장 순서)

### A. 툴 라이브 스모크 (즉시, 가장 쉬움)
```bash
python -m src.agent.tools readthrough AVGO      # 순수 — 즉답, 반도체 피어 22종
python -m src.agent.tools readthrough SMH       # bellwether도 피어가 나와야 함(빈 배열 X)
python -m src.agent.tools earnings_calendar     # Finnhub 실호출 — 유니버스 임박 실적
python -m src.agent.tools movers                # 유니버스+bellwether 가격 스캔(수십 초 가능)
```
- **기대**: `readthrough`는 빈 `peers_universe`가 아니어야 함(특히 bellwether). `earnings_calendar`/
  `movers` 출력에 `degraded_sources`가 비어 있으면 소스 정상. 채워져 있으면 어느 소스가 죽었는지 명시됨.
- **확인 포인트**: 키가 잘못됐거나 네트워크가 막혀도 **크래시 없이** `degraded_sources`에 표식만
  남고 나머지는 나오는지(fail-honest).

### B. 다음 morning research 턴에서 브리프가 실제로 들어갔는지
- 운영자 콘솔 **타임라인의 research 마커 오버레이**(F41)에서 라운드1 평가 텍스트/추론에
  무버·read-through 언급이 보이는지.
- 또는 워크스페이스의 `turns.jsonl` / agent report에서 라운드1 입력 맥락 확인.
- **기대**: 에이전트가 "오늘 X가 −n%라 피어 Y 점검" 식으로 브리프를 **참조**하면 push가 먹은 것.

### C. 에이전트가 브리프를 "행동"으로 옮기는지 (핵심 목적)
- `decisions.jsonl` / `positions/<SYM>.md` 의 rationale에 read-through·무버를 근거로 든 결정이
  나오는지(예: bellwether/실적 종목의 피어를 HOLD 재점검하거나 신규 후보로 검토).
- **이게 F61의 본질**: 브리프가 떠도 에이전트 판단은 LLM 몫(정적맵은 후보만 제시). 며칠치
  리서치 턴을 모아 "큰 변동→피어 점검"이 결정에 반영되는 빈도를 본다.

### D. 동기였던 시나리오 재현 관찰
- 다음에 **bellwether/실적발 급락(AVGO류)**이 실제로 나면, 그날 `movers`에 그 종목이 잡히고
  `readthrough`/브리프에 피어 경고가 떠서 **에이전트가 그 영향을 고려**하는지 확인.
- (참고) **애프터아워스 실적 갭은 다음 정규장 일봉 전까지 안 잡힘** — 이번 트랙 범위 밖(§6).

### E. 비용/안전 가드
- **토큰**: 기본 `pytest`/CI는 토큰 0(Tier-2 LLM 하니스는 `-m "not manual"`로 제외). 정기 실행에
  LLM 비용이 새지 않는지 확인.
- **지연**: 리서치 턴 시작이 눈에 띄게 느려지지 않는지(스캔 30s 상한 + 캐시). 느리면 로그에
  `signals: price scan exceeded ...s budget` 가 뜨고 그 턴은 무버 없이 진행(degrade).

## 4. 어디를 보면 되나 (관측 지점)
- **로그**: `signals:` 프리픽스 경고 — `price scan exceeded budget`, `news lookup failed`,
  `Finnhub ... failed`, `bellwether ... also in universe` 등.
- **툴 출력의 `degraded_sources`**: 어느 소스가 비활성/실패했는지 가장 빠른 단서.
- **타임라인 오버레이(F41)**: research 턴 라운드별 평가.

## 5. 튜닝 노브 (`config/settings.yaml` → `signals:`)
| 키 | 의미 | 시드 |
|---|---|---|
| `price_pct` / `vol_ratio` / `require` | 무버 임계(가격%/거래량배수, any\|both) | 5.0 / 2.0 / any |
| `readthrough_min_pct` / `max_peers` | 전파 트리거 임계 / 피어 상한 | 7.0 / 8 |
| `earnings_horizon_days` | 임박 실적 창 | 2 |
| `max_cause_hint_lookups` | 뉴스 cause-hint 조회 캡(fan-out 제한) | 5 |
| `bellwether_watchlist` | 시그널 전용 ETF(거래 불가) | SMH,SOXX,XLK,XLF,XLE,XLV,XLY,XLP,XLI |
| `peer_groups` | 정적 피어맵(종목→그룹). **bellwether는 반드시 어느 그룹에 속해야** 전파됨 | 18 그룹 |
| `scan_timeout_seconds` / `cache_ttl_seconds` | 스캔 상한 / 결과 캐시 | 30 / 300 |
| `sources.{news_primary,news_fallback,earnings_provider}` | 소스 토글 | alpaca/yfinance/finnhub |
> 임계가 너무 민감/둔감하면 `price_pct`·`readthrough_min_pct`를 조정. 새 종목/섹터를 universe에
> 추가하면 해당 `peer_groups`에도 넣어줘야 read-through가 작동한다(테스트 `test_config_seed.py`가
> bellwether 누락은 막아주지만, 일반 종목의 그룹 편입은 운영자 몫).

## 6. 알려진 한계 / 범위 밖 (후속 트랙 후보)
- **애프터아워스/프리마켓 갭 미포착**: 전부 일봉 기준. 실적 직후 시간외 폭락은 다음 정규장
  일봉 전까지 무버로 안 잡힘. (후속 D 트랙: AH/프리마켓 바 캡처)
- **yfinance 폴백 뉴스 무타임아웃**: Alpaca 뉴스 실패 시 폴백하는 yfinance 경로는 per-call
  타임아웃이 없음(연결 행 시 그 한 번의 cause-hint 조회가 지연될 수 있으나 `research_timeout`로
  상한, 캡으로 횟수 제한). 후속에서 폴백에도 타임아웃 적용 검토.
- **정적 피어맵의 한계**: 관계가 고정. 새 테마/상관 변화는 수동 갱신 필요(동적 상관 도출은 범위 밖).
- **감성 점수**: Alpaca(Benzinga)는 무료티어 감성 미제공 → `sentiment=None`(가짜값 금지). 제목
  기반 휴리스틱은 yfinance 폴백에만 존재.

## 7. 롤백 / 비활성
- **부분**: `config/settings.yaml` `signals.enabled: false` → 리서치 턴 브리프 push 중단(데몬
  재기동 후). 툴은 계속 호출 가능.
- **소스 단위**: `signals.sources.earnings_provider: none`(실적 끔) / `news_primary: yfinance`
  (Alpaca 뉴스 끔) 등으로 개별 비활성.
- **완전**: 머지 revert. 단 추가는 전부 additive·하위호환이라 기존 동작에 회귀 없음
  (머지 시점 852 tests green).

## 8. 검증 상태 (머지 전)
- 70 signals + **854 full suite passing**, 회귀 없음. HEAD `1b829d2`.
- code-review 5건 + critic 4건 + 실사용 라이브검증 1건(NaN 데이터가드) 반영 완료.
- **라이브 end-to-end 검증**(worktree, 실데이터):
  - `readthrough AVGO`→22 피어, `readthrough SMH`→13 반도체.
  - **Alpaca 뉴스(Benzinga) 실호출** → 실 헤드라인 수신(cause_hint 실제 채워짐).
  - **`movers` 전체 파이프라인**(yfinance 스캔+Alpaca뉴스+Finnhub+피어맵) → 실무버(CIEN −13.7%,
    AVGO −12.6%, MU −7.7%)+read-through+실 cause_hint, `degraded_sources` 비어 있음.
  - `earnings_calendar` 필터 정상(horizon=2 주말 0건=정직, horizon=14 ORCL/ADBE 등장).
- **실사용에서 잡은 데이터 이슈**: yfinance가 일부 종목(예: GOOG)에 NaN 일간변화를 반환 → 이제
  NaN change/volume 행은 무버에서 제외(허위 무버·허위 read-through 방지). 운영 중 비슷한
  공급자 데이터 결함은 `degraded_sources` 또는 무버 누락으로 드러난다.
