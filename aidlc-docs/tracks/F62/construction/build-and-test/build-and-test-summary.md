# Build & Test Summary — F62 귀속/효능 기반

> **Track**: F62 · **Date**: 2026-06-05 · **Branch**: feat/F62 @ f54d018 (base 43b26d7)

## 결과: ✅ PASS
- **전체 pytest: 824 passed**, 0 fail (worktree, 메인 venv).
- import/py_compile 클린 (efficacy/journal/collector/models).
- 직접 영향 회귀: test_quality + test_short_agent + test_agent = 101 passed.
- **0 new deps** (pandas/pydantic/hypothesis 기존).

## 구현 (단일 유닛 unit-attribution)
| 파일 | 변경 |
|------|------|
| `src/agent/journal.py` | Decision += `lessons_cited`/`prompt_version`; LessonRecord += `regime`/`sector`; `restamp_decisions` |
| `src/agent/efficacy.py` (신규) | `lesson_efficacy`/`prompt_version_efficacy`/`applied_counts` + `is_meaningful`/`persists` (순수) |
| `src/agent/quality/collector.py` | 숏 액션 필터 추가 + `_attach_excess`(방향-인지 excess) |
| `src/agent/quality/models.py` | DecisionOutcome += `excess` |
| `src/agent/tools/__main__.py` | lesson `add` += `--regime`/`--sector` |
| `src/agent/templates/CLAUDE.md` | decision 스키마 `lessons_cited` + 인용 지시 |

## 테스트 (tests/test_efficacy.py — 14건)
- **하위호환**: 레거시 Decision/LessonRecord 라인(신규필드 없음) 기본값 파싱; 신규 라인 round-trip.
- **집계**: lesson_efficacy/prompt_version_efficacy 손계산 일치; 미측정(excess None) 스킵; 순서 불변.
- **가드(PBT)**: is_meaningful 표본·효과 임계 + min_sample 단조; persists 부호 일관성·짧은 윈도우.
- **applied_counts(PBT)**: Σ 정합 불변.
- **restamp**: prompt_version 재기록 round-trip, 손실/중복 없음.
- **collector excess 방향성**: BUY>0, SELL_SHORT<0(반전), SELL=None.

## critic 반영 검증
- HIGH#1(append_decision 死코드): times_applied 파생(`applied_counts`)·prompt_version restamp로 해소 — 테스트 확인.
- HIGH#2(excess 부재 + BUY/SELL만): collector 확장 + `_attach_excess` — 방향성 테스트 확인.

## 라이브 검증
- 본 트랙은 순수 데이터/스키마 레이어(신규 거래 경로 0) → 라이브 페이퍼 호출 불요. collector의
  네트워크(yfinance OHLC)는 기존 경로 재사용(변경 없음), 단위테스트는 합성 데이터로 격리.

## Status
Build & Test PASS → 트랙 `merge-awaiting`. `/ai-dlc-merge`로 머지 가능 (F62 먼저, 이후 F65→F64).
