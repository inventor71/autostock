# F25 타임라인 바 개선 — Build & Test Summary

## 결과
- **Python**: 555 passed, 0 regression (Unit A: 15 신규 test_timeline_f25 + F22 테스트 et_date 모델로 갱신)
- **TypeScript**: tui-trading 13 tests pass (timeline-layout PBT: tz offset, wall→epoch, session bounds, layout placement, shiftDate)
- **Typecheck**: opencode 패키지 0 errors (tui-trading 번들 포함)
- **Import smoke**: Python OK, compute_et_date 동작 확인
- **0 new runtime deps** (Python: zoneinfo stdlib / TS: Intl 표준)

## Unit A (daemon-timeline, Python)
- `compute_et_date()` — ET 거래일 키 (자정 넘김 해결)
- monitor.json: `market` 규칙 + `session_et_date` + full-ISO `ts` + `et_date` 세션 필터 + `interventions[]`(거래만)
- turn ID 시퀀스도 et_date 키 (세션 중 KST 자정에 리셋 안 됨)

## Unit B (timeline-ui, TypeScript)
- 12h market-aware 레이아웃: epoch 기반 + IANA tz (DST 자동)
- 3구간 배경(pre/regular/after) + 마켓 경계선 + 로컬시간 라벨
- 날짜 네비게이션(마우스 `< Today >`), 무제한 히스토리(파일 직접 읽기)
- human 마커(✚) + InterventionOverlay

## Security Baseline
- SECURITY-03: intervention 직렬화에 토큰/시크릿 없음(InterventionRecord safe_view), log 레닥션 유지
- SECURITY-15: 시간대 변환/파일 읽기 fail-safe (파싱 실패 스킵, 빈 리스트 degrade)

## 보류 (후속 트랙)
- 키보드(← → T) + `/timeline <date>` slash command — opencode 중앙 keymap 통합 (파손 위험). 마우스 네비로 기능 충족.
- 공휴일 캘린더(Q8=A로 빈 바 허용) — Alpaca calendar 조회 미적용
