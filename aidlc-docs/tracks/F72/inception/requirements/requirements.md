# F72 — Research 스크리닝 결과 로깅 + TUI 노출: 요구사항

**Track**: F72 · **Depth**: Standard · **Date**: 2026-06-11
**확정 방향** (사용자 답변): 캡처=둘 다(quant 스냅샷 + LLM verdict), TUI=`/screening` + 날짜 조회, Security Baseline=Yes, PBT=Partial

---

## 1. 의도 분석 (Intent)

운영자가 TUI에서 "전체 유니버스 131개 중 왜 thesis가 9개뿐인가"를 물었을 때,
에이전트의 스크리닝→필터링 과정(어떤 종목이 검토됐고 왜 패스됐는지)을 확인할 방법이
없었다. 현재 구조에서 그 정보는:

- **quant 스캔**: `python -m src.agent.tools scoreboard` (131심볼 × close/chg/RSI/MACD/
  vol_ratio/dist_high) 출력이 LLM 턴 컨텍스트로만 들어가고 **휘발**.
- **필터링 사유**: LLM이 유망 후보를 골라 deep-dive하는 reasoning이 턴 transcript에만
  존재 — 구조화되지 않고 steer 채널로 노출 안 됨. 통과한 소수만 thesis/decision으로 남음.

**목표**: 두 층위(결정적 quant 스냅샷 + LLM의 후보별 verdict)를 워크스페이스에
영속화하고, operator TUI(steer_read)에서 `/screening [date]`로 조회 가능하게 한다.

## 2. 현재 상태 (관련 코드)

| 위치 | 역할 |
|---|---|
| `src/agent/tools/market.py:100` `scoreboard()` | 전 유니버스 quant 스캔 (행 리스트 반환, 저장 없음) |
| `src/agent/prompts.py` `morning_research_prompt()` step 4 | LLM에게 scoreboard 스캔→후보 deep-dive→thesis 지시 (verdict 기록 의무 없음) |
| `workspace/` (`decisions.jsonl`, `positions/*.md`, `watchlist.md`) | LLM이 직접 쓰는 산출물 — 통과 종목만 |
| `src/agent/turn_log.py` | ET-date 키 턴 텔레메트리 (`turns.jsonl`) — ET 날짜 규약의 선례 |
| `operator-console/src/steer-handler.ts` `handleSteerRead()` | 읽기 verb 디스패치 — `/thesis`·`/theses`는 워크스페이스 파일 직접 read 패턴, `/turns`·`/decisions`는 monitor.json 슬라이스 패턴 |
| `operator-console/src/parser.ts`, `filedrop.ts` | verb 파싱 / 워크스페이스 파일 reader |

## 3. 기능 요구사항 (FR)

### FR-1: 결정적 quant 스냅샷 자동 저장
- research turn에서 `scoreboard` 도구가 실행되면 그 결과 행 전체(131심볼, 에러 행 포함)를
  워크스페이스에 **자동 저장**한다 (LLM 준수에 의존하지 않는 코드 레벨 부수효과).
- 저장 키는 **ET trading date** (`turn_log.compute_et_date` 규약 재사용 — 로컬 자정
  교차 이슈 회피). 같은 ET 날짜에 여러 번 실행되면 최신 실행으로 갱신하되 실행 시각을
  기록한다.
- 저장 실패는 **fail-honest**: 경고 로그만 남기고 도구 출력(LLM에게 가는 결과)은
  정상 반환 — 스냅샷 저장이 research turn을 깨면 안 된다.

### FR-2: LLM 스크리닝 verdict 기록 (프롬프트 의무화)
- `morning_research_prompt()` Discovery 단계에 **의무 산출물**을 추가한다: 스캔에서
  주목한 후보 각각에 대해 한 줄 verdict를 기계가 읽을 수 있는 형식으로 기록
  (예: `workspace/screening/` 아래, 최소 필드 `symbol`, `verdict`, `reason`, `ts`).
- verdict 어휘(예: `entered` / `watchlist` / `passed`)와 정확한 파일 형식·경로는
  Functional Design에서 확정한다.
- 대상 범위: LLM이 **실제 검토한 후보**(통상 5~20개). 검토되지 않은 나머지 유니버스는
  FR-1 quant 스냅샷으로 커버된다(전수 사유 기록을 LLM에 강제하지 않음 — 비현실적).
- decisions.jsonl과 동일하게 LLM 서브프로세스가 직접 쓰는 패턴을 따른다.

### FR-3: TUI 조회 — steer_read `/screening [date]`
- 새 read-only verb `/screening`:
  - 인자 없음 → 가장 최근 ET 날짜의 스크리닝 결과 (quant 스냅샷 요약 + LLM verdict 목록).
  - `/screening 2026-06-10` → 해당 ET 날짜의 결과.
- 출력은 두 층위를 함께 보여준다: ① LLM verdict (종목 + 판정 + 사유), ② quant 스냅샷
  (전 종목 또는 컴팩트 요약 — 표시 형식은 설계에서 확정).
- 데이터 없는 날짜는 명확한 안내 문자열 반환 (`(no screening data for <date>)`) —
  thesis verb의 기존 관례를 따른다.
- 읽기 전용 경로: 주문 권한 없음, 게이트 없음 (기존 steer_read 관례).

### FR-4: 보존
- 날짜별 파일로 보관하여 과거 조회(FR-3 날짜 인자)를 지원한다.
- 별도 회전/삭제는 도입하지 않는다 (기존 워크스페이스 JSONL들과 동일 정책 —
  파일당 수십 KB 수준으로 부담 없음).

## 4. 비기능 요구사항 (NFR)

- **NFR-1 (fail-honest)**: 스냅샷 저장·verdict 파일 부재·파싱 실패가 research turn
  진행이나 다른 steer_read verb를 절대 막지 않는다.
- **NFR-2 (ET-date 일관성)**: 모든 날짜 키는 ET trading date — `turns.jsonl`(F25)과
  동일 규약, 동일 헬퍼 재사용.
- **NFR-3 (입력 검증)**: `/screening`의 날짜 인자는 콘솔 측에서 형식 검증
  (`YYYY-MM-DD` allowlist regex) 후 파일 경로에 사용 — 경로 조작 불가
  (SECURITY-05).
- **NFR-4 (fail-closed 응답)**: 파일 없음/손상 시 내부 오류 노출 없이 일반적 안내
  문자열 반환 (SECURITY-15).
- **NFR-5 (민감정보 없음)**: 기록 내용은 공개 시장 데이터와 에이전트 판단 텍스트뿐 —
  토큰/계정정보가 스크리닝 레코드에 포함되지 않아야 한다 (SECURITY-03).

## 5. Extension 룰 적용 매핑

**Security Baseline (Enabled)** — 적용 가능 룰:
- SECURITY-03 (구조적 로깅): Loguru 기존 인프라 사용, 민감정보 미기록 → NFR-5.
- SECURITY-05 (입력 검증): `/screening` 날짜 인자 검증 → NFR-3.
- SECURITY-15 (예외 처리/fail-safe): 저장·조회 오류 경로 → NFR-1, NFR-4.
- 나머지 (01,02,04,06~14): N/A — 신규 네트워크 endpoint·인증·암호화 자산·배포 인프라
  변경 없음 (로컬 파일 기록 + 기존 read-only 채널 내 verb 추가).

**Property-Based Testing (Enabled — Partial)**:
- 스크리닝 레코드 직렬화/파싱 round-trip property test.
- 날짜 인자 검증 함수(임의 문자열 → 절대 경로 탈출 불가) property test.
- 그 외(오케스트레이션, 프롬프트, TUI 출력 형식)는 예제 기반 테스트.

## 6. 범위 제외 (Out of Scope)

- intraday/wake/eod 턴의 스크리닝 기록 (research 턴 한정; scoreboard 자동 저장은
  도구 레벨이라 다른 턴에서 실행돼도 무해하게 동작하지만, verdict 의무는 research만).
- 과거 턴 transcript 소급 파싱 (이번 트랙 이후 데이터부터 쌓임).
- TUI 전용 시각화 위젯/패널 (steer_read 텍스트 응답으로 충분 — 운영자는 대화형 조회).
- 스크리닝 결과 기반 자동 필터/알림.

## 7. 수용 기준 (Acceptance)

1. research turn 1회 실행 후 해당 ET 날짜의 quant 스냅샷 파일이 존재하고 131개
   심볼 행을 담는다 (에러 행 포함).
2. 같은 턴에서 LLM이 verdict 파일에 검토 후보별 `symbol/verdict/reason`을 남긴다
   (프롬프트 준수 — live smoke로 확인).
3. TUI에서 `/screening` → 최신 결과(두 층위), `/screening <과거날짜>` → 해당 날짜
   결과, 없는 날짜 → 안내 문자열.
4. 스냅샷 저장 경로를 인위적으로 막아도 scoreboard 도구는 정상 출력을 반환한다.
5. 날짜 인자에 경로 문자(`../` 등) 주입 시 거부된다.
