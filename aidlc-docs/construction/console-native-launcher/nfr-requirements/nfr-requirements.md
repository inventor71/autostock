# F5 NFR Requirements (유닛 `console-native-launcher`) — minimal

> 깊이: minimal. 본 유닛은 진입점/운영/UX 레이어 → NFR은 대부분 기존 결정에서 도출되어 신규 질문 라운드 불필요.

## NFR-A 신뢰성 / fail-closed (헤드라인)
- 기동 경로의 모든 `blocking` 실패 = 명확한 진단 + 비-0 종료(BR-1). silent exit 경로 0개.
- 데몬 헬스 = `snapshot.json` 신선도(E4). `health_window`/health-wait 타임아웃은 설정 상수(기본:
  health_window 15s, health-wait 타임아웃 20s, 폴 0.5s — Code Gen에서 확정/검증).
- SECURITY-15 (명시적 에러/fail-closed) — blocking.

## NFR-B 보안 / 비밀
- 토큰 값 비노출(BR-6) — 진단/로그/배너 모두 boolean만. SECURITY-03 — blocking.
- 권한분리 불변(BR-10/11) — 콘솔/런처 주문권한 없음, agent 토큰 비접근. SECURITY-11 — blocking.

## NFR-C 계약 / 무회귀
- `steering/` 파일드롭 계약 + Unit A 엔진 불변(BR-12). 파이썬 데몬 코드 변경 0 목표(BR-13).
- 기존 콘솔(NL→MCP / 사이드바 / 락다운) + 파이썬 스위트 회귀 없음.

## NFR-D 이식성
- systemd **user** 서비스 전제(Q4=A). 이 WSL2 환경에서 검증됨(systemd active, `systemctl --user` running).
- 비-systemd 환경 = 명확한 에러로 안내(재결정 단서) — 폴백 supervisor는 비범위.

## NFR-E 성능 (가벼움)
- 기동 추가 지연 최소화: 데몬 이미 active면 health 확인만(수백 ms). cold start만 health-wait 비용.
- 런타임 watch 폴 간격은 사이드바 갱신 주기(기존 1.5s)와 정합.

## 기술 스택 결론
**신규 런타임 의존 0.** 상세는 `tech-stack-decisions.md`. 신규 질문 라운드 없음(모든 결정이 FD/요구사항에서 도출).
NFR Design으로 미룬 항목: (1) 런처 동시성(헬스-웨이트 폴 × systemctl 호출), (2) systemd 유닛 정확한 필드/설치
순서, (3) 프리플라이트 모듈 경계 + 토큰 비교 위치, (4) 배너를 사이드바에 주입하는 방식.
