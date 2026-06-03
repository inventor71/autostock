# F6 console-sidebar-upgrade · NFR Requirements (minimal)

> 깊이: minimal. 결론: **0 new runtime deps**(TS·Python 양측). 신규 질문 라운드 없음(결정은 FD에서 정착).

## 결론: 신규 런타임 의존성 0
- **TS(콘솔)**: 마우스 드래그 = OpenTUI `onMouseDown/Drag/DragEnd`(이미 존재; **핸들에 `selectable=false` 필수**, critic #2).
  폭 영속 = Node stdlib `fs`로 XDG `ui.json` 읽기/원자적 쓰기. `steer_read{view}` = 기존 `@modelcontextprotocol/sdk`/`zod`
  재사용(단 parser/filedrop/handler 3-파일 변경, critic #3).
- **Python(데몬)**: pydantic/loguru/APScheduler/alpaca-py 재사용. account = 기존 `equity_log.snapshot` 재사용(critic #5).
  라운드트립 = `match_round_trips` + **UTC→ET 변환**(`zoneinfo`, stdlib, critic #4). fills 소스 = **F3 정렬 `get_fills`
  activities 포트**(저빈도 broker 호출 — alpaca-py 0.43.2엔 Trading client에 `GetActivitiesRequest` 없음 → raw
  `RESTClient.get('/account/activities')`; 여전히 0 new deps지만 페이퍼 라이브검증 항목). monitor 발행 = `add_seconds_job` 재사용.

## 성능
- **NFR-P1 (critic #6)**: 콘솔 **읽기 폴링 1.5초**(`autostock.tsx:142`) ≠ 데몬 **발행 5초**(`agent.py:181`). 신규
  필드 최대 ~5초 지연. account/round_trip 신선도 기대치를 발행 주기 기준으로 기술.
- **NFR-P2 (critic #1 정정)**: account = 기존 `ps` 재사용으로 **추가 broker 호출 0**. **round_trip은 0이 아님** —
  fills 집계 위해 **저빈도(30~60초) broker activities 호출 1종** 추가(별도 잡). API 부하 제한 위해 발행 주기보다 느리게.
- **NFR-P3**: monitor 발행은 저빈도 잡. turns/decisions/log는 tail/요약만(전체 파일 적재 지양).
- **NFR-P4**: 드래그는 프레임당 시그널 1회 갱신 + 저장은 `onMouseDragEnd` 디바운스 → I/O 폭주 없음.

## 보안 (Security Baseline)
- **SECURITY-03**: 계정/turns/decisions/log/진단 출력에 operator token 등 시크릿 비포함. log tail 발행 시 토큰류 마스킹.
- **SECURITY-11**: 권한분리 불변. 신규 read 경로는 쓰기/주문 권한 없음(`steer_read`=read=allow).
- **SECURITY-15**: 발행 빌드/파일 I/O 실패 시 skip+warn(부분 실패 허용), 콘솔 빈 상태 폴백.

## 무회귀
- **NFR-R1**: 기존 사이드바/이벤트/contract(snapshot/events) + Python 스위트 무회귀. snapshot 신규 필드는 가산적(additive).

## PBT
- 대부분 N/A(TS UI). **부분 적용 후보(데몬 순수 함수)**: `summarize_today_round_trips` (win_rate∈[0,1], count≥0,
  realized_pnl 합 불변), 폭 클램프 함수(24 ≤ out ≤ bound) — Hypothesis(dev).

## 검증 항목(Code Gen에서)
- R1: 실제 `bun dev` TUI에서 **드래그 캡처 거동**(핸들 `selectable=false`, 첫-drag 캡처가 핸들 보유, 폭 변경) 라이브 확인(사용자, critic #2).
- R2: XDG `ui.json` 읽기/쓰기 경로 + 권한.
- R3: `steer_read{view}`가 데몬 발행 read 파일을 정확히 반환(빈/부재 시 graceful) — parser/filedrop/handler 3-파일.
- R4: `get_fills` activities 페이퍼 계정 라이브검증(raw `/account/activities` GET; F3 NFR-Req R1과 동일 항목).
