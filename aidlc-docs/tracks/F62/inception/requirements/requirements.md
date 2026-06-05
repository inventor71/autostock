# F62 — 귀속/효능 기반 요구사항

> **Track**: F62
> **Phase**: Requirements Analysis
> **Depth**: Standard (내부 데이터 레이어, 신규 거래 경로 없음, 후속 트랙의 전제)
> **Date**: 2026-06-05
> **언어**: 한국어

---

## 1. Intent Analysis

### 1.1 배경
자가학습 에픽(F62→F65→F64) 설계 토론에서, F65(회상)과 F64(자가재작성)이 **공통으로 의존하는
빠진 1차 조각**이 식별되었다: "레슨/프롬프트버전 → 결정 → 결과"의 **닫힌 귀속 링크**와 그 위의
**효능 스코어**. 현재:
- F24 결정품질 메트릭(`src/agent/quality/`)은 측정만 하고 에이전트 행동으로 피드백되지 않음.
- `LessonRecord.times_applied`(`src/agent/journal.py:43`)는 선언만 되고 **한 번도 증가하지 않는
  죽은 필드** → 레슨이 실제로 도움됐는지 신호 0.

### 1.2 핵심 의도
1. 결정이 **어떤 레슨을 근거로** 했고 **어떤 프롬프트 버전**에서 나왔는지 박제(귀속).
2. 결정→체결→결과 매칭(F24 collector 보유)을 재사용해 **레슨별·프롬프트버전별 효능** 산출.
3. 효능을 "통계적으로 의미있는지" 판정하는 **경량 인라인 가드** 제공 (소표본 과적합 방지).
4. 전부 **순수·결정론·하위호환** — 신규 거래 경로/외부 호출/LLM 호출 없음.

### 1.3 요청 유형
- **Type**: Internal data/infrastructure layer (enabling)
- **Scope**: `src/agent/journal.py` (스키마), `src/agent/quality/collector.py` (재사용),
  신규 `src/agent/efficacy.py`. 레슨 인용 증가 배선 1곳.
- **Complexity**: Moderate (스키마 하위호환 + 순수 집계; 거래 로직 무관)

---

## 2. 설계 결정 (확정)

| # | 영역 | 결정 | 근거 |
|---|------|------|------|
| D1 | 귀속 필드 | Decision에 `lessons_cited: list[str]` + `prompt_version: str` 추가 | 정직한 효능 귀속을 위해 필수 (UAQ 확정) |
| D2 | 하위호환 | 두 필드 기본값(`[]` / `"seed"`) → 기존 라인 무손상 | 운영중 decisions.jsonl 보존 |
| D3 | 회상 태그 | LessonRecord에 `regime`/`sector` 추가 | F65 상황 회상 키 |
| D4 | times_applied | 본 트랙에서 **증가만** 배선 (소비는 F65) | 죽은 필드 부활, 책임 분리 |
| D5 | 효능 산출 | F24 collector 재사용, LLM 호출 없음 | 결정론·기존 자산 활용 |
| D6 | 통계 가드 | 경량 인라인(min_sample/효과크기/지속성), 정식 통계는 F72 | 소표본 과적합 방지하되 스코프 절제 |
| D7 | Security | Enabled (SECURITY-03만 적용, 나머지 N/A) | 프로젝트 관행 |
| D8 | PBT | Partial (Hypothesis) — 순수 집계/가드 함수 | 직렬화·단조성·경계 |

---

## 3. Functional Requirements

### FR-1: 결정 귀속 (Decision Attribution)
- **FR-1.1** `Decision`에 `lessons_cited: list[str] = []` 필드를 추가한다 (이 결정의 근거가 된
  `LessonRecord.lesson_id` 목록).
- **FR-1.2** `Decision`에 `prompt_version: str = "seed"` 필드를 추가한다 (결정 생성 시점의
  활성 가이던스 프롬프트 버전 식별자).
- **FR-1.3** 기존 decisions.jsonl 라인(두 필드 없음)은 기본값으로 무손상 파싱되어야 한다
  (Pydantic 기본값 하위호환).

### FR-2: 레슨 레코드 확장
- **FR-2.1** `LessonRecord`에 `regime: str = ""` + `sector: str | None = None` 태그를 추가한다.
- **FR-2.1b** (critic MED) `lesson` 도구(`tools/__main__.py`)·argparse·EOD 프롬프트를 확장해 레슨
  생성 시 `regime`/`sector`를 채운다 (안 하면 항상 빈 태그 → F65 회상키 무력화).
- **FR-2.2** `times_applied`는 **저장하지 않고 read 시 파생**한다 (`Σ` over `lessons_cited`).
  인플레이스 증가는 append-only `lessons.jsonl`과 레이스하므로 금지 (critic MED). 필드는 직렬화
  호환용으로 두되 권위값은 파생.

### FR-2c: Write-path (critic HIGH#1)
- **FR-2c.1** `append_decision`은 死코드 — 결정은 LLM이 `decisions.jsonl`에 직접 쓴다. `lessons_cited`
  는 **LLM이 emit**(CLAUDE.md 스키마+프롬프트 지시), `prompt_version`은 **Python이 사후 스탬프**
  (`read_decisions()[before:]` 후 torn-safe rewrite).

### FR-3: 효능 스코어 (`efficacy.py`, 순수)
- **FR-3.1** `lesson_efficacy(decisions, outcomes) -> dict[lesson_id, LessonEfficacy]`를 제공한다.
  `LessonEfficacy = {applied_n, win_rate, avg_excess}`.
- **FR-3.2** `prompt_version_efficacy(decisions, outcomes) -> dict[version, VersionEfficacy]`를
  제공한다 (동일 메트릭, 프롬프트 버전 단위 집계).
- **FR-3.3** 결정→결과 매칭은 F24 collector(`collect_outcomes`)를 재사용하되 **확장**한다 (critic HIGH#2):
  (a) 숏 액션(SELL_SHORT/BUY_TO_COVER) 처리 — 현재 BUY/SELL만; (b) `DecisionOutcome.excess` 부착 —
  현재 벤치마크 경로를 버려 excess 산출 불가. 확장 후 efficacy는 `outcome.excess`를 읽는다.
- **FR-3.4** 결과/excess가 없는 레슨/버전은 `applied_n=0`, `win_rate/avg_excess=None` (NaN/예외 금지).

### FR-4: 통계 가드 (경량 인라인)
- **FR-4.1** `is_meaningful(applied_n, effect, *, min_sample, min_effect) -> bool` 순수 함수 —
  표본 수·효과크기 임계를 동시 충족할 때만 True.
- **FR-4.2** `persists(history: list[float], window) -> bool` — 효과가 최근 window에서 부호/방향
  일관성을 유지하는지 (단발 노이즈 배제).
- **FR-4.3** 임계 기본값은 settings로 조정 가능하되, 보수적 기본(예: `min_sample≥20`).

---

## 4. Non-Functional Requirements
- **NFR-1 (결정론)**: efficacy/가드는 동일 입력에 동일 출력. 시간·랜덤 의존 금지.
- **NFR-2 (하위호환)**: 스키마 변경은 추가-only. 기존 워크스페이스 무손상.
- **NFR-3 (성능)**: 집계는 O(decisions+outcomes); 일/세션 단위 호출이라 비병목.
- **NFR-4 (0 new deps)**: 기존 pandas/pydantic만. 신규 런타임 의존 없음 (F23/F24 관행).
- **NFR-5 (관측성)**: 효능 산출은 기존 quality CLI/JSON 출력에 합류 가능한 형태.

---

## 5. 검증 기준 (Acceptance)
1. 기존 decisions.jsonl(필드 없는 라인) 로드 시 예외 없음 + 기본값 채워짐.
2. 레슨 인용 1회 → 해당 `times_applied` 정확히 +1, 영속.
3. `lesson_efficacy`/`prompt_version_efficacy`가 합성 데이터에서 손계산과 일치 (단위테스트).
4. 빈 입력·결과없음·단일표본에서 가드가 `False`로 안전 동작 (PBT 경계).
5. 전체 pytest green + py_compile/import 클린, 0 new deps.
