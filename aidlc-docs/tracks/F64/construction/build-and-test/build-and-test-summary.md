# Build & Test Summary — F64 헌장 경계 자가재작성

> **Track**: F64 · **Date**: 2026-06-05 · **Branch**: feat/F64 @ 861a259 (base b80656b = F65)
> **스택**: main → F62(f54d018) → F65(b80656b) → **F64(861a259)**. 미머지, 일괄 검수 예정.

## 결과: ✅ PASS
- **전체 pytest: 858 passed** (F65 838 + F64 20), 0 fail, 0 회귀. **0 new deps.**
- import 클린 (constitution/self_rewrite/orchestrator/prompts).

## 구현 (단일 유닛 unit-self-rewrite)
| 파일 | 변경 |
|------|------|
| `src/agent/constitution.py` (신규) | `AGENT_CONSTITUTION`(품질규율 6원칙) + `check_compliance`(순수 fail-closed) + `constitution_sha256` |
| `src/agent/self_rewrite.py` (신규) | GuidanceVersion/History·build_guidance·load/save·propose_rewrite·should_rewrite·maybe_rollback |
| `src/agent/orchestrator.py` | 가이던스턴 헌장 프리앰블 주입 + prompt_version 스탬프(`_stamp_new`) + EOD `_run_self_rewrite`(inert) |

## 테스트 (20건)
- **test_constitution_pin.py(11)**: 헌장 **고정 체크섬**(변경 시 red=사람 승인); 컴플라이언스 음성 —
  주문권/스탑회피/리스크우회/인젝션/헌장헤더주입/과대변경, clean 통과.
- **test_self_rewrite.py(11)**: 2층 조립(헌장 prepend); propose disabled/adopt/**reject(현재유지+lineage)**/
  held(예외); should_rewrite 게이트(쿨다운·표본); **롤백(악화 복귀/개선 유지/cold-start 보류)**; 영속 round-trip.

## v1 스코프 편차 (정직 — 검수 포인트)
1. **자가재작성 INERT (rewrite_fn=None)**: 전 기계(헌장·컴플라이언스·버전·롤백·게이트)는 구현·테스트
   했으나 orchestrator는 `_rewrite_fn=None`로 호출 → **실제 LLM 재작성은 일어나지 않음.** 활성화 =
   rewrite_fn 주입. 안전 출하: 켜기 전까지 가이던스는 seed 고정.
2. **CLAUDE.md 정적 유지(미-gut)**: 설계는 "진화 휴리스틱을 CLAUDE.md에서 제거"였으나, v1은 CLAUDE.md를
   정적 역할로 두고 **진화 가이던스를 Python 저장소(프리앰블 주입)로 추가**. 안전모델 유지 근거: 자가
   재작성 대상=Python 저장소(게이트), CLAUDE.md는 재작성 루프 밖. (에이전트의 CLAUDE.md 편집 능력은
   F64 이전부터 존재하는 별개 조건.)
3. **잔여 리스크(설계 명시)**: 에이전트 셸 접근으로 Python 저장소 덮어쓰기 이론상 가능 — 권위 사본
   cwd 밖 배치 완화는 follow-up. 현재 저장소는 workspace/guidance/history.json.
4. **드리프트 점검(원본 시드 회귀, FR-5.3)**: 미구현 follow-up. 롤백은 parent 1세대만.

## critic 반영 검증
- HIGH#3: 진화 가이던스 Python 저장소화(에이전트 직접편집 게이트 우회 차단) — build_guidance/저장소.
- prompt_version 스탬프(F62 HIGH#1): `_stamp_new` 3사이트 — 전체 테스트 통과.
- 롤백 parent-only + cold-start: maybe_rollback 테스트 확인.

## Status
Build & Test PASS → `merge-awaiting`. **검수 핵심**: 자가재작성 활성화(rewrite_fn) 여부는 머지/활성
시점의 운영 판단(현재 inert로 안전). 머지 순서 F62→F65→F64.
