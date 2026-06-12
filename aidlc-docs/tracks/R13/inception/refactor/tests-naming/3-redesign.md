# R13 단계 3 — Redesign (명명·구조 규칙 + 매핑표)

## 명명 규칙 (수립)
1. **테스트 파일은 검증 대상(행동/모듈) 기준**으로 명명. **트랙ID(F-번호)는 금지**
   — 머지 후 휘발하고 무엇을 검증하는지 안 드러남.
2. **구조는 `src/` 패키지를 미러**. 한 패키지에 테스트가 다수면 `tests/<pkg>/` 서브디렉터리로
   묶고 `__init__.py`를 둔다(기존 `benchmark/`·`signals/` 패턴). 단일 파일이면 평면 유지.
3. 함수/클래스명도 F-번호 제거, 행동 기술.

## 매핑표 — 파일 리네임 (git mv, 내용 불변)
| 현재 | 새 이름 | 검증 대상 |
|------|---------|-----------|
| test_f14.py | **test_daemon_wedge_resilience.py** | 데몬 wedge 복원력(HTTP timeout/BarCache/WakeDetector latch) |
| test_f56_bugfixes.py | **test_post_review_regressions.py** | 리뷰 회귀(get_daily_bar prev_close / executor cursor / early-session) |
| test_f69_health_publish.py | **test_health_publish.py** | health.json 경량 발행 |
| test_monitor_f22.py | **test_monitor_output.py** | monitor.json 구조 출력 + current_turn |
| test_sidebar_status_rich.py | **test_snapshot_enrichment.py** | 스냅샷 보강(positions/orders/account/fills) |
| test_sidebar_upgrade.py | **test_round_trip_summary.py** | 라운드트립 요약 + account 블록 + monitor 발행 |
| test_timeline_f25.py | **test_timeline_et_sessions.py** | ET-date 세션/마켓 룰/개입 |
| test_turn_dedup_f44.py | **test_turn_dedup.py** | TurnCoordinator 수동턴 dedup |
| test_turn_log_f22.py | **test_turn_log.py** | turn_id 생성/요약 빌더/record_turn |

## 매핑표 — 함수/클래스명 정합
| 위치 | 현재 | 새 이름 |
|------|------|---------|
| test_short_etb_gate.py | `def test_account_farm_broker_gets_side_from_f54_parity` | `test_account_farm_broker_gets_side_parity` |
| test_post_review_regressions.py(구 f56) | `class TestEarlySessionMonitorF56` | `class TestEarlySessionMonitor` |

## 매핑표 — 서브디렉터리 그룹화 (git mv + `__init__.py`)
- **`tests/intraday/`** ← 13개, `intraday_` 접두 제거:
  test_intraday.py→`test_pattern_detection.py`, test_intraday_bars→`test_bars.py`,
  _brief→`test_brief.py`, _fills→`test_fills.py`, _integration→`test_integration.py`,
  _news→`test_news.py`, _orchestrator→`test_orchestrator.py`, _records→`test_records.py`,
  _snapshot→`test_snapshot.py`, _util→`test_util.py`, _wake→`test_wake.py`,
  _watch→`test_watch.py`, _wiring→`test_wiring.py`.
- **`tests/kis/`** ← test_kis_broker/integration/pricing/provider → `test_broker.py` 등(접두 제거).
- **`tests/surge/`** ← test_surge_detector/store/tools → `test_detector.py` 등.

## 동치성 논증 (T1)
- 모든 변경은 git mv(파일) / 식별자 치환(이름)뿐 — import는 전부 `from src.*` 절대경로라
  파일 위치와 무관. 상호 test import·CI·문서 참조 0(단계 1 전수검사) → 깨질 표면 없음.
- `__init__.py` 추가는 기존 서브디렉터리(benchmark/signals)와 동일 패턴 → 패키지 수집 정상.

## 마이그레이션 순서 (각 단계 후 `--co` count 확인)
1. 파일 리네임 9개 → count 확인(1087).
2. 함수/클래스명 정합 2건 → green 확인.
3. intraday 그룹화(+__init__) → count.
4. kis·surge 그룹화(+__init__) → count.
5. 전체 `pytest tests/ -q` green + `--co` 1087 최종 확인.

## 범위 메모
- early_session은 단일 파일이라 평면 유지(규칙 2). 다른 평면 테스트도 단일이면 그대로.
- 동시 트랙(F73/F74)이 tests/ 추가 가능 → R13은 기존 파일 이동만(신규와 무충돌), 머지는 rebase로.
