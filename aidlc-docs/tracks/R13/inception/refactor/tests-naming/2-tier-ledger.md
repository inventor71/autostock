# R13 Tier Ledger — tests 네이밍/구조

범위: `tests/**` (파일·함수·클래스 이름 + 위치). 작성일: 2026-06-12

## T1 — 동작 보존 (자율 진행). 보존검증 = 수집 수 1087 동일 + 전체 green
| # | 변경 항목 | 보존되는 동작 | 검증 |
|---|-----------|---------------|------|
| 1 | 트랙ID 파일 9개 → 행동 기반 리네임(git mv) | 테스트 내용 불변, 수집 동일 | count+green |
| 2 | F-번호 함수/클래스명 2건 정합 | 동일 테스트 실행 | count+green |
| 3 | intraday 13 → `tests/intraday/`(+__init__), `intraday_` 접두 제거 | 수집 동일 | count+green |
| 4 | kis 4 → `tests/kis/`, surge 3 → `tests/surge/`(+__init__) | 수집 동일 | count+green |

## T2 — 안전한 확장
(없음)

## T3 — 의도 변경 / 기능 cut
**(없음)** — 순수 이름·위치 변경. 테스트 삭제/병합/로직 수정 일절 없음.

## 정지 지점
- [x] T3 항목 없음 — cut 상의 불요
- [x] 모든 항목 T1, 보존검증=count(1087)+green 매핑 완료
