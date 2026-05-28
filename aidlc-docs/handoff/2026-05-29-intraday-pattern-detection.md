# Handoff — 인트라데이 패턴 감지 (F1), 2026-05-29

이 문서만 읽고도 다음 세션에서 이어서 작업할 수 있도록 정리한 인계 노트.
연관 추적 문서: `aidlc-docs/aidlc-state.md`(F1 트랙), `aidlc-docs/audit.md`(F1 항목),
요구사항 `aidlc-docs/inception/requirements/intraday-pattern-feature.md`.

## 1. 배경 & 목표
"장시작~장마감 그래프를 매일 추적하면 패턴(개장 급락 후 회복, 급등+커뮤니티 반응 후 하락 등)이
보이지만, 그 패턴은 수주~수개월 단위로 변한다(비정상성)"는 사용자 관찰에서 출발. LLM이 이런
패턴을 기록·동적 감지·활용하게 하고 싶지만, **구현 전에 아이디어 유효성부터 검증**하는 게 목적.

## 2. 타당성 결론 (재구성)
- 관찰 자체는 타당(실재하는 현상) + 비정상성 지적이 정확(= 핵심 난점).
- 단, "LLM이 변하는 패턴을 예측" 원안은 위험: 레짐당 표본 ~20–60일, agent+웹 경로는 백테스트 불가,
  과거 실시간 커뮤니티 반응 데이터는 싸게 못 구함, LLM의 서사적 과적합(없는 패턴을 자신있게 지어냄).
- **재구성(채택):** "예측"이 아니라 **"반증 가능한 가설 + 정직한 out-of-sample 채점"**. 기존
  agent/journal/lessons/EOD-review 구조의 확장. 커뮤니티 감성은 **API 기반 부차적 contrarian 피처**로만.
- 단계: **P0**(결정론적 피처 store + 패턴 존재성 분석, 백테스트 가능) → P1(저널 가설 라이프사이클 +
  EOD out-of-sample 채점) → P2(감성 API 피처) → P3(graduated 가설→사이징, paper-only + 성공기준 게이트).
- 사용자 결정: **P0만 먼저(탐색적)** — "패턴이 통계적으로 실재·지속하는가"를 데이터로 답한 뒤 재판단.

## 3. 완료된 것 (P0 + P0+)
모두 결정론적, LLM/웹/트레이딩 영향 0.
- `src/data/intraday_features.py` — 세션별 순수 피처 + `FEATURE_COLUMNS`.
- `src/data/intraday_store.py` — `IntradayFeatureStore`, 심볼별 CSV(`data/intraday/`), `(date,symbol)` 멱등 upsert.
- `src/data/intraday_collector.py` — `sessionize`/`features_for_symbol`/`collect` + CLI(`backfill`/`today`).
  **P0+**: `collect()`에 `start`/`end` 추가(범위 모드, limit 제거) + CLI `--provider {yfinance,alpaca} --start --end`
  → Alpaca로 수년치 딥 백필 가능.
- `src/data/intraday_analysis.py` — `Hypothesis` 레지스트리(gap-down 반전 / gap-up fade / 개장 surge fade /
  개장 dip recover), 조건부 엣지(n/hit_rate/mean-excess/t-stat/direction_ok) + **rolling-window 안정성**,
  md/JSON 리포트 + CLI.
- `tests/test_intraday.py` — 17개(피처 예시+Hypothesis 불변식, store 멱등성/멀티심볼/빈store, collector
  sessionize/prev_close 연결/장애격리/범위·limit 라우팅, 분석 주입패턴 vs 무패턴 + 마크다운).

## 4. 현재 상태
- **전체 테스트 196 통과**(기존 179 + 신규 17).
- 라이브 검증 완료: yfinance(AAPL 14세션) + Alpaca 1개월(3,899봉→21세션) + Alpaca 딥
  (2024-01~2026-05, **107,633봉→633세션**, ~30초).
- `data/intraday/AAPL.csv`에 647세션 샘플 존재(**gitignore 처리됨, 커밋 안 함**).
- 647세션 리포트 발견: `gap_down_reversion`만 흔적(hit 83%, excess +1.33%, t≈2.8)이나 **n=12**이고 한
  rolling 윈도우에서 부호가 음으로 뒤집힘. 나머지 3개는 엣지 없음. → 단일 종목·짧은 기간의 표본 부족과
  비정상성을 그대로 보여줌(= P0가 의도한 정직한 산출물).

## 5. 핵심 결정 & 제약
- **저장은 "하루 1행 피처 레코드"** (원본 분봉 아님) → 용량 극소.
- 저장 포맷 CSV(신규 의존성 회피; pyarrow 없음, pandas 3.0). store는 추후 Parquet로 교체 가능한 추상화.
- 데이터 소스: yfinance 인트라데이 ~60일 한계 / Alpaca 분봉 2016~ (무료는 IEX feed = 거래량 부분집합;
  SIP는 provider에 `feed` 파라미터 추가 필요 — 미구현, 범위 밖).
- 커뮤니티 반응 결합 패턴은 **백테스트 불가**(과거 실시간 감성 데이터 부재) — 가격-형태 절반만 검증 가능.
- universe는 `config/settings.yaml`의 `trading.symbols`(~105). CLI `main()`은 composition root이므로
  `get_settings()` 사용 OK(U2 규칙과 일관).

## 6. 파일 위치
- 코드: `src/data/intraday_{features,store,collector,analysis}.py`
- 테스트: `tests/test_intraday.py`
- 요구사항/타당성: `aidlc-docs/inception/requirements/intraday-pattern-feature.md`
- 추적: `aidlc-docs/aidlc-state.md`(F1 섹션), `aidlc-docs/audit.md`(F1 항목)
- 샘플 데이터(비커밋): `data/intraday/*.csv`

## 7. 실행 방법 (CLI)
```bash
# 최근치 빠른 수집(yfinance, ~60일 한계)
python -m src.data.intraday_collector backfill --days 30
# 수년치 딥 백필(Alpaca, 날짜범위) — .env에 alpaca 키 필요
python -m src.data.intraday_collector backfill --provider alpaca --start 2024-01-01 [--end 2026-05-01]
# 당일 1회
python -m src.data.intraday_collector today
# 패턴 존재성 리포트
python -m src.data.intraday_analysis [--symbols AAPL ...] [--windows 6] [--format md|json] [--gap-thr 0.01] [--or-thr 0.005]
```

## 8. 다음 단계 (열린 항목)
사용자와 합의된 우려 2가지(용량/종목별 특성)에 대한 결론:
1. **용량은 비이슈** — 종목당 ~171 bytes/세션. universe 전체: ~2.4년 ≈ 11MB, 10년 ≈ 45MB.
   진짜 비용은 네트워크/시간(전체 universe 딥 백필 ≈ 30–60분 순차).
2. **종목별 특성 해석이 핵심 미해결** — 현재 분석기는 순진한 풀링 + 원시 임계값(v0). 제대로 하려면
   **P0.5 분석 업그레이드** 필요:
   - **변동성 정규화**: 원시 `gap_pct` 대신 종목 자기 σ 단위 z-score → 종목 간 풀링이 정당해짐.
   - **특성 버킷**: 티커가 아니라 변동성/유동성/(섹터) 분위수로 묶어 분석.
   - **교차종목 일관성**: 가설이 버킷 내 다수 종목에서 같은 부호인지(한 종목이 끌고 가는지) 검증.
   - **부분 풀링/shrinkage**(엄밀 경로, 선택): 표본 적은 종목 추정치를 버킷 평균으로 수축.
   - 해석 단위 = (특성 버킷 × 정규화 조건), 검증 축 = (시간 윈도우 × 버킷 내 종목들).

**추천 순서(미착수):** P0.5 분석 업그레이드(코드만, 새 데이터 불필요로 개발 가능) →
변동성 스펙트럼 대표 소수 바스켓(~8종목) 백필로 검증 → 전체 universe 딥 백필 → 제대로 된 리포트 →
P1 진행 여부 판단. (대안: 전체 백필 먼저 돌려두고 분석기 업그레이드.)

정직한 한계: 도구는 "엣지가 존재/안정적인가"를 정확히 **측정·특성화**할 수 있을 뿐(없으면 "없음"도
정직하게), 없는 신호를 만들지는 못함. 안정적 수익 엣지의 존재 여부는 위 순서로 답할 실증 문제.
