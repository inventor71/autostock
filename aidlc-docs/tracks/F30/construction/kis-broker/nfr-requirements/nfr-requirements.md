# NFR Requirements — kis-broker (U1)

> PoC 등급. 기존 패턴(F14 timeout, alpaca `install_session_timeout`, fail-closed 관행) 정합.

## NFR-1. 성능 (Performance)
| 항목 | 요구 | 근거 |
|---|---|---|
| 주문 제출 | 동기, 짧은 fill-confirm 폴링(타임아웃 ~5s, alpaca `fill_poll_timeout=5` 정합) | 즉시성 vs 무한대기 방지 |
| reconcile_oco | 5초 주기 합승, 그룹당 O(open orders) | Q1=A |
| universe fetch | hot path 밖, 1일 캐시 | 주문 지연에 영향 없음 |
| 시세 폴링 | 보유∪open 심볼만(Q7=A) | rate-limit 절약 |
- **SLA**: 엄격 SLA 없음(PoC). reconcile 지연 ≤5초 허용.

## NFR-2. Rate Limiting / Throughput
- KIS 호출 상한: **실전 초당 ~15건(계정당)**, **모의 보수적 초당 2건**(정확값 Code Gen 검증).
- **token-bucket / 최소 호출 간격**으로 셀프 스로틀. 초과 위험 시 호출 직렬화.
- 초과 응답(429 상응) → **지수 backoff 재시도**, 지속 실패 시 `BrokerError`(fail-closed).
- 잔고조회 20종목/회 페이징은 호출 수에 포함 — 보유 종목 수 비례.

## NFR-3. 신뢰성 / 가용성 (Reliability / Availability)
- **fail-closed 전반**(SECURITY-15): 토큰 실패·timeout·rate-limit·장외·미지원 주문 → 주문 강행 금지, `BrokerError`.
- **1차 보호 = 거래소 resting 스탑지정가**(폴링/피드 정지에도 상주). 2차 = polled exit 백업.
- **데몬 재시작 복구**(F14 self-heal 연계): 재시작 시 OcoGroup(in-memory)은 `get_open_orders`로 거래소 resting leg 재발견하여 best-effort 재구성. 메타 소실이 보호 손실은 아님.
- **HTTP timeout**: connect 3.0s / read 5.0s(생성자 기본, F14 패턴). 무한대기 금지 → timeout은 best-effort 재시도로 흡수.
- **현금계좌 oversell 안전**: 잔여 SELL leg 지연 취소돼도 보유 초과 매도는 KIS가 거부.

## NFR-4. 보안 (Security extension — 적용)
| 규칙 | 적용 |
|---|---|
| SECURITY-03 (no secrets in logs) | 토큰/시크릿/계좌 마스킹·미출력 |
| SECURITY-05 (input validation) | 수량/가격/심볼/주문유형 검증 후 전송 |
| SECURITY-09 (error handling, fail-safe) | 모든 실패 경로 fail-closed |
| SECURITY-10 (dependency pinning) | KIS SDK git **커밋 핀** + 버전 고정 |
| SECURITY-11 (defense in depth) | 거래소 스탑 + polled exit 이중 보호 |
| SECURITY-12 (credential management) | `KIS_PAPER_*` / `KIS_LIVE_*` 환경변수, 하드코딩 금지 |
| SECURITY-15 (exception handling, fail-closed) | is_market_open 오류 시 False 등 |

## NFR-5. 유지보수 / 테스트 (PBT Partial — Hypothesis)
- `round_to_tick`(멱등·tick 배수·단조), 수량 floor 불변식, 주문유형 매핑 round-trip.
- 생성자: 현실적 가격(1~1,000,000원)·수량 분포; 실패 shrink 재현(PBT-08).
- KIS API 호출은 단위테스트에서 모킹(네트워크 비의존).

## NFR-6. 환경 분리
- Paper/Live 분리: `paper=True → vps(모의)`, `paper=False → prod(실전)`. 자격증명 env 분리.
- 기본 paper. live 전환은 명시 설정 필요(안전 기본값).
