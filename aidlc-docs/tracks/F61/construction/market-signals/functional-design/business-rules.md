# F61 Functional Design — Business Rules & Config (unit: market-signals)

> 모든 임계/맵/리스트는 `config/settings.yaml`의 `signals:` 블록으로 노출(FR-7). 아래는 **시드 기본값**.

## R1. 무버 판정 (detect_movers)
- 종목이 무버로 채택되는 조건: `abs(change_pct) ≥ price_pct` **OR** `volume_ratio ≥ vol_ratio` (기본 OR; `require=both`로 AND 전환 가능).
- 정렬: `abs(change_pct)` 내림차순. 표시 상한 `max_movers`.
- `change_pct`는 기준 종가(전일 종가) 대비. (애프터아워스 정밀 갭은 범위 밖 — 후속 D 트랙.)
- **시드**: `price_pct=5.0`, `vol_ratio=2.0`, `require=any`, `max_movers=12`.
  (surge 감지기 7%보다 민감 — 무버는 "주목" 단계, surge는 "사후 분석" 단계로 역할 분리.)

## R2. 전파 판정 (build_readthrough)
- read-through 경고는 무버 중 `abs(change_pct) ≥ readthrough_min_pct` 인 트리거에만 발생.
- `affected_peers` = `peers_of(trigger)` ∩ `universe` (행동 가능한 유니버스 종목만), self 제외, 상한 `max_peers`.
- 피어가 0이면 경고 미생성. 트리거는 유니버스 밖(bellwether)이어도 됨.
- `cause_hint`: 트리거 뉴스 신규 헤드라인에서 추출(있으면). 실패/없음 → None(경고는 그대로 생성).
- **시드**: `readthrough_min_pct=7.0`, `max_peers=8`.

## R3. 임박 실적 (select_imminent_earnings)
- 대상: `universe ∪ held`, `today ≤ earnings_date ≤ today + horizon_days`.
- `is_held` 표시. `peer_readthrough` = 실적종목의 `peers_of` ∩ (`held` ∪ `universe`) — "보유 종목이 임박 실적 종목의 피어면 점검" 유도(FR-4).
- **시드**: `horizon_days=2`.

## R4. Fail-honest / degrade (NFR-1)
- 각 소스 호출은 독립적으로 감싼다. 실패(네트워크/레이트리밋/키부재/파싱)는:
  - 해당 섹션만 비우고 `degraded_sources`에 소스명 추가, 나머지로 brief 조립.
  - 1회 경고 로그(스팸 금지). 가짜/추정 데이터 절대 생성 금지.
- `FINNHUB_API_KEY` 부재 → 실적 캘린더 조용히 비활성(`degraded_sources=["earnings:finnhub(no key)"]`). 폴백 yfinance per-symbol은 비용 높아 **기본 미사용**(opt-in).
- Alpaca 뉴스 실패 → yfinance 뉴스 폴백 → 그것도 실패면 cause_hint 없이 진행.

## R5. 타임아웃/캐시 (NFR-2/3)
- **가격 스캔**: yfinance는 per-call 타임아웃이 없으므로 **스캔 전체를 daemon 스레드 + join(deadline)으로 바운드**(`scan_timeout_seconds`, 시드 30s). 초과 시 degrade(`prices:timeout`), 데몬 워커는 백그라운드 drain(프로세스 종료 미차단). (critic 반영: `ThreadPoolExecutor` `with`/non-daemon 누수 회피)
- **뉴스/Finnhub**: per-HTTP connect/read 타임아웃(F14 패턴). 뉴스 cause-hint 조회는 **상위 N 트리거로 캡**(`max_cause_hint_lookups`, 시드 5)해 변동성 큰 날의 fan-out 제한. (정정: collect() **전체**를 단일 상한으로 묶지는 않음 — 스캔 바운드 + 뉴스 캡 + per-HTTP, 그리고 turn은 `research_timeout` 보호.)
- Finnhub ≤ 60 calls/min: 실적 캘린더는 날짜범위 1회 호출(종목별 호출 금지).
- `collect()` 결과 TTL 캐시(시드 `cache_ttl_seconds=300`, 키 = today|horizon|held) — push와 툴이 동일 결과 공유.

## R6. 시드 피어 맵 (`signals.peer_groups`) — 실제 유니버스 기반
> 한 종목이 여러 그룹에 속할 수 있음. AVGO ∈ {semiconductors, ai_networking, ai_infra_broad}.
```yaml
peer_groups:
  semiconductors:   [NVDA, AMD, AVGO, QCOM, TXN, INTC, MU, MRVL, ARM, TSM, ADI, MPWR, RMBS]
  semicap_equipment:[AMAT, LRCX, KLAC, ASML, TER]
  memory_storage:   [MU, SNDK, WDC, STX, RMBS]
  ai_networking:    [ANET, CIEN, COHR, LITE, MRVL, AVGO]
  ai_servers_odm:   [DELL, SMCI]
  ai_hyperscalers:  [MSFT, GOOGL, GOOG, AMZN, META, ORCL]   # AI-capex buyers
  datacenter_power: [VRT, ETN, PWR, GEV, NVT, MOD, VST, CEG]
  datacenter_reit:  [DLR, EQIX, AMT, CCI, PLD]
  software_infra:   [NOW, CRM, ADBE, INTU, ORCL]
  megacap_tech:     [AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA]
  banks:            [JPM, BAC, WFC, C, USB, PNC, TFC, COF, GS, MS]
  payments:         [V, MA, AXP]
  energy:           [XOM, CVX, COP, SLB, EOG, MPC, PSX, VLO, OXY]
  # ai_infra_broad: 반도체+공급망 전반 cross-group (AVGO 실적쇼크가 공급망 전체로 번지는 케이스)
  ai_infra_broad:   [NVDA, AMD, AVGO, MRVL, ARM, AMAT, LRCX, KLAC, ANET, VRT, DELL, SMCI, MU]
```
→ AVGO −N% ⇒ peers_of(AVGO) = semiconductors ∪ ai_networking ∪ ai_infra_broad 합집합 − {AVGO}.

## R7. 시드 bellwether 워치리스트 (`signals.bellwether_watchlist`) — 시그널 전용(거래 불가)
- 유니버스에 SPY/QQQ/IWM/DIA/VTI는 이미 포함. 추가 섹터 ETF만 워치:
```yaml
bellwether_watchlist: [SMH, SOXX, XLK, XLF, XLE, XLV, XLY, XLP, XLI]
```
- 이들은 스캔/전파의 **트리거 소스로만** 사용. `filter_in_universe`가 거래는 계속 차단.

## R8. 소스 토글 (`signals.sources`)
```yaml
sources:
  news_primary: alpaca      # alpaca | yfinance
  news_fallback: yfinance
  earnings_provider: finnhub # finnhub | none
```

## R9. 다유형 시나리오 코퍼스 (Tier 1, 결정적) — `tests/signals/scenarios/`
각 시나리오 = 고정 입력(가격 rows + 뉴스 + 캘린더) + 기대 출력 요지. 종목/숫자는 합성(실제 종목명 사용하되 가격은 합성).
| ID | 유형 | 입력 요지 | 기대 |
|---|---|---|---|
| S1 | 실적 쇼크 전파(AVGO류) | AVGO −15%, 뉴스 "guidance miss" | 무버[AVGO down] + read-through{trigger=AVGO, peers⊇[NVDA,AMD,MRVL,...]∩universe}, cause_hint≈"miss" |
| S2 | 섹터 동반락 | banks 5종 −6~8% | 무버 다수(banks) + read-through(banks 그룹) |
| S3 | 매크로 쇼크 | 트리거=XLE(bellwether) +9%, 유가급등 | 무버[XLE] + read-through{peers⊇energy∩universe}; XLE는 거래 안 됨(in_universe=False) |
| S4 | 개별 악재 비전파 | 단일 종목 −12%(피어그룹 없음/리콜성 특이악재) | 무버[해당] 있으나 read-through **미생성**(오탐0) |
| S5 | 무이벤트일 | 전 종목 |chg|<3%, vol 정상 | 무버/경고/실적 **전부 빈 brief**, degraded 없음 |
- S1·S3 = 진양성(전파 잘 됨), S4·S5 = 오탐0(안 떠야 할 때 안 뜸). 둘 다 강제.

## R10. Tier 2 토큰 보호 (NFR-7)
- `eval_harness`는 `src/signals/eval_harness.py` + `python -m src.signals.eval_readthrough <scenario>` 로만 LLM 호출. `tests/` 밖 또는 `@pytest.mark.manual`(기본 deselect, `addopts = -m "not manual"`). 기본 `pytest`·CI run = 토큰 0 보장.

## 확인 포인트 (게이트에서 조정 가능한 기본값)
1. 무버 임계 `price_pct=5.0 / vol_ratio=2.0`, 전파 `readthrough_min_pct=7.0` — 민감도.
2. 시드 피어 그룹 멤버십(R6) — 추가/삭제 희망 그룹.
3. bellwether 워치리스트(R7) — 섹터 ETF 목록.
4. 실적 horizon 2일.
(별도 질문 파일 없이 합리적 기본값으로 진행; 위 4개는 언제든 config로 조정.)
