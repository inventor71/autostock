# F88 Build & Test Summary

## Build
순수 파이썬, 빌드 단계 없음. 신규 런타임 의존: 없음(httpx는 기존, Docker는 런타임 외부 의존).
주의: triggers `enabled: true`일 때만 daemon이 Docker를 호출 — Docker 미가용이면 부팅 시 loud
error 후 triggers만 비활성(daemon 정상, critic#5).

## 테스트 실행
```
venv/bin/python -m pytest tests/triggers -q          # F88 단위 (101)
venv/bin/python -m pytest tests/triggers/test_sandbox.py -q   # 격리(실제 컨테이너; docker 없으면 skip)
venv/bin/python -m pytest -q                          # 전체 회귀
```

## 결과 (2026-06-18, main venv python 3.12)
- **F88 전체 `tests/triggers`: 101 passed.**
  - U1 models/store/ast (PBT 포함), U2 sandbox 10(실 컨테이너 격리 실증), U3 fetch 10,
    U4 evaluator 13 + wake_macro 4, U5 cli 6 + settings/schema 4.
- **전체 스위트: 1429 passed, 3 failed.**
  - 3 failed = `tests/signals/test_sentiment_sweep.py` (TestSweeper happy/symbol-failure/rate-limited).
  - **F88 무관·기존 버그**: ET_NOON이 `2026-06-12`로 하드코딩(test:17)인데 sweeper는 실시계로
    오늘 날짜에 저장 → `load_recent(now=ET_NOON)`가 미스. wallclock drift(오늘 06-18). F88은
    sentiment 파일 미수정(`git diff --name-only` 확인). main에서도 오늘 날짜면 동일 실패.
  - 권고: 별도 lean fix(sweeper에 now_fn 주입)로 처리 — F88 범위 밖(다른 트랙 테스트).
- intraday 회귀 110 passed (run_wake/wake_prompt 변경이 기존 wake 안 깨뜨림).

## 테스트 종류별
- **Unit**: models/store/ast/fetch/evaluator/settings/schema/cli (fakes, 빠름).
- **Security/격리(핵심)**: `test_sandbox.py` — src 미마운트·net=none·시크릿 비가시·timeout·fail-closed를
  실제 컨테이너로 실증(수용 기준). docker 없으면 skip(CI 환경 인지).
- **PBT(Partial 02/03/07/08)**: `test_models_pbt.py` — spec/Verdict round-trip, TTL 단조 불변, Hypothesis.
- **Integration**: register(CLI)→store→active_specs→evaluator tick→fire→WakeEvent→run_wake macro
  프롬프트 경로를 단위 결합으로 커버(evaluator + wake_macro + tools_cli). 실 daemon e2e는 라이브
  스모크로(아래 post-merge-guide).

## Security 컴플라이언스 종합 (Baseline Enabled)
SECURITY-05/06/07/09/10/13/14/15 충족(설계 §6 + U1/U2/U5 테스트 실증). 03/08/12 부분.
01/02/04 N/A. **블로킹 없음.**

## PBT 컴플라이언스 (Partial)
PBT-02/03 충족(round-trip·불변), 07 도메인 생성기, 08 Hypothesis 기본 shrink/seed. **블로킹 없음.**
