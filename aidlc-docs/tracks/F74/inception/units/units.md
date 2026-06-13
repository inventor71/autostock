# F74 Units of Work

> 승인된 execution-plan.md(U1→U2→U3 의존 순서)와 application-design.md(C1~C8)를 유닛으로
> 확정. 별도 질문 없음 — 분해가 두 승인 문서에서 이미 합의됨.

## U1 — tools DataSources 팩토리 (+ fixture/record 모드)
- **컴포넌트**: C1(sources.py), C2(fixture_sources.py)
- **변경**: `src/agent/tools/{sources.py,fixture_sources.py}` 신규,
  `market.py` 8개 함수에 주입 파라미터(기본값 유지), `__main__.py` 결선 교체
- **완료 기준**: fixture 미설정 시 기존과 동일 결선(동작 보존), fixture 모드에서 13개 명령
  JSON 응답 + fail-honest, record 모드 캡처 동작. 테스트: 결선 단위 테스트 + fixture 계약
  PBT(round-trip).
- **프로덕션 접점**: 유일 — 가장 먼저, 독립 검증.

## U2 — eval harness
- **컴포넌트**: C3(scenario.py), C4(sandbox.py), C5(artifacts.py), C6(grading.py),
  C7(evals/ 글루)
- **변경**: `src/evals/` 신규 패키지, `evals/{provider.py,promptfooconfig.yaml,
  promptfooconfig.tier2.yaml,rubrics/,workspace_template/,package.json}` 신규
- **완료 기준**: 가짜 runner(_FakeRunner 패턴)로 end-to-end 토큰-0 테스트 — 시나리오 →
  sandbox → (fake) turn → 산출물 → Tier-1 채점 → provider 출력 JSON. guidance 주입 검증
  테스트(수용 기준 7). PBT: scenario round-trip + expectation 매칭 불변식.
- **의존**: U1의 fixture 모드.

## U3 — 추출기 + 시나리오 코퍼스
- **컴포넌트**: C8(extract.py) + `evals/scenarios/` 코퍼스
- **완료 기준**: 추출기 CLI가 자동 슬라이스 + TODO_MANUAL 마커 생성. 시나리오 ≥10
  (wake/intraday/eod 커버, 실사건 리플레이 우선 — 보강 소스: positions/*.md, lessons.md).
  각 시나리오는 스키마 검증 테스트 통과.
- **의존**: U2의 스키마/provider.

## 진행 방식
설계 승인 시 자율 construction이 함께 승인됨 — 유닛별 FD(경량) → Code Gen을 연속 진행,
Build & Test에서 정지(스모크 eval은 실 LLM 비용이라 사용자 안내 후 실행).
