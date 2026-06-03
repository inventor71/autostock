# NFR Requirements Plan — F30 (U1 kis-broker + U2 universe-provider)

> NFR은 대부분 기존 패턴(F14 HTTP timeout, alpaca `install_session_timeout`, 이미 확정된
> 토큰/reconcile/캐시 결정)과 설정된 Security/PBT extension에서 도출 → 차단 질문 없이 PoC 기본값으로
> 작성하고 가정을 완료 게이트에서 검토. 이견 시 Request Changes.

## 체크리스트
- [x] 성능: 주문 체결확인/ reconcile/ universe fetch 위치 및 목표
- [x] Rate limiting: KIS 실전/모의 호출 상한 + token-bucket/backoff
- [x] 신뢰성/가용성: fail-closed, 거래소 resting 1차보호, 데몬 재시작(F14) 복구, OcoGroup 재구성
- [x] 보안: Security extension 적용 매핑(SECURITY-03/05/09/10/11/12/15)
- [x] 유지보수/테스트: PBT Partial(Hypothesis) 대상
- [x] Tech stack 결정: 기존 dep 재사용 + KIS SDK git 핀
- [x] 산출물 2종 작성 + 2-option 게이트

## 가정 (게이트에서 검토 — 이견 시 알려주세요)
- KIS 모의투자 rate limit 정확값 불명 → **보수적 기본(초당 2건)** 적용, 실전 초당 ~15건. Code Gen 직전 검증.
- 성능 SLA 없음(PoC). reconcile 지연 ≤5초 허용(거래소 스탑이 1차 보호).
- 신규 인프라 없음. 단일 데몬/단일 브로커(동시성 낮음).
