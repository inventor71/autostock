# F96 Post-Merge Guide — 진입 드리프트 가드 + 뉴스 신선도

## 무엇이 바뀌나 (prod 관찰 가능)
1. **진입 드리프트 가드** — 에이전트가 **지정가 없이(market)** 낸 BUY/SELL_SHORT가, 결정 시각
   대비 실행 시점 가격이 **0.5 ATR 이상 불리하게** 벌어졌으면 시장가 대신 **지정가(LIMIT @
   결정가±0.5ATR)** 로 나간다. 즉 "달아난 종목"은 밴드 안으로 눌릴 때만 체결되고, 아니면 미체결.
   - 결정가 앵커는 데몬이 **턴 직후** 스탬프한 `ref_price`(그 순간 시세). 에이전트가 지정가를
     준 진입은 이 가드의 영향 없음(기존 동작 그대로).
2. **뉴스 신선도** — `news` 툴 출력의 각 항목에 `age_hours` + `priced_in_risk`("fresh"/"elevated")
   가 붙는다. 프롬프트/aggressive posture에 "24h 넘은 촉매는 priced-in 위험 → 고점 추격 금지" 규칙 추가.

## 선행 조건
- **데몬 재시작 필수** (프롬프트·실행 경로·config 스키마 변경). 다중 인스턴스면 전부.
- **신규 config 키**: `config/settings.yaml` `risk.entry_drift_guard_atr: 0.5` (기본값 shipped).
  `0`으로 두면 가드 완전 비활성(기존 동작). env 키 추가는 없음.

## 실사용 검증 체크리스트
1. **가드 발동 관찰** — 데몬 로그에서 진입 시 `Risk approved: BRACKET BUY … guard=drift-capped(limit=…)`
   라인을 확인. 이게 찍히면 market 진입이 LIMIT으로 강등된 것. 안 찍히고 그냥 MARKET이면 정상 범위.
   - 어디서: 데몬 stdout/로그. 정상: 대부분의 진입은 MARKET(강등 없음), 급하게 달아난 종목만 강등.
2. **ref_price 스탬핑 확인** — `workspace/decisions.jsonl`의 최근 market BUY/SELL_SHORT 라인에
   `"ref_price": <숫자>` 가 채워졌는지(지정가 진입·HOLD·SELL엔 `null`이 정상).
3. **뉴스 필드** — `python -m src.agent.tools news <SYM>` 실행 → 각 항목에 `age_hours`,
   `priced_in_risk` 존재. 하루 지난 헤드라인은 `elevated`.
4. **미체결 관찰** — 강등된 LIMIT이 안 눌리면 미체결로 남는다(정상). 브로커 open orders에서
   해당 심볼 LIMIT 확인 가능. 다음 턴에 에이전트가 재평가.

## 튜닝 노브
- `risk.entry_drift_guard_atr` (기본 `0.5`): 클수록 관대(더 큰 드리프트까지 허용), 작을수록 타이트.
  `0` = 가드 끔. 변경 후 데몬 재시작.
- 뉴스 priced-in 임계는 코드 상수 `src/agent/tools/market.py::_PRICED_IN_HOURS = 24.0` (조언용,
  하드 게이트 아님 — 에이전트 판단 보조).

## 롤백
- `risk.entry_drift_guard_atr: 0` 로 두면 가드만 즉시 무력화(재시작). 뉴스 필드는 additive라 무해.
- 전체 되돌리려면 feat/F96 revert.

## 알려진 한계 / 범위 밖
- **지정가(limit) 진입은 가드 대상 아님** — 기존 buy-the-dip/sell-the-rip 로직이 이미 상방/하방을
  캡하므로 의도적. 가드는 **무지정가 market 진입**(진짜 드리프트 갭)만 대상.
- `ref_price` 스탬프는 `price_provider` 결측/오류 시 생략(fail-honest) → 그 진입은 가드 미적용.
- **범위 밖(별도 트랙)**: 최소 ATR stop 거리 floor(#2), execute_pending 주기/time-lag 튜닝(#1).
- 테스트 `test_health_publish::test_publish_resolves_repo_root_not_above_it`는 worktree 전용
  환경 실패(main 통과) — 머지 후 main 트리에서 그린 재확인.
