# NFR Requirements — Unit B `operator-tool` (F4, opencode 하드 fork)

_AI-DLC 트랙 F4 · CONSTRUCTION · Unit B · NFR Requirements · 2026-05-30._
_입력: requirements §NFR + Unit B Functional Design(Q1=B′) + opencode 조사. 사전 조사: `opencode-feasibility.md`._

> **Unit A와 다른 점:** Unit A는 신규 런타임 의존성 0(순수 Python). Unit B는 **별도 언어/런타임의 대형 베이스
> (opencode)** 를 fork해 소유한다 → tech-stack 결정과 **fork-feasibility 스파이크**가 실제로 필요.

## 0. 베이스 확정 (실증됨)
- **opencode = `github.com/sst/opencode`, MIT 라이선스** → fork·리브랜딩 허용(저작권·라이선스 고지 유지 의무).
- 아키텍처: **TS 코어/서버(Bun 런타임) + Go TUI(Bubble Tea)**. fork = 양쪽 소유.
- ⚠ 레포 정체성 모호(`sst/opencode` vs `anomalyco/opencode` 리네임/포크 이력) → **스파이크에서 정식 레포·태그 확정**.

## 1. Tech stack (신규 — Unit A 대비 큼)
- **런타임/툴체인(신규):** Bun(TS) + Go(TUI). 이 Python 레포에 새 툴체인 추가.
- **베이스 의존성:** opencode 전체 + 그 deps. **baseline commit/tag 핀**(SECURITY-10) — 업스트림 추적 안 함(보안 패치만 선별).
- **배포:** 단일 브랜드 바이너리(`autostock-console`) 또는 fork에서 bun/go로 실행. 운영자 머신 로컬.

## 2. file-drop 계약 상호운용 (cross-language, 핵심 NFR)
- Unit B(TS)는 repo-root `steering/`에 **commands.jsonl append**(원자적), **events.jsonl tail**, **snapshot.json read**.
- 스키마(E7 `SteeringCommand`/E8 `SteeringEvent`/snapshot)는 **Unit A(pydantic) 소유** → TS 측 타입은 그와 **동기 유지**.
  - 결정: TS 타입을 **수기 유지 + 계약 테스트**(TS가 만든 SteeringCommand가 Unit A pydantic으로 파싱됨을 교차검증). (스키마가
    작고 안정적이라 코드 생성기는 과함 — 단, 스키마 변경 시 양쪽 갱신을 계약 테스트가 잡음.)
- 원자적 append/torn-safe는 양측 합의: 운영자=단일 write(개행 종료), 데몬=완전 라인만 소비(Unit A BR-11 이미 구현).

## 3. 보안 (Security Baseline, Q7=A)
- **SECURITY-10:** opencode baseline + 플러그인/Go·TS 의존성 **버전 핀** + 라이선스(MIT) 고지 유지.
- **SECURITY-11:** **컴파일타임 도구 봉쇄**(BR-B4) — side-effect 도구를 `steer`(+읽기)로 한정, `task`/파일쓰기/bash/web 제거.
  검증: fork 빌드에 제거 대상 미등록. confirm 무결성(BR-B1) = 결정적 레이어 소유.
- **SECURITY-03:** 토큰 env에서만 읽고 화면/로그 미표시. **SECURITY-15:** 환원/확인 fail-closed.

## 4. 성능/가용성
- 단일 운영자, 로컬. events tail/snapshot 폴은 경량. 콘솔 크래시는 데몬 무영향(별도 프로세스).

## 5. 테스트
- **TS 측**(bun test/vitest): 결정적 파서/환원, 토큰 부착, confirm 승격 불변식(example) — PBT는 환원 핵심 함수에 한해.
- **계약 테스트**(cross-language): TS 산출 SteeringCommand → Unit A pydantic 파싱 OK; Unit A 산출 events → TS 파싱 OK.
- Python 회귀: Unit B는 데몬을 안 건드리므로 기존 스위트 영향 0(별 프로세스/언어).

## 6. 선행 스파이크 (Code Gen 전 — 권장 필수)
fork는 최대 미지수라 **fork-feasibility 스파이크**를 Code Gen Part 1의 1순위로:
- (a) sst/opencode 정식 레포·태그 핀 + 빌드/실행 확인(Bun+Go).
- (b) **custom tool 등록 + 결정적 execute** 동작 확인(confirm/토큰/append).
- (c) **side-effect 도구 컴파일타임 제거** 지점 확인(소스 위치).
- (d) **커스텀 TUI pane** 추가 가능 확인(Go/Bubble Tea 1개 패널 PoC).
- 스파이크 결과에 따라 NFR Design/Code-Gen 범위 확정(불가 항목 있으면 설계 조정).

## 7. 신규 질문 없음
tech-stack 결정이 Q1=B′ + MIT 실증 + 프로젝트 기본으로 귀결. 미지수는 **사용자 분기가 아니라 스파이크로 해소**할 엔지니어링
사항(레포 정체성, 도구 제거 지점, pane 추가). NFR Design으로 이월: 프로세스/스레딩 모델(events tail goroutine × TUI 루프),
스키마 동기 메커니즘, 컴파일타임 제거 구현 패턴.
