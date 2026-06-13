# F74 Build & Test Summary

## 빌드
- Python: 신규 의존성 없음 (hypothesis 기존). `src/evals/` + `src/agent/tools/fixtures.py`.
- Node: `evals/package.json` — promptfoo **0.121.15** 고정.
  `cd evals && PATH=~/.bun/bin:$PATH bun install` → `node_modules/.bin/promptfoo` 0.121.15 확인됨 (2026-06-13).

## 토큰-0 테스트 (전부 통과, 2026-06-13)
| 범위 | 결과 |
|---|---|
| 전체 스위트 `pytest tests/` | **1200 passed** (13.1s — LLM 호출 0, 수용 기준 "pytest 토큰-0" 충족) |
| F74 신규 `tests/evals/` | 127 passed — U1 fixture(15) + 스키마/채점/e2e(34-15) + 코퍼스 전수(11×8+α) + 추출기(2) |
| PBT (Partial: 02/03/07/08/09) | round-trip(INV-1, fixture store + Scenario 파일), no-silent-substitute(INV-2), behavior 매칭 불변식 ×2; 제너레이터 중앙화(`tests/evals/generators.py`); hypothesis 기본 shrinking/seed 보고 유지; CI 포함(순수 함수만) |
| promptfoo config | YAML 파싱 검증 + tests.yaml 참조 무결성 테스트 |

## 격리 증명 (수용 기준 "운영 무부수효과")
- 디스패치 인터셉트: fixture 모드에서 15개 market 명령 전부 라이브 팩토리 미호출
  (`test_all_market_commands_intercepted` — 팩토리를 호출 시 fail로 monkeypatch).
- e2e: 임시 sandbox에서만 실행(runner cwd 검증), `FIXTURE_ENV` 복원, sandbox 청소 확인.
- executor replay: execution_log이 sandbox journal에만 기록(`test_replay_logs_into_sandbox_journal`).
- 동작 보존: env 미설정 시 기존 결선 그대로(`test_no_env_uses_live_wiring`) + 기존
  tools/market 테스트 104개 무수정 통과.

## guidance 주입 증명 (수용 기준 7)
`test_pinned_guidance_reaches_prompt_and_stamp`: 핀된 g2 버전 마커가 subject 프롬프트에
존재 + 산출 decisions의 `prompt_version == "g2"` 스탬프. EOD turn은 guidance 미주입
(프로덕션 동일) 확인.

## 실 LLM 스모크 (별도 실행 — 토큰 비용)
`cd evals && bun run eval` 전체는 11 turn × 수 분. 스모크는 1개 시나리오 권장:
```bash
cd evals && PATH=~/.bun/bin:$PATH bunx promptfoo eval -c promptfooconfig.yaml \
  --filter-pattern "quiet-no-trigger" --no-cache
```
판정 기준: provider error 없음 + tier1.hard.extraction_ok=true + (관찰) behavior.matched.
Tier-2(`bun run eval:tier2`)는 ANTHROPIC_API_KEY 종량 — on-demand 전용.

## 남은 리스크
- 행동 채점은 non-blocking 설계(NFR-3) — flake rate는 운영 데이터로 축적.
- 시나리오 fixture에 없는 tool을 agent가 부르면 fixture_missing — 거동 자체가 루브릭
  관찰 대상(설계 의도).
