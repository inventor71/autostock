# F85 — Workflow Planning

## 실행할 단계와 깊이
| 단계 | 실행 | 깊이 | 근거 |
|------|------|------|------|
| Workspace Detection | ✅ | — | brownfield 확인 완료 |
| Reverse Engineering | ⏭️ skip | — | 아티팩트(codekb) 존재, 조사로 충분 |
| Requirements Analysis | ✅ 완료 | standard | 조사+critic+기존자산까지 |
| User Stories | ⏭️ skip | — | 신규 사용자 페르소나/워크플로 없음 (운영자 단일 config 다이얼). 순수 내부 행동 변경 |
| Workflow Planning | ✅ | — | 본 문서 |
| Application Design | ✅(경량) | minimal | 신규 모듈 1개(preset) + Decision 스키마 확장 — 컴포넌트 경계 명시 필요 |
| Units Generation | ⏭️ skip | — | 단일 응집 단위. 분해 시 인터페이스 오버헤드만 증가 |
| Functional Design | ✅ | standard | 데이터 모델(preset 표/Decision 필드/grade 영속) + C3 maturity 규칙 |
| NFR Requirements/Design | ✅(경량) | minimal | 성능 영향 미미(EOD 채점 경로). 안전/하위호환은 Security Baseline로 흡수 |
| Infrastructure Design | ⏭️ skip | — | 신규 인프라 없음 (로컬 config + 기존 파일) |
| Code Generation | ✅ | — | worktree feat/F85 생성 후 |
| Build & Test | ✅ | — | unit + property-based + F74 시나리오 스모크 |

## 변경 시퀀스 (의존 순서)
1. **설정 계층** — `config/config.py`(field_validator), `config/settings.yaml`(키 추가).
2. **SSOT preset 모듈** — 레벨→(risk overlay, prompt disposition, grading_horizon, recency weight) 단일 표.
3. **Decision 스탬핑** — `journal.py`(필드 추가) + `orchestrator.py`(stamp; F62 자리 확장).
4. **리스크 레이어** — `main.py` 두 RiskManager 구성에 preset overlay 적용.
5. **프롬프트 레이어** — `prompts.py` 빌더 전수 + `orchestrator.py` 와이어링 + `main.py` 주입.
6. **학습 레이어** — `quality/collector.py`+`efficacy.py`(maturity 게이트+grade 영속), `recall.py`/`orchestrator.py:321`(recency weight).
7. **검증 자산** — `evals/tests.yaml` 레벨 시나리오 + `guidance_label`.
8. **테스트** — unit/property/integration.

## 산출물 경로
- 설계: `aidlc-docs/tracks/F85/inception/application-design/`, `construction/<unit>/functional-design/`
- 코드: worktree `feat/F85` (Code Gen Part 2 전 생성).
