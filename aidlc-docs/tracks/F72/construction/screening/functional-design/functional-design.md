# F72 / Unit "screening" — Functional Design

**Date**: 2026-06-11 · **Base**: requirements.md + workflow-plan.md (모두 승인)

## 1. 데이터 설계

### 1.1 파일 레이아웃 — `workspace/screening/`

```text
workspace/screening/
├── 2026-06-11.scan.json        # 결정적 quant 스냅샷 (코드가 씀, 날짜당 1개, 최신 실행이 덮어씀)
└── 2026-06-11.verdicts.jsonl   # LLM verdict (LLM 서브프로세스가 append, decisions.jsonl 패턴)
```

- 날짜 키 = **ET trading date** (`src/agent/turn_log.compute_et_date` 재사용, NFR-2) —
  scan(코드)과 verdicts(프롬프트 문구) **양쪽 모두** 이 키를 쓴다 (critic #2).
- `workspace/screening/`은 `Journal.init()`이 생성 (critic #3: 에이전트의 제한된
  Bash로는 mkdir 불가 — 그날 첫 scan 전에 verdict를 쓰는 순서에서도 안전).
- 워크스페이스 루트 = `AGENT_JOURNAL_ROOT` env → 없으면 `Journal().root`
  (기존 `watch` 도구와 동일한 writer/reader 일치 규약).

### 1.2 scan.json 스키마 (FR-1)

```json
{
  "et_date": "2026-06-11",
  "ts": "2026-06-11T09:31:02-04:00",
  "count": 131,
  "rows": [
    {"symbol": "AAPL", "close": 234.5, "chg_1d": 0.3, "chg_5d": 1.2, "chg_20d": 4.0,
     "rsi_14": 61.2, "macd_hist": 0.45, "vol_ratio": 1.1, "dist_high_20d_pct": -2.3},
    {"symbol": "XYZ", "error": "no data"}
  ]
}
```

- `rows`는 `market.scoreboard()` 반환값 그대로 (에러 행 포함 — 수용기준 1).
- 같은 ET 날짜 재실행 → 파일 전체를 **원자적으로 덮어씀** (tmp 파일 + `os.replace`),
  `ts`가 마지막 실행 시각.

### 1.3 verdicts.jsonl 레코드 (FR-2)

```json
{"ts": "2026-06-11T09:40:00-04:00", "symbol": "NVDA", "verdict": "passed", "reason": "RSI 82 과열 + 갭 위 진입 비대칭 — 후보 제외"}
```

- **verdict 어휘**: `entered`(결정 추가) / `watchlist`(관심 유지) / `passed`(검토 후 제외).
- append-only; 같은 날 여러 턴이면 그대로 누적 (읽기 측은 시간순 표시, dedupe 안 함 —
  검토 이력 자체가 정보).
- 읽기 측 파싱은 **관대(lenient)**: 미지의 verdict 값·필드 누락 행도 버리지 않고
  표시(fail-honest, NFR-1). 손상 행은 건너뛰고 경고 없이 나머지 표시.

## 2. 컴포넌트 설계

### 2.1 신규 `src/agent/screening_log.py` (Python, 순수 + I/O 분리)

```python
SCREENING_DIR = "screening"

def scan_path(root: Path, et_date: str) -> Path          # <root>/screening/<date>.scan.json
def verdicts_path(root: Path, et_date: str) -> Path
def record_scan(rows: list[dict], root: Path | None = None, ts: datetime | None = None) -> Path | None
    # et_date = compute_et_date(ts); mkdir -p; tmp 쓰고 os.replace (원자성)
    # 모든 예외 → logger.warning + None 반환 (fail-honest, NFR-1/SECURITY-15)
def read_scan(root: Path, et_date: str) -> dict | None    # 없음/손상 → None
def read_verdicts(root: Path, et_date: str) -> list[dict] # 관대 파싱, 손상 행 skip
```

### 2.2 캡처 훅 — `src/agent/tools/__main__.py` scoreboard 분기

```python
elif args.cmd == "scoreboard":
    symbols = args.symbols or _universe()
    out = market.scoreboard(symbols, _provider())
    screening_log.record_scan(out, root=...)   # AGENT_JOURNAL_ROOT or Journal().root
```

- `market.scoreboard()` 자체는 무변경(순수 유지) — 부수효과는 CLI 경계에만.
- `record_scan` 실패해도 `out`은 정상 출력 (수용기준 4).
- **전체 유니버스 실행만 기록** (`--symbols` 부분 실행은 저장 안 함 — critic #1:
  부분 스캔이 그날의 131종목 레코드를 덮어쓰는 사고 방지). research 외 턴/수동
  전체 실행은 동일하게 기록 — "최신 전체 스캔" 의미 유지.

### 2.3 프롬프트 의무 — `src/agent/prompts.py`

`morning_research_prompt()` step 4 (Discovery)에 추가:

> For EVERY candidate you actually examined this turn (dug into or consciously
> rejected after a look), append one JSON line to
> `screening/{ET날짜}.verdicts.jsonl` (critic #2: 프롬프트 헤더의 로컬 `today`가
> 아니라 `compute_et_date()` — 비ET 호스트의 자정 경계에서 scan 파일과 날짜가
> 갈라지는 것을 방지):
> `{"ts": "<ISO>", "symbol": "<SYM>", "verdict": "entered|watchlist|passed", "reason": "<one line>"}`.
> Do NOT write lines for names you never looked at.

- F23 병렬 research 경로의 discovery 프롬프트에도 동일 문구 추가 (코드 생성 시
  해당 프롬프트 함수 확인 후 — 같은 파일 형식이므로 충돌 없음).
- intraday/wake/eod 프롬프트는 무변경 (Out of Scope).

### 2.4 TUI verb — operator-console (`/screening [date]`)

- **parser.ts**: `READ_VERBS`에 `"screening"` 추가 (raw 인자 전달은 thesis와 동일 메커니즘).
- **filedrop.ts**: `screeningDir = join(steeringDir, "..", "workspace", "screening")` (F53 positionsDir 패턴).
  - `listScreeningDates(): string[]` — `*.scan.json`/`*.verdicts.jsonl`에서 날짜 추출, 정렬.
  - `readScreening(date: string): {scan: object|null, verdicts: object[]} | null`
    — 두 파일 모두 없으면 null; verdicts는 관대 파싱.
- **steer-handler.ts** `handleSteerRead`:
  1. `raw`에서 둘째 토큰 = 날짜 인자(선택).
  2. **검증**: `^\d{4}-\d{2}-\d{2}$` allowlist — 불일치 시
     `"(screening: invalid date, expected YYYY-MM-DD)"` (SECURITY-05; 경로 join 전 차단,
     수용기준 5).
  3. 인자 없음 → `listScreeningDates()` 최댓값(최신). 데이터 전무 →
     `"(no screening data yet)"`.
  4. 해당 날짜 데이터 없음 → `"(no screening data for <date>)"` (수용기준 3, SECURITY-15).
  5. 출력 형식:

```text
screening 2026-06-11 (scan 2026-06-11T09:31-04:00, 131 symbols):
verdicts (3):
  09:40 NVDA passed — RSI 82 과열 + 갭 위 진입 비대칭
  09:44 TMO entered — limit 진입 셋업
  09:51 HON watchlist — 지지선 재확인 대기
scan (symbol close chg1d% chg5d% chg20d% rsi volx dist20d%):
  AAPL 234.5 +0.3 +1.2 +4.0 61.2 1.1x -2.3
  ... (131행 전체, 에러 행은 "SYM error: <msg>")
```

  verdicts 없으면 `verdicts: (none recorded)` — scan만 표시(역도 동일).

### 2.5 데몬 변경 없음
콘솔이 워크스페이스 파일을 직접 읽으므로(thesis 선례) `monitor.json` 발행·runtime 변경 불요.

## 3. 오류 경로 매트릭스 (NFR-1/4, SECURITY-15)

| 상황 | 동작 |
|---|---|
| scan 저장 실패 (권한/디스크) | warning 로그, 도구 출력 정상 반환 |
| verdicts.jsonl에 손상 행 | 해당 행 skip, 나머지 표시 |
| scan.json 손상 | scan 섹션 `(scan unreadable)`, verdicts는 표시 |
| 날짜 인자 형식 오류 | 일반적 거부 문자열, 내부 정보 없음 |
| screening/ 디렉터리 없음 | `(no screening data yet)` |

## 4. 테스트 설계 (PBT Partial 포함)

**Python (`tests/agent/test_screening_log.py`)**:
- record_scan: 파일 생성/스키마/덮어쓰기/원자성(파일 내용 완전성).
- fail-honest: 읽기전용 root → 예외 없이 None (수용기준 4).
- read_verdicts: 정상/손상 행 혼재 → 관대 파싱.
- **PBT(hypothesis)**: 임의 scoreboard-형 rows(float/None/error 혼합) →
  `record_scan`→`read_scan` round-trip이 rows를 보존.

**Console (`operator-console/test/`)**:
- parser: `/screening`, `/screening 2026-06-10` readOnly 파싱.
- handler: 날짜 검증(잘못된 형식·경로 주입 거부), 최신 날짜 선택, no-data 문자열, 출력 형식.
- **PBT(fast-check — 기존 테스트가 사용 중이면; 아니면 경계값 예제로 대체)**:
  임의 문자열 날짜 인자 → 검증 통과 시 항상 `YYYY-MM-DD`이고 경로 분리자 미포함.

**프롬프트**: `morning_research_prompt()` 출력에 verdict 의무 문구 포함 단언 (기존 프롬프트 테스트 패턴 따름).

**Live smoke (Build & Test)**: 데몬 또는 수동 1회 scoreboard 실행 → scan.json 확인;
가능하면 research 턴 1회로 verdicts 생성 확인 → `/screening` 콘솔 조회 (post-merge guide에도 수록).
