# F74 Post-Merge Guide — Prompt Eval & Regression Framework

## 무엇이 바뀌나
- **신규**: `evals/`(promptfoo 글루 + 시나리오 11종 + 루브릭), `src/evals/`(파이프라인 코어),
  `src/agent/tools/fixtures.py`.
- **프로덕션 접점 1곳**: `src/agent/tools/__main__.py` 디스패치에 fixture/record 인터셉트 —
  **env 미설정 시 동작 동일**(테스트로 증명). 데몬 재시작 불필요(라이브 경로 무변경),
  단 재시작해도 무해.

## 전제 조건
- Tier-1 실행: `claude` CLI 로그인(구독 OAuth) — 기존 데몬과 동일. API key 불필요.
- Tier-2 실행: `ANTHROPIC_API_KEY` (종량 과금). 환경에 두지 말고 실행 시에만 주입 권장:
  `ANTHROPIC_API_KEY=... bun run eval:tier2`
- 최초 1회: `cd evals && PATH=~/.bun/bin:$PATH bun install`

## 실사용 검증 체크리스트 (머지 후 1회)
1. **스모크 (시나리오 1개, ~수 분, 구독 토큰)**
   ```bash
   cd evals && PATH=~/.bun/bin:$PATH bunx promptfoo eval -c promptfooconfig.yaml \
     --filter-pattern "quiet-no-trigger" --no-cache
   ```
   정상: PASS 1/1 (hard assert), output JSON에 `tier1.behavior.matched` 표기.
   `bun run view`로 뷰어에서 응답/채점 확인.
2. **운영 무부수효과 확인**: 스모크 후 `git status workspace/` 변화 없음 +
   `workspace/decisions.jsonl` 끝줄 timestamp가 스모크 이전임을 확인.
3. **record 모드 (선택)**: 데몬 환경에 `AUTOSTOCK_TOOLS_RECORD_DIR=/tmp/tool-capture` 1일
   설정 → turn의 tool 응답이 fixture 포맷으로 캡처되는지 확인 → 이후 실사건 시나리오의
   자동 소스. (라이브 영향: 없음 — 저장 실패도 fail-soft)

## 운용 패턴
- **프롬프트/CLAUDE.md 수정 시**: 수정 브랜치에서 `bun run eval` → main 결과와 뷰어
  비교(side-by-side). 행동 체크는 비차단 시그널 — 같은 시나리오의 PASS↔FAIL 플립이
  반복 관찰될 때만 회귀로 취급.
- **F64 guidance 후보 검증**: `tests.yaml`에 `guidance_file`/`guidance_label` 행 추가
  (예시 행 참조) → 같은 시나리오의 seed vs 후보 비교.
- **새 lesson 등록 시**: 시나리오 1개 추가 권장 —
  `python -m src.evals.extract --date ... --symbol ... --turn-type ...` 후 TODO_MANUAL
  보강(1차 소스: positions/*.md Call-vs-Outcome) + `tests.yaml` 행 추가 +
  `pytest tests/evals/test_corpus.py`.

## 튜닝 노브
- `evals/promptfooconfig.yaml` `maxConcurrency`(기본 1 — 구독 rate limit 보호),
  provider `config.model`(기본 sonnet) / `config.timeout`.
- 루브릭: `evals/rubrics/common.md` (pass threshold 0.6).

## 롤백
eval은 라이브 경로와 분리 — 문제 시 `evals/`+`src/evals/` 미사용으로 충분.
tools 인터셉트까지 되돌리려면 `src/agent/tools/__main__.py`의 F74 블록 +
`fixtures.py` revert (다른 코드 의존 없음).

## 한계 / Out of scope (v2)
- F64 채택-전 자동 게이트(현재는 수동 비교 패턴), morning 3-round 시나리오,
  red-team 자동 생성, 웹 스텁(현재 웹 허용 — 시나리오는 실사건 리플레이 우선),
  nightly 자동화. 행동 채점은 의도적으로 비차단(NFR-3).
