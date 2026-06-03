# F6 console-sidebar-upgrade · Business Rules (Functional Design)

## 폭/드래그 (FR-1)
- **BR-1**: 사이드바 폭은 `24 ≤ width ≤ dims.width − MIN_CONTENT`로 항상 클램프. 드래그/로드/터미널 리사이즈 모두 적용.
- **BR-2**: 드래그 폭 갱신은 절대 좌표 기반 `width = dims.width − e.x` (사이드바=오른쪽, 핸들=좌측 경계).
- **BR-2.1 (critic #2 HIGH)**: DragHandle box는 **`selectable={false}`** — 없으면 OpenTUI 텍스트 선택이 `onMouseDrag`를
  가로챈다. 캡처는 첫 drag의 hit-target에 잡히므로 드래그는 핸들에서 시작해야 함. 라이브 스파이크(R1)로 거동 확정.
- **BR-3 (영속, Q3=A)**: 폭은 `onMouseDragEnd`에서 디바운스 저장. 다음 실행에서 복원. 우선순위 **저장값 > env > 42**.
- **BR-4 (fail-safe)**: 상태파일 부재/손상/범위밖 → env → 42. 콘솔은 절대 중단하지 않음.
- **BR-5**: 폭 변경은 메인 콘텐츠 폭을 동시 재계산(`contentWidth`가 동일 시그널 구독). 콘텐츠가 음수/0폭이 되지 않음.

## 데이터 발행/표시 (FR-2/3/5)
- **BR-6 (NFR-2 broker 단일경로)**: 계정 지표는 **워커의 기존 `get_portfolio_state()` 결과 + `equity_log.snapshot(ps)`
  재사용**(critic #5, 재구현 금지). 사이드바/콘솔은 broker를 직접 호출하지 않는다(권한분리 불변).
- **BR-7 (critic #1/#4)**: 라운드트립 요약은 **워커의 저빈도(30~60초) fills 집계** + `match_round_trips` 재사용 +
  **`filled_at` UTC→ET(zoneinfo) 변환** 후 오늘 필터. `trades.jsonl`(eod 전용) 파일 읽기로는 장중 빈 값이므로 금지.
  fills 소스는 F3 `get_fills` activities 포트와 공유. 거래 없음/소스 실패 → 빈 상태(`win_rate=None`, fail-closed).
- **BR-8 (무회귀, NFR-4)**: snapshot에 신규 필드(`account`/`round_trip`)가 없으면 사이드바는 해당 블록을 숨기고
  기존 표시를 그대로 유지. 구버전 데몬 + 신버전 콘솔, 그 반대 모두 동작.
- **BR-9 (가독성, FR-5)**: PnL은 `≥0` 초록(theme.success)/`<0` 빨강(theme.error). 숫자 정렬. 빈 상태 명시 문구.
  default-on/기본폭은 변경 금지(F5 소유).

## 깊은 모니터링 (FR-4)
- **BR-10 (read-only)**: turns/decisions/log 경로는 어떤 쓰기/주문 권한도 부여하지 않음. `steer_read`만 확장(read=allow).
- **BR-10.1 (critic #3)**: `steer_read` 확장은 3-파일 변경 — `parser.ts` read 동사(turns/decisions 추가), `filedrop.ts`
  monitor.json 리더(경계 내), `steer-handler.ts` verb 분기(현재 verb 무시·snapshot만 반환을 수정). "인자만 추가" 아님.
- **BR-11 (경계 유지)**: 데몬이 요약을 `steering/`(=`STEERING_DIR`) read 파일로 발행 → 콘솔/MCP는 contract 경계 안에서만 읽음.
  콘솔이 `workspace/`/`logs/`를 직접 읽지 않는다(경계·권한 일관).
- **BR-12 (원자적 발행)**: read 파일은 원자적 쓰기(temp+rename). 소비측은 torn-line 안전(기존 패턴 재사용).

## 보안/시크릿 (Security Baseline)
- **BR-13 (SECURITY-03)**: 계정/턴/로그/진단 출력에 operator token 등 시크릿을 절대 포함하지 않음. log tail 발행 시
  토큰류 라인 마스킹/제외 검토.
- **BR-14 (SECURITY-11 불변)**: 권한분리(콘솔↔에이전트, advisor-only) 변경 없음. 신규 발행 잡은 데몬 내부 read.
- **BR-15 (SECURITY-15 fail-closed)**: 발행 빌드 실패 시 기존처럼 skip+warn(부분 실패 허용), 콘솔은 빈 상태 표시.

## F5 조율
- **BR-16**: F6는 사이드바 default-on/리브랜드를 구현하지 않는다(F5 소유). 변경을 좁게 유지해 머지 충돌 최소화;
  충돌 시 F6가 리베이스.
- **BR-16.1 (critic #7)**: F5와 F6 모두 `index.tsx:236-243`의 인접 memo(`sidebarVisible`/`contentWidth`)와 `autostock.tsx`를
  건드린다 → **텍스트 충돌이 아닌 로직 충돌** 위험. 완화: 폭 시그널을 `sidebarVisible`과 **독립 context**로 분리하고,
  `contentWidth`/`Sidebar.width`/F5 가시성 토글이 **모두 같은 단일 폭 시그널**을 구독하도록 머지 계약 명시.
