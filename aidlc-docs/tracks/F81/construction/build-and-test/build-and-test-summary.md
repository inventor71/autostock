# F81 — Build & Test Summary

## Status: ✅ ALL GREEN (live SEC integration proven)

## What was built
소스-무관 "공개 보유내역" 수집 → 봇 유니버스/브리프 공급. 1차 구현 = SEC EDGAR 13F (SA LP).
- **신규**: `src/signals/holdings/` (`records`, `provider`, `store`, `overlay`, `brief`, `refresher`,
  `providers/sec_13f`, `providers/cusip_map`), `config/holdings/cusip_ticker.json`.
- **배선**: `src/signals/{records,collector,brief,settings}.py`, `src/universe/factory.py`,
  `src/trading/modes/agent.py`, `config/settings.yaml`.

## Build
- 추가 런타임 의존성 **없음**(stdlib `xml.etree` + 기존 `requests`/`pydantic`/`loguru`). lock 변경 없음.
- `python -m py_compile` (touched files) → OK. `import main` / `import src.trading.modes.agent` → OK.

## Unit / PBT / Integration tests (신규 — 40 passed)
```
venv/bin/python -m pytest tests/signals/test_sec_13f.py \
  tests/signals/test_holdings_core.py tests/signals/test_holdings_wiring.py -q
→ 40 passed
```
- **test_sec_13f.py**: put→SHORT / share·call→LONG 정규화, unmapped 드롭+카운트, weight 정규화
  (unmapped 포함 분모), 동일종목·동일사이드 집계, long/short 분리, 최신 13F-HR(/A 포함) 선택,
  13F-NT 스킵, none→raise, **DOCTYPE/ENTITY 거부(SECURITY-13)**, CIK allowlist(SECURITY-05),
  비-SEC 호스트 거부(SECURITY-11).
- **test_holdings_core.py**: HoldingsSnapshot/Highlight round-trip(PBT), store write/read/rotate/
  diff/staleness, 손상 파일 스킵·없는 dir 빈 결과(fail-honest), **overlay 방향-게이트**
  (shorting OFF→롱만, ON→롱+숏, stale 제외, source allowlist), brief 방향 명시 렌더.
- **test_holdings_wiring.py**: refresher fail-honest(나쁜 provider 스킵·전부 실패해도 무예외),
  factory `_holdings_overlay`(기본 롱-only, shorting ON시 숏 포함, disabled·overlay:false·garbage→[]),
  collector 캐시-read(HTTP 없음, disabled·no-cache 무degraded).

## 회귀 확인
- `pytest tests/signals/` → **159 passed**, 3 failed.
- 3 failures = `test_sentiment_sweep.py` (날짜 의존 F77 테스트) — **F81 이전 main에서도 동일 실패**
  (pristine main 트리에서 재현 확인). F81 무관, 본 트랙이 새로 깨뜨린 것 없음.

## Live SEC smoke (real data — fakes can't prove this)
```
Sec13FProvider(cik=0002045724).fetch_snapshot()
→ accession 0002045724-26-000008, as_of 2026-05-18
→ 32 mapped / 5 unmapped
  LONG : CLSK RIOT IREN CORZ BTDR APLD CRWV BE MU TSM ... (miners / AI-infra 보유)
  SHORT: NVDA ORCL AVGO AMD MU TSM ASML INTC ... (puts = AI-하드웨어 약세 베팅)
```
방향 정규화·CUSIP 매핑·최신 filing 선택이 실데이터에서 정확히 동작. 알려진 thesis와 일치.

## Security Baseline 컴플라이언스
| Rule | 상태 | 비고 |
|---|---|---|
| SECURITY-05 입력검증 | ✅ | CIK `^\d{1,10}$`, accession/파일명 allowlist regex, XML 크기 상한, 숫자 파싱 가드 |
| SECURITY-11 SSRF/rate | ✅ | 호스트 핀(`data.sec.gov`/`www.sec.gov`), URL은 코드 상수+검증된 숫자만, `request_gap_s` 페이싱 |
| SECURITY-13 역직렬화 | ✅ | DOCTYPE/ENTITY 선언 XML 거부(XXE/billion-laughs), stdlib ET |
| SECURITY-15 fail-closed | ✅ | 모든 외부호출·파싱 try/except → degrade(open 금지), 턴/데몬 무중단 |
| SECURITY-10 공급망 | ✅ | 신규 의존성 없음, lock 무변경, 신뢰 소스(SEC) |
| SECURITY-03 로깅 | ✅ | loguru 재사용, 공개 13F 보유표만 저장(PII 없음) |
| 01/02/04/06/07/08/09/12/14 | N/A | 데이터스토어/웹엔드포인트/인증/IaC/네트워크 인프라 없음(데몬 내 캐시 파일 + outbound only) |

## PBT(Property-Based Testing) 컴플라이언스
- round-trip 불변식(HoldingsSnapshot/Highlight model_validate∘model_dump==id), overlay 방향-게이트,
  weight 정규화 등 순수 로직에 Hypothesis 적용. ✅
