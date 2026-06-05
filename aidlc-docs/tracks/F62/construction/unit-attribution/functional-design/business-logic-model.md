# Functional Design — F62 unit-attribution

> **Track**: F62 · **Unit**: attribution · **Phase**: Functional Design · **Date**: 2026-06-05

---

## 1. Data Model 변경

### 1.1 `Decision` (src/agent/journal.py) — 필드 추가
```python
class Decision(BaseModel):
    # ... 기존 필드 불변 ...
    lessons_cited: list[str] = Field(default_factory=list)  # 근거 LessonRecord.lesson_id 목록
    prompt_version: str = "seed"                            # 결정 시점 가이던스 프롬프트 버전
```
- **하위호환**: 기본값 존재 → 필드 없는 기존 decisions.jsonl 라인이 그대로 검증·로드된다.
- `prompt_version`의 기본 `"seed"`는 F64 이전(자가재작성 없음) 모든 결정을 가리키는 고정 라벨.

### 1.2 `LessonRecord` (src/agent/journal.py) — 태그 추가
```python
class LessonRecord(BaseModel):
    # 기존: lesson_id, date, category, signal_used, outcome, takeaway, times_applied
    regime: str = ""               # F65 회상 키 (예: "bull-low-vol", "high-vol")
    sector: str | None = None      # F65 회상 키 (해당 시)
```

### 1.3 효능 결과 모델 (`src/agent/efficacy.py`)
```python
class LessonEfficacy(BaseModel):
    lesson_id: str
    applied_n: int                 # 인용된(결과 매칭된) 결정 수 (= 파생 times_applied)
    win_rate: float | None         # 결과 있는 인용 중 excess>0 비율; n=0 → None
    avg_excess: float | None       # 벤치마크 대비 평균 초과수익; n=0 → None

class VersionEfficacy(BaseModel):
    prompt_version: str
    applied_n: int
    win_rate: float | None
    avg_excess: float | None
```
> **critic 반영(HIGH#2)**: `avg_excess`/`win_rate(excess>0)`를 만들려면 벤치마크(SPY/QQQ) 대비
> excess가 필요한데, 현재 `DecisionOutcome`(`quality/models.py:40`)엔 excess 필드가 없고
> `collect_outcomes`(`collector.py:259`)는 벤치마크 경로를 버린다. → **§2.1에서 collector를
> 확장**해 outcome에 `excess`를 부착한 뒤 efficacy가 그걸 읽는다. 부착 전엔 `avg_excess=None`.

---

## 2. 핵심 알고리즘 (순수 함수)

### 2.1 결정→결과 매칭 (재사용 + 확장)
F24 `src/agent/quality/collector.py:collect_outcomes()`가 decisions ↔ execution_log ↔ 가격경로를
매칭해 `DecisionOutcome`(`.decision` 포함 — **lessons_cited/prompt_version 도달 가능 ✓**)을 만든다.
**재구현하지 않고 import**하되, 두 곳을 확장한다 (critic HIGH#2):

- **(a) 숏 커버리지** — 현재 `collector.py:278`은 `action in ("BUY","SELL")`만 처리해
  **SELL_SHORT/BUY_TO_COVER(F54 숏)이 누락**된다. 필터를 숏 액션까지 넓힌다 (사용자 결정:
  "collector를 숏까지 확장"). round_trip 매칭·가격경로 로직은 방향-인지로 재사용.
- **(b) excess 부착** — `_extract_benchmark_paths`(`collector.py:222`)의 SPY/QQQ 경로로
  `benchmark_excess`(`metrics.py:138`)를 호출해 각 `DecisionOutcome`에 **`excess: float | None`
  필드를 채워 반환**한다 (collect_outcomes가 더 이상 벤치마크 경로를 버리지 않음).

효능은 이렇게 보강된 outcomes를 `lessons_cited` / `prompt_version`으로 group-by 한 얇은 집계.

### 2.2 lesson_efficacy
```
for outcome in outcomes:               # outcome.excess 부착됨 (§2.1b)
    decision = outcome.decision
    for lesson_id in decision.lessons_cited:
        if outcome.excess is not None:
            bucket[lesson_id].append(outcome.excess)
→ 각 bucket: applied_n=len, win_rate=mean(e>0 for e in bucket), avg_excess=mean(bucket)
빈 bucket(결과/excess 없음): applied_n=0, win_rate=None, avg_excess=None  (NaN/예외 금지)
```
`prompt_version_efficacy`는 동일하되 `decision.prompt_version`으로 group-by.

### 2.3 통계 가드 (경량, F72 대체)
```python
def is_meaningful(applied_n: int, effect: float, *, min_sample=20, min_effect=0.0) -> bool:
    return applied_n >= min_sample and abs(effect) >= min_effect

def persists(history: list[float], window: int = 3) -> bool:
    # 최근 window 효과가 모두 같은 부호 → 단발 노이즈 배제
    tail = history[-window:]
    return len(tail) == window and (all(x > 0 for x in tail) or all(x < 0 for x in tail))
```
- 정식 통계(Bootstrap CI/permutation)는 **F72**. 본 트랙은 표본수·효과크기·지속성의 보수적 게이트만.

---

## 3. Write-path — 누가 lessons_cited/prompt_version을 채우나 (critic HIGH#1 반영)

**중요 정정**: `Journal.append_decision`(`journal.py:120`)은 **死코드**다(호출처 0). 결정은
**LLM 서브프로세스가 `decisions.jsonl`에 직접 append**하고(`prompts.py:19` "Record … in
decisions.jsonl per the schema in CLAUDE.md"), 오케스트레이터는 `read_decisions()[before:]`로
새 결정을 **읽기만** 한다(`orchestrator.py:220`). 따라서 "append_decision에 증가 배선"은 불가능.

### 3.1 두 필드의 출처
- **`lessons_cited`** = **LLM이 emit**한다. → `templates/CLAUDE.md`의 decision 스키마에
  `lessons_cited` 추가 + 프롬프트가 "근거로 쓴 lesson_id를 적어라"라고 지시. (정직한 귀속 =
  사용자가 "필수"로 확정한 항목.) 회상이 lesson_id를 노출해야 인용 가능 → **F65 의존**(렌더에
  id 추가).
- **`prompt_version`** = **Python이 사후 스탬프**한다. LLM은 활성 버전을 신뢰성 있게 알 수 없으므로,
  오케스트레이터가 `read_decisions()[before:]`로 얻은 새 결정에 현재 `prompt_version`(F64 활성
  가이던스 버전; F64 이전엔 `"seed"`)을 찍고 **재영속(rewrite)**한다.

### 3.2 스탬핑 지점 (신규 Python 경로)
```
new = journal.read_decisions()[before:]      # LLM이 방금 쓴 결정들 (orchestrator.py:220 패턴)
for d in new:
    d.prompt_version = active_prompt_version   # Python 스탬프
journal.restamp_decisions(new)                 # 신규: torn-safe rewrite (atomic_write_text)
```
- `restamp_decisions`는 `steering/jsonl.py:atomic_write_text` 패턴으로 원자적 재기록. LLM의
  후속 append와의 레이스는 "턴 종료 직후, 다음 LLM 호출 전" 시점에 수행해 회피.

### 3.3 times_applied — 저장 말고 **read 시 파생** (critic MED 반영)
인플레이스 증가는 append-only `lessons.jsonl`을 rewrite → 크로스프로세스 LLM append와 lost-write
레이스. 대신 **저장하지 않고** read 시 순수 파생한다:
```python
def applied_counts(decisions) -> dict[lesson_id, int]:
    # Σ over decisions: lessons_cited 등장 횟수
```
- `LessonRecord.times_applied`는 직렬화 호환을 위해 필드는 두되(기본 0) **권위값은 파생**으로 본다.
  (efficacy.applied_n 과 동일 정의 → 단일 정의.) "죽은 필드 부활"이 *저장* 형태로는 불필요해짐.

## 4. 파일 터치포인트 (critic 반영 후)
| 파일 | 변경 |
|------|------|
| `src/agent/journal.py` | Decision(`lessons_cited`/`prompt_version`)·LessonRecord(`regime`/`sector`) 필드 추가; 신규 `restamp_decisions`(torn-safe rewrite); `applied_counts` 파생 헬퍼. **append_decision엔 증가 배선 안 함(死코드)** |
| `src/agent/templates/CLAUDE.md` | decision 스키마에 `lessons_cited` 추가 + "근거 lesson_id 적어라" 지시 |
| `src/agent/efficacy.py` (신규) | LessonEfficacy/VersionEfficacy + group-by 집계(outcome.excess 소비) + 통계 가드 (순수) |
| `src/agent/quality/collector.py` | **확장**: 숏 액션 처리(L278 필터) + `DecisionOutcome.excess` 부착(벤치마크 경로 보존) |
| `src/agent/quality/models.py` | `DecisionOutcome`에 `excess: float \| None = None` 추가 |
| `src/agent/orchestrator.py` | `read_decisions()[before:]` 후 `prompt_version` 스탬프 + restamp (§3.2) |
| `src/agent/tools/__main__.py` | `lesson` 서브커맨드 + argparse에 `--regime`/`--sector` (born-untagged 방지; MED) |
| golden contract / TUI `MonitorTurn` | **변경 불요**(확인됨): TS는 추가필드 무시(`use-monitor-data.ts:39`), Pydantic 기본값 OK |

## 5. 테스트 (PBT Partial)
- **하위호환**: 필드 없는 레거시 라인 로드 → 기본값. 신규 라인 round-trip.
- **집계 정확성**: 합성 decisions+outcomes에서 손계산 일치.
- **PBT**: efficacy 집계는 입력 순서 불변(교환), 빈/단일/결과없음 경계, win_rate∈[0,1] 불변,
  times_applied 합 정합.
- **가드**: min_sample 미달·단발 효과 → False (음성 테스트).
