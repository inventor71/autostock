# F81 — Application Design (+ Functional Design + NFR-light)

> 소스-무관 "공개 보유내역" 수집 → 봇 유니버스/브리프 공급. 1차 구현 = SEC EDGAR 13F.
> 기존 F77 sentiment 패턴(**데몬 스윕 → 캐시 쓰기 / 턴은 읽기만, HTTP 없음**)을 차용한다.

## 0. 핵심 아키텍처 결정 (F77 sweep 패턴 차용)
외부 SEC HTTP를 **리서치 턴 핫패스에서 절대 호출하지 않는다**. 대신:
- **데몬 측 주기 리프레시**(`HoldingsRefresher`, sentiment_sweep와 동형): 하루 1회 각 provider의
  `fetch_snapshot()`(유일한 HTTP) 호출 → 정규화 `HoldingsSnapshot`을 `workspace/holdings/<source_id>.json`에 원자적 기록.
- **턴/유니버스 경로**: 그 캐시 JSON을 **읽기만** 한다(HTTP 0). 캐시 없음/파싱 실패 → 오버레이/섹션 부재(degrade), 크래시 ❌.
→ NFR-3(핫패스 동기 네트워크 금지), FR-6(fail-honest), NFR-1(격리)이 구조적으로 충족.

## 1. 신규 서브패키지 레이아웃 (`src/signals/holdings/`)
```
src/signals/holdings/
  __init__.py
  records.py      # 정규화 도메인 (소스-무관)
  provider.py     # HoldingsProvider 프로토콜 + registry(type→builder)
  store.py        # 캐시 read/write (workspace/holdings/*.json) + diff
  overlay.py      # HoldingsSnapshot[] → 유니버스 심볼 오버레이 (소스-무관)
  brief.py        # HoldingsSnapshot[] → 브리프 하이라이트/렌더 (소스-무관)
  refresher.py    # 데몬 주기 리프레시 러너 (sentiment_sweep 동형)
  providers/
    __init__.py
    sec_13f.py    # EDGAR 13F-HR 구현 — 모든 SEC-fragile 로직 격리
    cusip_map.py  # CUSIP→ticker 매핑 (격리)
```
> **소스 무관 경계(FR-1)**: `overlay.py`/`brief.py`/`store.py`/`refresher.py`는 `HoldingsSnapshot`만
> 의존하고 13F/EDGAR를 import하지 않는다. 새 공시 소스 추가 = `providers/<x>.py` + registry 등록만.

## 2. 도메인 모델 (`records.py`) — pydantic round-trip (PBT-02 동형)
```python
Side = Literal["LONG", "SHORT"]   # 주식 보유=LONG, 풋=SHORT (방향 정규화)

class HoldingRow(BaseModel):
    ticker: str                    # 매핑 성공분만 (실패분은 snapshot.unmapped_n로 카운트)
    side: Side
    weight: float                  # 0..1, 매니저 포트폴리오 내 비중 (value 기준 정규화)
    value_usd: float | None        # 13F value (천$ 단위 원본은 provider에서 환산)
    shares: int | None
    raw_id: str                    # 원천 식별자 (CUSIP 등) — 디버그/추적용
    put_call: Literal["PUT","CALL",None] = None  # 원천 방향(투명성), side는 이미 정규화됨

class HoldingsSnapshot(BaseModel):
    source_id: str                 # 예: "sec_13f:0002045724"
    manager_name: str              # 예: "Situational Awareness LP"
    as_of: date                    # filing report date (분기말) — staleness 기준
    fetched_at: datetime           # 리프레시 시각
    accession: str | None          # 추적용 (13F accession no.)
    rows: list[HoldingRow]
    unmapped_n: int = 0            # ticker 매핑 실패 건수 (브리프에 "unmapped N")
    def long_tickers(self) -> list[str]: ...
    def short_tickers(self) -> list[str]: ...

class HoldingsDiff(BaseModel):     # 직전 snapshot 대비 (브리프 NEW/ADD/EXIT)
    new: list[str]; added: list[str]; exited: list[str]
```

## 3. Provider 프로토콜 + registry (`provider.py`)
```python
class HoldingsProvider(Protocol):
    source_id: str
    manager_name: str
    def fetch_snapshot(self) -> HoldingsSnapshot: ...   # 불순(HTTP). 데몬 리프레시만 호출.

# config type → builder. 새 소스는 여기 한 줄 등록.
_BUILDERS: dict[str, Callable[[dict, Settings], HoldingsProvider | None]] = {
    "sec_13f": build_sec_13f_provider,
}
def build_providers(cfg, settings) -> list[HoldingsProvider]:  # fail-honest per provider
    ...
```

## 4. SEC 13F 구현 (`providers/sec_13f.py`) — fragile 로직 전부 격리
- 입력: `{type: sec_13f, cik, overlay, manager_name?}`.
- **fetch_snapshot()**:
  1. `GET https://data.sec.gov/submissions/CIK{cik:010d}.json` (UA 헤더 필수).
  2. recent filings에서 **`form ∈ {"13F-HR","13F-HR/A"}`** 중 최신 `filingDate` accession 선택
     (FR-8: /A 수정본 포함). `13F-HR/A`가 같은/더 최신 분기면 우선. **`13F-NT`는 보유표 없음 → 건너뜀**.
  3. 해당 accession의 **INFORMATION TABLE XML**(`*.xml`, `<informationTable>`) fetch.
  4. 파싱(네임스페이스 무관, local-name 매칭): 각 `infoTable` →
     `nameOfIssuer, cusip, value(천$), shrsOrPrnAmt, putCall?`.
  5. **방향 정규화**: `putCall` 없음/"Call" → 평가에서 제외 or LONG? → **풋만 SHORT, 그 외 주식보유 LONG;
     `Call`(롱 콜)은 LONG**. (롱 콜은 강세이므로 LONG로 둠. 표 대부분은 주식 SH=LONG, 풋=SHORT.)
  6. **CUSIP→ticker**(`cusip_map.py`): 매핑 성공분만 `HoldingRow`, 실패는 `unmapped_n++`.
  7. `value` 합으로 `weight` 정규화. `HoldingsSnapshot` 반환.
- **resilience(FR-8)**: 위 어느 단계 실패든 예외를 올려 보내고(데몬 리프레시가 잡아 degrade),
  스키마 drift는 관대한 파싱 + 실패 시 fail-closed(부분 표는 채택하되 표 자체 없으면 degrade).

### CUSIP→ticker 매핑 (`cusip_map.py`)
- 1차: **로컬 정적 맵** `config/holdings/cusip_ticker.json`(시드 = SA LP 13F의 주요 종목 +
  S&P100 매핑). 무료·오프라인·결정론적.
- 매핑 실패분은 드롭 + `unmapped_n` 집계(브리프 노출). (외부 CUSIP API는 유료/ToS라 본 트랙 제외 —
  후속 확장 포인트. provider 내부에 격리되어 교체 자유.)

## 5. 캐시 store + diff (`store.py`) — 소스 무관
- `write_snapshot(root, snap)`: `workspace/holdings/<safe(source_id)>.json` 원자적 기록
  (tmp→replace, `BaseUniverseProvider._save_snapshot` 동형). 직전 파일은 `.prev.json`로 보존(diff용).
- `read_snapshots(root) -> list[HoldingsSnapshot]`: 모든 `*.json` 읽기, 손상/구버전은 스킵(fail-honest).
- `compute_diff(prev, cur) -> HoldingsDiff`: ticker 집합 비교(NEW/ADD/EXIT). 순수.
- **staleness**: `read_snapshots`는 `as_of`가 `today - max_age_days`(기본 135)보다 오래면
  `stale=True`로 표시(드롭 여부는 소비자 결정 — 오버레이는 드롭, 브리프는 "stale" 태그로 노출).

## 6. 유니버스 오버레이 (`overlay.py`) — 소스 무관, FR-3/FR-4
```python
def holdings_universe_overlay(snapshots, *, shorting_enabled: bool,
                              max_age_days: int) -> list[str]:
    # 비-stale snapshot에서:
    #   LONG ticker → 항상 포함
    #   SHORT ticker → shorting_enabled=True 일 때만 포함 (FR-4: 기본 OFF면 brief-only)
    # overlay=False인 provider는 호출 전 필터링(브리프 전용)
```
**`resolve_universe` 통합**(`src/universe/factory.py`): base ∪ themes 계산 후, fail-honest로
`holdings_universe_overlay(read_snapshots(root), shorting_enabled=settings.risk.shorting_enabled,
max_age_days=cfg.max_age_days)`를 union. 읽기 실패/파일 없음 → 오버레이 0(기존 동작 보존).
- **모든 resolve_universe 호출부 자동 수혜**(main 157/333/418, intraday, tools). 추가 배선 불필요.
- 안전: 오버레이는 union-only(기존 종목 제거 ❌), 빈 오버레이는 무영향, 토글 off → 즉시 0.

## 7. 브리프 섹션 (`brief.py` + signals 배선) — 소스 무관, FR-5
- `holdings_highlights(snapshots, diffs) -> list[HoldingsHighlight]` (순수): 매니저별
  `manager_name · as_of분기 · top LONG n · top SHORT n(방향 태그) · NEW/EXIT diff · unmapped_n · stale?`.
- `MarketSignalBrief`에 `disclosed_holdings: list[HoldingsHighlight]` 필드 추가
  (`records.py`, default_factory=list — round-trip/`is_empty`/`to_dict` 갱신).
- `SignalCollector.collect`에 단계 추가: `_disclosed_holdings(degraded)` — **store 읽기만**
  (sentiment outliers와 동일하게 HTTP 없음, 실패 시 `degraded.append("holdings:read")`).
- `to_prompt_text`에 13F 섹션 렌더(움직임/실적 섹션과 동일 톤, 방향 명시):
  `[기관공시] Situational Awareness LP (13F Q1'26): SHORT NVDA,AVGO,TSM · LONG CLSK,RIOT,IREN · NEW… · unmapped 3`.

## 8. 데몬 리프레셔 (`refresher.py` + agent.py 배선) — FR-7/FR-2
- `HoldingsRefresher(providers, root, cfg)` — `SentimentSweeper` 동형. `refresh_tick()`:
  각 provider `fetch_snapshot()` 호출 → 변경 시 `write_snapshot`. 모든 런타임 에러 흡수(degrade).
- `agent.py`에 `_setup_holdings_refresh()`(= `_setup_sentiment_sweep` 패턴): cfg.enabled면
  `scheduler.add_seconds_job(refresher.refresh_tick, cfg.refresh_hours*3600, "holdings_refresh",
  misfire_grace_time=…)`. 데몬 부팅 시 1회 즉시 + 이후 주기. 실패해도 데몬 무영향.

## 9. Config 스키마 (`config/settings.yaml` + settings.py)
```yaml
signals:
  disclosed_holdings:            # 신규 (DisclosedHoldingsConfig)
    enabled: false               # 기본 OFF (안전; 켜야 동작) — NFR-5
    refresh_hours: 24            # FR-7 폴링 주기
    max_age_days: 135            # staleness (≈1분기+45일 시차)
    user_agent: "autostock/1.0 (contact: <email>)"   # SEC fair-access (NFR-4)
    request_gap_s: 0.5           # SEC rate 예의
    providers:
      - { type: sec_13f, cik: "0002045724",
          manager_name: "Situational Awareness LP", overlay: true }
```
- `DisclosedHoldingsConfig(BaseModel)`를 `SignalsConfig`에 추가(`SentimentConfig` 선례).
- **CIK 검증(SECURITY-05)**: `^\d{1,10}$` allowlist, 아니면 해당 provider 거부.

## 10. NFR / Security 설계 (light)
| 항목 | 설계 |
|---|---|
| **NFR-1/FR-6 fail-honest** | provider별·섹션별 try/except → degrade. 데몬/턴 크래시 불가. |
| **NFR-3 성능** | HTTP는 데몬 리프레시(일1회)만. 턴/유니버스는 캐시 read-only. |
| **NFR-4 SEC fair-access** | UA 헤더 필수, `request_gap_s` 간격, **호스트 핀** `data.sec.gov`/`www.sec.gov`만 허용. |
| **SECURITY-05 입력검증** | CIK 정규식 allowlist; XML 크기 상한; 숫자 필드 파싱 가드. |
| **SECURITY-11 SSRF/rate** | URL은 코드 상수 호스트에서만 구성(설정 CIK는 경로 숫자로만 삽입), 외부 URL 입력 불가. |
| **SECURITY-13 역직렬화** | XML은 **방어적 파서**(`defusedxml` 또는 stdlib + entity/DTD 비활성)로 외부 콘텐츠 파싱 — XXE/billion-laughs 차단. |
| **SECURITY-15 fail-closed** | 모든 외부호출 try/except, 부분 실패는 해당 소스만 무력화(open 금지). |
| **SECURITY-10 공급망** | 신규 의존성은 `defusedxml`(있으면 stdlib 가드로 대체 가능) — lock 갱신. 신뢰 레지스트리. |
| **SECURITY-03 로깅** | loguru 재사용. PII/메시지 본문 미저장(13F는 공개 보유표만). |

## 11. 영향/리스크 & 테스트 (요약)
- **방향 오인 차단(핵심)**: 풋→SHORT 정규화 + shorting OFF시 유니버스 미편입(brief-only). 테스트로 고정.
- **숏 comply**: 유니버스 편입은 후보일 뿐, 실제 숏은 `RiskManager`(F54/F60) 게이트 통과 — 무변경.
- **테스트**: ① 순수 파서/diff/방향/staleness 단위+PBT(라운드트립·diff 불변식) ② overlay 방향-게이트
  (shorting on/off 분기) ③ fail-honest(파일없음/손상/HTTP실패→크래시 없음) ④ 13F XML fixture 파싱
  ⑤ 라이브 SEC 스모크(실 CIK 0002045724 read-only).

## 12. 변경 파일 요약
- **신규**: `src/signals/holdings/**`, `config/holdings/cusip_ticker.json`.
- **수정(배선)**: `src/signals/records.py`(brief 필드), `collector.py`(read 단계+from_settings),
  `brief.py`(렌더), `settings.py`(config), `src/universe/factory.py`(overlay union),
  `src/trading/modes/agent.py`(refresher 배선), `config/settings.yaml`.
- **무변경 소비**: `src/risk/manager.py`(숏 게이트), universe provider base.
