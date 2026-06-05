# Functional Design — F65 unit-recall

> **Track**: F65 · **Unit**: recall · **Phase**: Functional Design · **Date**: 2026-06-05
> **선행**: F62 (`lesson_efficacy`, LessonRecord.regime/sector)

---

## 1. Data Model

```python
@dataclass(frozen=True)
class SituationFingerprint:
    regime: str                       # 예: "bull-low-vol"
    vix_bucket: str                   # 예: "low" | "mid" | "high"
    breadth_bucket: str               # 시장 폭 버킷
    action_categories: tuple[str,...] # 대기 결정의 LESSON_CATEGORIES 교집합
    sectors: tuple[str,...]           # 보유/유니버스 섹터

@dataclass(frozen=True)
class ScoredLesson:
    lesson: LessonRecord
    score: float                      # 1차 점수 (FR-2.2)
    verified: bool                    # applied_n >= 임계 (F62 가드)
```

---

## 2. 파이프라인 (4단계 + 생애주기)

### 단계 1 — 상황 지문 (순수)
```python
def build_fingerprint(market_snapshot, account_snapshot, pending) -> SituationFingerprint
```
- 기존 regime.md / brief / market 데이터 재사용. 시간·랜덤 의존 없음.

### 단계 2 — 태그 사전필터 + 1차 정렬 (순수)
```python
def prefilter_and_rank(
    lessons: list[LessonRecord],
    fp: SituationFingerprint,
    efficacy: dict[str, LessonEfficacy],   # F62
    weights: RecallWeights,
    k_prime: int,
) -> list[ScoredLesson]
```
> **critic MED 선결조건**: regime/sector 매칭이 의미를 가지려면 레슨이 **생성 시점에 태깅**돼야
> 한다. 현재 `lesson` 도구(`tools/__main__.py:125`)는 regime/sector를 안 받아 모든 신규 레슨이
> 빈 태그로 태어난다. F62 FR-2.1b(도구/argparse/EOD 프롬프트 확장)가 **선행 전제**. 미태깅 레슨은
> regime 매칭에서 중립 처리(필터-아웃 아닌 관련성 0)해 폴백 안전.
- 후보 = regime/sector/category 매칭 레슨 (은퇴 레슨 제외).
- `score = w_e·eff + w_r·recency + w_rel·relevance`
  - `eff`: `efficacy[id].avg_excess` 정규화; **미검증(applied_n<임계)이면 eff 기여를 캡** (D6).
  - `recency`: 날짜 기반 지수감쇠.
  - `relevance`: 지문 태그 일치 개수/가중.
- 상위 K' 반환 (결정론: 동점은 lesson_id 사전순 tie-break → 안정 정렬).

### 단계 3 — LLM 재랭크 (비결정, cheap 턴)
```python
def rerank(candidates: list[ScoredLesson], fp, k: int) -> list[LessonRecord]
```
- 후보 K' + 지문을 보유 `claude` 브레인에 제시 → 오늘 관련 K개 id 선택.
- **폴백**: 호출 실패/타임아웃/파싱오류/id-미스매치 → `candidates[:k]`의 레슨 (FR-3.2).
  폴백은 예외를 삼키고 로그만 남긴다 (회상은 항상 성공).

### 단계 4 — 주입
```python
def build_lesson_context(selected: list[LessonRecord], max_n: int) -> str   # 기존 함수 대체
```
- **critic MED 정정**: 기존 `_build_lesson_context`(`prompts.py:198-205`)는 `- [date][category]
  takeaway`만 렌더하고 **lesson_id를 출력하지 않는다** → 에이전트가 인용할 id를 못 봄. 따라서
  **렌더에 `lesson_id`를 포함**하고, CLAUDE.md/프롬프트가 "근거로 쓴 lesson_id를 `lessons_cited`에
  적어라"라고 지시해야 F62 귀속 루프가 닫힌다. (이 변경이 없으면 lessons_cited는 영구히 빈 값.)

### 생애주기 — decay/은퇴 (EOD)
```python
def mark_retirements(lessons, efficacy, *, neg_window, idle_days) -> list[lesson_id]
```
- 효능이 `persists()`로 지속 음(-) 또는 장기 미인용 → `retired=True` 표시(LessonRecord에
  `retired: bool = False` 추가 검토; 또는 별도 은퇴 인덱스). 기록은 보존.

---

## 3. 파일 터치포인트
| 파일 | 변경 |
|------|------|
| `src/agent/recall.py` (신규) | SituationFingerprint, prefilter_and_rank(순수), rerank(+폴백), mark_retirements |
| `src/agent/prompts.py` | `_build_lesson_context` → recall.build_lesson_context 위임 (F61과 함수레벨 분리) |
| `src/agent/orchestrator.py` | `_get_lessons`/주입 경로에서 지문 조립+회상 호출 |
| `src/agent/review.py` 또는 EOD | decay/은퇴 훅 |
| `src/agent/journal.py` | (선택) LessonRecord.retired 플래그 — F62에 합치거나 본 트랙 |

## 4. 테스트
- **순수(PBT)**: prefilter_and_rank 정렬 안정성·동점 tie-break·관련성 단조·빈/경계;
  build_fingerprint 결정론.
- **폴백**: rerank 강제 실패 주입 → 1차정렬 K개 반환, 예외 없음 (음성).
- **영향 캡**: 미검증 고-excess 레슨이 검증된 동점보다 위로 안 올라옴.
- **회귀 시나리오**: 고VIX 갭다운 지문에서 관련 레슨이 recency-only 대비 상위 회상.

## 5. 미정/후속
- 가중치 `RecallWeights` 기본값은 합성 시나리오로 튜닝 후 settings 노출.
- 임베딩(Opt2)은 본 트랙 OOS — 태그+LLM이 불충분 입증 시 별도 트랙.
