# F71 — User Stories (Part 2)

> 페르소나: **P1 운영자**(개발자 본인, 단일 사용자) — PC에서 autostock 데몬 운영, 외출/소파에서
> 폰으로 상태 확인·개입. 기술 숙련자.
> AC 표기: `Given / When / Then`. US-5·US-7의 AC는 Security Baseline 검증 항목과 1:1 매핑.

---

## US-1 — 폰 1회 페어링 (QR)

**As** P1, **I want** PC가 보여주는 QR(tailscale URL+비번)을 폰으로 스캔해 서버를 등록하고
**so that** 이후엔 아무 설정 없이 재접속한다.

**AC:**
1. Given serve 가동 + QR 표시 명령, When 폰 PWA로 QR 스캔, Then 서버(URL+비번)가 자동 등록되고 연결 성공이 표시된다.
2. Given 등록 완료, When PWA 재실행, Then 저장된 서버로 자동 재연결된다(재입력 없음).
3. Given QR 표시, Then QR은 요청 시에만 표시되고 화면 밖(로그/파일)에 비번이 잔류하지 않는다.

## US-2 — 한눈 상태 확인 (홈 = 대시보드)

**As** P1, **I want** 앱을 열면 바로 equity·포지션·health·대기승인 요약을 보고
**so that** 대화 없이 30초 안에 "흥넘 확인"을 끝낸다.

**AC:**
1. Given 연결된 PWA, When 앱 진입, Then 첫 화면이 대시보드이며 equity/일중 PnL, 포지션 수+심볼, health 상태(F69), 대기 승인 건수가 보인다.
2. Given 대기 승인 ≥1, When 항목 탭, Then 해당 승인 상세(steer_read)로 이동한다.
3. Given 데이터 로드, Then 마지막 갱신 시각이 표시되고 수동 새로고침이 가능하다.

## US-3 — 추론 읽기 (턴 트레이스)

**As** P1, **I want** 오늘 research/intraday/eod 턴의 논지·결정·근거를 폰에서 읽고
**so that** "왜 이 결정을 했는지" 이동 중에도 확인한다.

**AC:**
1. Given 오늘 턴 ≥1, When 트레이스 탭 진입, Then 턴 목록(유형/시각/요약)이 시간순으로 보인다.
2. When 턴 선택, Then 논지(thesis)·결정·인용 레슨이 읽기 좋게 렌더된다(steer_read 기반).
3. Given 턴 없음(주말 등), Then 빈 상태가 명확히 표시된다(에러 아님).

## US-4 — 대화 개입 (steer)

**As** P1, **I want** 폰에서 에이전트와 대화하며 언락/노트/디렉티브/answer를 보내고
**so that** 데스크톱 없이 운영 개입한다.

**AC:**
1. Given 연결된 PWA, When 채팅 탭에서 메시지 전송, Then 에이전트가 autostock MCP 도구(steer/steer_read)를 사용해 응답한다.
2. When "/unlock SYM·/note·/directive·/answer" 의도 전달, Then 해당 steering 명령이 데몬 파일드롭에 도달하고 결과가 회신된다.
3. Given steering verbs 중 비뮤테이팅, Then 서명 없이 실행된다(US-5와 경계 명확).

## US-5 — 안전한 개입 (모든 뮤테이팅 = 지문 서명, 예외 없음)

**As** P1, **I want** 주문 취소/포지션 청산/**긴급정지 포함** 모든 뮤테이팅을 지문(WebAuthn) 서명
후에만 실행하고 **so that** 폰 분실·오조작에도 자금이 보호된다.

**AC (Security Baseline 1:1):**
1. Given 뮤테이팅 도구 호출(취소/청산/긴급정지), When 실행 직전, Then 작업 요약이 표시되고 WebAuthn 서명(지문/Face)이 요구된다 — **긴급정지도 예외 없음**.
2. Given 서명 미통과/취소, Then 도구는 실행되지 않고 거부가 기록된다.
3. Given 서명 우회 시도(클라이언트 변조 등), Then **서버측**이 서명 없는 뮤테이팅 요청을 거부한다(클라이언트만의 게이트가 아님).
4. Given 서명 통과, Then 기존 서버측 게이트(human-order-gate/RiskManager)는 그대로 적용된다(이중 게이트).
5. 신규 매수/매도 주문 작성 UI/도구는 존재하지 않는다(FR-9).

## US-6 — 상시 도달 (systemd)

**As** P1, **I want** PC 부팅 후 아무 조작 없이 폰에서 항상 접속되길
**so that** "서버 켜러 PC 앞에 가는" 일이 없다.

**AC:**
1. Given PC 부팅 완료, Then serve가 systemd --user로 자동 기동되어 있다.
2. Given serve 크래시, Then systemd가 재시작한다.
3. Given serve 가동, Then 데몬·TUI의 기존 동작은 불변이다(NFR-2; serve는 추가 표면).

## US-7 — 안전 실패 (명확한 거부·표시)

**As** P1, **I want** 연결/인증 실패가 모호하지 않게 표시되길
**so that** "되는 줄 알았는데 안 된" 사고가 없다.

**AC (Security Baseline 1:1):**
1. Given tailnet 밖(또는 tailscale off), When 접속 시도, Then 도달 불가가 명확히 표시된다(무한 스피너 금지).
2. Given 잘못된 서버 비번, Then 인증 실패가 표시되고 재시도 가능하다.
3. Given `:4096`이 tailnet 밖 인터페이스에 바인드, Then 구성 검증(또는 문서화된 체크)이 이를 차단/경고한다.
4. Given 연결 끊김(서버 다운/네트워크), Then 대시보드가 오프라인 상태 + 마지막 데이터 시각을 표시한다.

## US-8 — TUI 세션 이어보기 (feasibility 게이트)

**As** P1, **I want** PC TUI에서 하던 에이전트 대화를 폰에서 열람/이어가길
**so that** 자리 이동 시 맥락이 끊기지 않는다.

**AC:**
1. [게이트] Application Design에서 serve↔TUI 세션 저장소 공유 여부 검증 결과가 문서화된다.
2. (가능 시) Given PC TUI 세션 존재, When 폰 세션 목록 진입, Then 그 세션이 보이고 열람/이어가기가 된다.
3. (불가 시) **Fallback 확정**: 폰은 별도 대화를 가지되 데몬 상태(steering)는 공유됨이 UI에 명시되고, 다운그레이드가 사용자에게 보고된다.

---

## 매핑 요약

| 스토리 | FR | NFR/Ext |
|--------|----|---------|
| US-1 | FR-3, FR-4 | NFR-4 |
| US-2 | FR-6 | NFR-4 |
| US-3 | FR-7 | — |
| US-4 | FR-5 | — |
| US-5 | FR-8, FR-9 | **NFR-1 / Security** |
| US-6 | FR-1, FR-2 | NFR-2, NFR-3 |
| US-7 | FR-3 | **NFR-1, NFR-4 / Security** |
| US-8 | FR-10 | — (feasibility) |
