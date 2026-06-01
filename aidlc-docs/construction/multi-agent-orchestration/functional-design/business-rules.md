# Unit 2: multi-agent-orchestration — Business Rules

## BR-1: 모드 전환 규칙
- `multi_agent.enabled=false` → 기존 `run_morning_research()` 그대로 실행
- `multi_agent.enabled=true` + `n_agents < 2` → 설정 오류, 로그 경고 + `enabled=false`로 폴백
- `multi_agent.enabled=true` + `n_agents >= 2`:
  - `mode=sequential` → Mode B (`_run_sequential_research`)
  - `mode=parallel` → Mode C (`_run_parallel_research`)
  - 다른 값 → 로그 경고 + `sequential`로 폴백

## BR-2: Decision Counting (전체 debate = 1 research turn)
- `_run()` 대신 `_run_multi_research()`가 전체 멀티에이전트 파이프라인을 감쌈
- `before = len(journal.read_decisions())` → 전 파이프라인 → `after`
- `turn_log.record_turn(turn_type="research", ...)` 1회만 기록
- 중간 라운드에서 에이전트가 decisions.jsonl에 기록하지 않도록 프롬프트에서 명시적 지시

## BR-3: Sub-agent 격리 (Mode C)
- Sub-agent workspace = `tempfile.mkdtemp()` + 원본 journal 읽기 파일 복사
- `decisions.jsonl` 미복사 → sub-agent가 쓸 수 없음
- `allowed_tools` = 읽기 전용 (Write/Edit 미포함)
- `AGENT_JOURNAL_ROOT` = temp workspace로 override
- Sub-agent는 결과를 stdout `result`로 반환 (파일이 아닌 텍스트)
- 완료 후 `shutil.rmtree(tmp)`

## BR-4: Hard Deadline (pre-market 마감)
- timeout = `(research_start_before_open - research_end_before_open) * 60`
- 기존 `research_timeout`이 기본값(1800)이 아닌 다른 값이면 override (하위 호환)
- timeout 초과 시:
  - Mode B: 마지막 완료 라운드까지의 결과 사용
  - Mode C: 완료된 sub-agent 보고서만으로 synthesis
- 0 decisions이면 → 기존 단일 세션 1회 시도 (최후 폴백)

## BR-5: Lesson 주입 (Reflection)
- `research.reflection.enabled=true`이면:
  - `journal.read_lessons_jsonl()[-max_lessons_injected:]`를 연구 프롬프트에 주입
  - Mode B: Round 0 프롬프트에 주입
  - Mode C: Manager planning 프롬프트에 주입 (sub-agent에게는 주입하지 않음)

## BR-6: Verdict 구조화 결론
- 최종 synthesis turn의 출력에 `## Verdict` 섹션 포함 (프롬프트로 강제)
- Verdict 파싱은 best-effort (정규식으로 추출, 실패해도 research turn 전체가 실패하지 않음)
- 파싱된 verdict는 F22 AI 탑바 연동용으로 별도 파일에 저장 가능 (F22 의존, 현재는 로그만)

## BR-7: Signal 도구 가이드 주입
- `research.signals` 목록에 따라 프롬프트에 사용 가능한 도구 가이드 생성
- 예: `signals: [earnings, insider, macro]` → 프롬프트에 해당 도구 사용법 추가
- 비활성화된 시그널의 도구는 가이드에서 제외 (도구 자체는 항상 사용 가능하지만, 프롬프트에서 안내하지 않음)

## BR-8: N=1 동작
- `multi_agent.enabled=true` + `n_agents=1` → BR-1에 의해 `enabled=false`로 폴백
- 기존 단일 세션과 완전 동일하게 동작
