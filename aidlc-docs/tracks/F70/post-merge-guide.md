# F70 — Post-Merge Guide (섀도우 벤치마크)

## 무엇이 바뀌나 (prod 브랜치)
- 신규 `src/benchmark/` 패키지 + `src/strategy/buy_and_hold.py`.
- `config/settings.yaml`에 **`benchmark:` 섹션 추가** — **기본 `enabled: false`**.
- `run_agent`(agent 데몬)이 토글 on일 때만 백그라운드 벤치마크 러너를 띄움.
- **기본 동작 변화 없음**: 토글 off면 데몬 코드 경로·LLM 거래·주문이 이전과 100% 동일.

## 켜기 전 전제조건 (실사용)
1. **sandbox 계정 생성/확보.** baseline 5개(`buy_and_hold, ma_crossover, rsi, macd, bollinger`)
   각각에 **별도 페이퍼 계정**이 필요. `scripts/broker_create_accounts.py`로 계정 farm 생성/조회.
   계정 수가 부족하면 일부 baseline만 매핑해도 됨(나머지는 fail-closed 스킵).
2. **`.env` 자격증명.** `BROKER_API_KEY` / `BROKER_API_SECRET`(sandbox)이 설정돼 있어야 함
   (계정별 접속은 `account_id`로 분기 — 자격증명은 farm 공통).
3. **라이브 계정 ID와 절대 겹치지 않게** 매핑. 겹치면 해당 baseline은 자동 스킵(NFR-1 가드).
4. `settings.yaml`:
   ```yaml
   benchmark:
     enabled: true
     baselines: [buy_and_hold, ma_crossover, rsi, macd, bollinger]
     accounts:
       buy_and_hold: "<sandbox-acct-id-1>"
       ma_crossover: "<sandbox-acct-id-2>"
       rsi:          "<sandbox-acct-id-3>"
       macd:         "<sandbox-acct-id-4>"
       bollinger:    "<sandbox-acct-id-5>"
     interval: eod          # 또는 정수 분(예: 30)
   ```
5. **데몬 재시작**(autostock 런처) — 설정은 기동 시 로드됨.

## 실사용 검증 체크리스트 (smoke)
1. 토글 on + 계정 매핑 후 데몬 재시작 → 로그에 `benchmark: started with N baselines, cadence=eod`.
   - 계정 누락/충돌 baseline은 `... skipped` 경고로 드러남(정상, fail-closed).
2. 한 tick 경과 후(또는 `interval: 1`로 임시 단축) `data/benchmark/equity/`에 전략별 `.jsonl` 생성 확인.
   각 줄에 `equity/cash/position_count/account_masked`(시크릿 없음) 존재.
3. baseline 계정에 실제 페이퍼 체결이 들어오는지 브로커 콘솔/계정 상태로 확인(buy_and_hold면 유니버스 매수).
4. 지표 추출: `python -m src.benchmark.metrics data/benchmark`
   → `data/benchmark/metrics/<ts>.jsonl` 생성 + 콘솔에 `llm cum_return / alpha=...` 출력.
   - **정상 모습**: `alpha`가 양수면 LLM이 그 기법을 이기는 중, 음수면 지는 중.
5. 토글 off로 되돌리고 재시작 → 러너 로그 없음, 데몬 정상.

## 튜닝 노브
- `interval`: `eod`(하루 1회, 기본) ↔ 정수 분. 분 단위는 API 호출/저장 증가.
- `baselines`: 부분 집합만 운용 가능. `accounts`에 매핑된 것만 실제 가동.
- `retention_days`(기본 365): equity 시계열 보존. 컴팩션은 원천만 정리, 지표 스냅샷은 별도 보존.
- `storage_dir`(기본 `data/benchmark`, gitignore됨).

## 롤백
- 즉시 무력화: `benchmark.enabled: false` → 데몬 재시작. (코드 잔존하나 완전 비활성.)
- 완전 제거: feat/F70 revert. 다른 경로에 영향 없음(추가형 변경).

## 알려진 한계 / 범위 밖
- **ML baseline(RF/LSTM) 제외** — 학습 파이프라인·모델 부재(미학습=영원히 HOLD). 후속 트랙 영역.
- EOD = "하루 1회"이며 정확한 장마감 시각 정렬은 아님(비교 목적엔 충분).
- baseline은 LLM과 **앙상블/경쟁이 아니라 측정자**. LLM 프롬프트에 baseline 성과를 피드백하지 않음(범위 밖).
- LLM 자체 백테스트는 하지 않음(룩어헤드/비재현/비용). 백테스트 엔진은 결정론 전략 튜닝용으로만.
- 실거래(live) 미지원 — 페이퍼/샌드박스 전용.

## 라이브 스모크 메모
- 코드 검증은 fake 기반 단위테스트 + 로컬 스모크로 수행. **실제 sandbox 계정 매핑이 필요한
  end-to-end 페이퍼 체결 검증은 계정 수급(A1) 후 운영자가 위 체크리스트로 1회 수행**해야 함
  (fake로는 외부 브로커 통합을 증명할 수 없음).
