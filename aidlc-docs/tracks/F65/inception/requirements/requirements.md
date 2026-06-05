# F65 — 하이브리드 회상 요구사항

> **Track**: F65 · **Phase**: Requirements Analysis · **Depth**: Standard
> **Date**: 2026-06-05 · **언어**: 한국어 · **선행**: F62 (귀속/효능 기반)

---

## 1. Intent Analysis

### 1.1 문제
레슨이 **recency만**으로 주입됨 (`prompts.py:198` `_build_lesson_context`,
`lessons[-max_n:]`, N=10). 결과:
- 오늘 시장맥락과 무관한 레슨이 관련 레슨을 밀어냄.
- 효능 순위 부재 — 운 좋게 한 번 맞은 레슨과 검증된 레슨이 동급.

### 1.2 핵심 의도
recency 절단을 **상황 기반 회상**으로 대체: 오늘 시장맥락에 가장 관련되고 **입증된 효능**이 높은
레슨을 회상한다. 신규 의존(벡터DB) 없이, 프로젝트의 "결정론·감사가능·0 new deps" 관행 유지.

### 1.3 요청 유형
- **Type**: Internal agent capability (recall quality)
- **Scope**: 신규 recall 모듈, `prompts.py` `_build_lesson_context` 대체, `orchestrator.py`
  주입 경로, EOD decay/은퇴 훅.
- **Complexity**: Moderate (순수 랭킹 + 1회 LLM 재랭크 + 폴백)

---

## 2. 설계 결정 (확정)

| # | 영역 | 결정 | 근거 |
|---|------|------|------|
| D1 | 회상 메커니즘 | **하이브리드** — 태그 사전필터 → LLM 재랭크 | UAQ 확정. 벡터스토어 불요, 보유 브레인 활용 |
| D2 | 임베딩 | **배제** (v1) | 신규 dep·비결정·감사난이도; 태그로 시작 |
| D3 | 랭킹 신호 | 효능(F62) × recency × 관련성 | 검증된 레슨 우선 |
| D4 | 비결정 격리 | 1·2단계 순수, 3단계만 LLM | 단위테스트 가능 유지 |
| D5 | 폴백 | 재랭크 실패 시 1차 정렬 사용 | graceful, 턴 실패가 회상 전체를 죽이지 않음 |
| D6 | 오염 방지 | 미검증 레슨(applied_n<임계) 영향 캡 | 운 좋은 단발 레슨 전파 차단 |
| D7 | 생애주기 | 모순·낡은 레슨 decay·은퇴(EOD) | 무한 누적·레짐 드리프트 방지 |

---

## 3. Functional Requirements

### FR-1: 상황 지문 (Situation Fingerprint)
- **FR-1.1** Python이 매 회상 전 상황 지문을 조립한다: `{regime, vix_bucket, breadth_bucket,
  pending_action_categories, sectors}`. (가능한 한 기존 brief/regime 데이터 재사용.)
- **FR-1.2** 지문 조립은 순수 함수 (입력=시장/계좌 스냅샷, 출력=지문 dataclass).

### FR-2: 태그 사전필터 + 1차 정렬 (순수)
- **FR-2.1** 후보 = 지문의 `regime`/`sector`/카테고리와 매칭되는 레슨 (LessonRecord 태그, F62).
- **FR-2.2** 1차 점수 = `w_e·efficacy + w_r·recency + w_rel·relevance` (가중치 settings).
  효능은 F62 `lesson_efficacy`에서, 미검증 레슨은 효능 기여 캡(D6).
- **FR-2.3** 상위 K'개를 LLM 재랭크 후보로 전달 (K' settings, 예: 20).

### FR-3: LLM 재랭크 (비결정, cheap 턴)
- **FR-3.1** 후보 K'개 + 오늘 지문을 보유 `claude` 브레인에 주어 "오늘 진짜 관련 K개"를 선택.
- **FR-3.2** **폴백 (FR-3.2)**: 재랭크 호출 실패/타임아웃/형식오류 시 FR-2 1차 정렬 상위 K개 사용.
  회상은 절대 빈손/예외로 끝나지 않는다.

### FR-4: 주입
- **FR-4.1** 선택된 K개를 리서치/인트라데이 프롬프트에 주입 (`_build_lesson_context` 대체).
- **FR-4.2** 렌더에 **`lesson_id`를 포함**한다 (critic MED 정정: 기존 `_build_lesson_context`는
  id 미출력 → 인용 불가). + CLAUDE.md/프롬프트가 근거 id를 `lessons_cited`에 적도록 지시 →
  F62 귀속 루프 연결. **선행 전제**: F62 FR-2.1b(레슨 생성 시 regime/sector 태깅).

### FR-5: 생애주기 (decay/은퇴)
- **FR-5.1** EOD 통합 스텝에서, 효능이 지속적으로 음(-)이거나 장기 미인용 레슨을 은퇴 표시.
- **FR-5.2** 은퇴 레슨은 회상 후보에서 제외하되 기록은 보존(감사).

---

## 4. Non-Functional Requirements
- **NFR-1 (결정론 격리)**: 1·2·5단계 순수·단위테스트. 비결정은 3단계 1회 LLM 호출로 한정.
- **NFR-2 (성능/비용)**: 재랭크는 저빈도 턴(아침/EOD)만; K' 상한으로 토큰 통제.
- **NFR-3 (0 new deps)**: 벡터스토어/임베딩 라이브러리 도입 금지 (v1).
- **NFR-4 (회상 안전)**: 폴백 항상 동작; 회상 실패가 리서치 턴을 막지 않음.

---

## 5. 검증 기준 (Acceptance)
1. 동일 지문·동일 레슨셋에서 1차 정렬 결정론 (단위테스트).
2. 재랭크 호출 실패를 주입 시 → 1차 정렬 K개로 폴백, 예외 없음.
3. 미검증 레슨이 검증된 동점 레슨보다 위로 못 올라옴 (영향 캡 검증).
4. recency-only 대비, 합성 시나리오에서 관련 레슨 회상률 개선 (회귀 시나리오).
5. 전체 pytest green, 0 new deps. (회상은 F62 효능 API에 의존 → F62 선행 머지.)
