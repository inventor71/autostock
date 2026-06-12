# F71 — Application Design (Standard)

> 3유닛(U1 server-runtime / U2 security-gate / U3 pwa-client). 기존 opencode fork 인프라
> (serve/permission/세션DB/launcher systemd) 최대 재사용.

## 0. US-8 Feasibility — ✅ 가능 (코드 검증 완료)

| 검증 항목 | 결과 | 근거 |
|---|---|---|
| 세션 저장소 | **글로벌 단일 SQLite** (프로세스별 아님) | `storage/db.ts:33` `Global.Path.data/opencode.db`; 실머신 `~/.local/share/opencode/opencode-local.db` 존재 |
| 다중 프로세스 동시 접근 | **안전** | `db.ts:104-106` `journal_mode=WAL` + `busy_timeout=5000` — TUI와 serve 동시 가동 OK |
| 원격 세션 열람 API | **있음** | `session.ts:112` `session.list` ("all sessions, most recently updated") + get/메시지 API |
| 결론 | **US-8 구현 채택** — 폰에서 TUI 세션 목록 열람/이어가기. fallback 불필요 | U3 범위에 포함 |

부수 발견: serve가 **mDNS publish**(`server/mdns.ts`, bonjour `opencode-{port}`)를 함. 단 앱이
소비 안 하고 Tailscale은 멀티캐스트 미통과 → 본 트랙 흐름과 무관(LAN 한정 보너스로만 기록).

## 1. 컴포넌트 모델

### U1 — server-runtime

**C1. `autostock serve` 서브커맨드** — `operator-console/launcher/cli.ts`
- 기존 launcher가 TUI에 쓰는 wiring(`config.ts`: `mcpServerPath`, STEERING_DIR/TOKEN env, 권한
  프로파일 머지)을 **재사용**해 `opencode serve --port 4096`을 기동.
- `OPENCODE_SERVER_PASSWORD` 필수 강제(미설정 시 기동 거부 — fail-closed, NFR-1).
- 바인드는 loopback+tailscale 인터페이스로 한정(또는 시작 시 경고 — US-7 AC3).

**C2. systemd --user 유닛** — `launcher/unit-template.ts`/`install.ts` 확장
- `autostock-serve.service` 추가(기존 데몬 유닛 패턴 복제). 부팅 자동 기동 + 크래시 재시작(US-6).

**C3. QR 페어링 표시** — `autostock serve --qr`(또는 `autostock qr`)
- tailscale IP 자동 검출(`tailscale ip -4`) → `{url, password}` JSON을 QR로 터미널 출력.
- 요청 시에만 표시, 로그 미기록(US-1 AC3).

### U2 — security-gate

**C4. WebAuthn 등록/검증 라우트** — opencode fork `server/routes/`에 추가
- `POST /autostock/webauthn/register-challenge|register` (패스키 1회 등록; credential 공개키를
  `Global.Path.data/autostock-passkeys.json`에 저장 — 시크릿 아닌 공개키).
- `POST /autostock/webauthn/assert-challenge` (서명 챌린지 발급).
- 라이브러리: `@simplewebauthn/server` (사실상 표준).

**C5. 뮤테이팅 permission 게이트 (핵심 훅)** — 기존 permission 엔진 재사용
- 흐름: 뮤테이팅 MCP 도구 호출 → opencode **permission ask** 발생(F26 프로파일로 모바일 세션엔
  뮤테이팅=항상 ask 강제) → PWA가 ask 수신 → **WebAuthn ceremony** → 서명 첨부해
  `permission.reply` 호출 → **서버가 서명 검증 후에만 approve 전달**.
- 서버측 강제(US-5 AC3): `permission.reply` 핸들러에서 *뮤테이팅 도구의 approve*는 유효한
  WebAuthn assertion 없으면 **거부**. 클라이언트 변조 무력화.
- 뮤테이팅 분류: MCP 도구 명세의 `MUTATING` 표기(mcp-server.ts에 이미 존재)를 단일 출처로 사용.
- 기존 human-order-gate/RiskManager는 데몬측에서 그대로(이중 게이트, US-5 AC4).

**C6. 모바일 권한 프로파일** — `launcher/config.ts` 권한 머지 확장
- serve 기동 시 normal 프로파일 + "뮤테이팅 MCP=ask" 오버레이. supervisor 키는 모바일에 비노출.

### U3 — pwa-client

**C7. 홈 대시보드** — `packages/app` 신규 페이지(autostock 전용 addon)
- equity/PnL·포지션·health(F69)·대기승인. 데이터는 **steer_read 패널 래핑**(결정론 슬래시 경로
  재사용; F9 패턴). 폴링 + 마지막 갱신 시각 + 수동 새로고침(US-2).
- 오프라인 표시(US-7 AC4): 헬스체크 실패 시 배너 + 마지막 데이터 시각.

**C8. 트레이스 뷰어** — 턴 목록/상세(steer_read 기반, US-3).

**C9. QR 스캔 페어링** — 카메라 스캔(`BarcodeDetector` API, 폴백 라이브러리) → 서버 등록(기존
  멀티-서버 picker 저장 재사용, US-1).

**C10. WebAuthn confirm UX** — permission ask 수신 → 작업 요약 시트 → 패스키 서명 → reply(US-5).

**C11. 세션 목록/이어가기** — `session.list`로 TUI 세션 노출 + 열람/이어가기(US-8, feasible 확정).

## 2. 시퀀스 (핵심: 뮤테이팅 confirm)

```text
폰 PWA          serve(opencode)        MCP(stdio)         데몬(파일드롭)
  │ chat: "NVDA 주문 다 취소"            │                   │
  │──────────────►│ agent가 cancel 도구 호출                 │
  │               │── permission ask (MUTATING) ─► PWA      │
  │ [요약 시트+지문]│                      │                   │
  │── assert-challenge ─►│               │                   │
  │◄─ challenge ──│                      │                   │
  │── reply(approve + WebAuthn 서명) ─►│  서명 검증(C5)      │
  │               │ 유효 ⇒ approve ─► 도구 실행 ─► steering 파일드롭
  │               │ 무효 ⇒ 거부 + 기록  │                   │ (human-gate/Risk 그대로)
```

## 3. 설계 결정

- **D1. confirm = 기존 permission 엔진에 WebAuthn을 얹음** (새 승인 채널 발명 X). F26 프로파일,
  permission.reply API, MUTATING 표기 전부 재사용 → U2가 작아짐.
- **D2. 뮤테이팅 분류 단일 출처 = MCP 도구 명세.** UI/서버가 따로 목록 들고 있지 않음(드리프트 방지).
- **D3. 패널 데이터 = steer_read 결정론 경로.** 에이전트 LLM 호출 없이(비용 0, 빠름) 패널 폴링.
- **D4. US-8 채택** (feasibility ✅). fallback 설계 불필요.
- **D5. 패스키 저장 = 공개키만** 글로벌 데이터 디렉토리(시크릿 아님). 비번/토큰과 분리.

## 4. 영향 파일 요약

| 영역 | 파일 | 유닛 |
|---|---|---|
| launcher | `cli.ts`(serve/qr 서브커맨드), `config.ts`(프로파일 오버레이), `unit-template.ts`/`install.ts`(serve 유닛) | U1, U2 |
| opencode fork | `server/routes/`(webauthn 라우트), permission.reply 핸들러(서명 검증) | U2 |
| MCP | `operator-console/src/mcp-server.ts` — MUTATING 메타를 게이트가 읽을 수 있게 정규화(필요 시) | U2 |
| PWA | `packages/app` — 대시보드/트레이스/QR/confirm/세션목록 (autostock addon 디렉토리로 격리) | U3 |
| 데몬(Python) | **변경 없음**(읽기는 기존 steering 산출물) | — |

## 5. 리스크 / 검증 포인트 (Construction에서)

- R1. permission ask가 serve HTTP/이벤트 스트림으로 PWA까지 도달하는 end-to-end 경로(이벤트 구독) — U2 첫 검증.
- R2. `BarcodeDetector` 안드로이드 크롬 지원(광범위) — 폴백 라이브러리 1개 지정.
- R3. WAL 동시성은 안전하나 TUI/serve가 **동시에 같은 세션에 쓰는** 경우의 UX(이어가기 중 TUI도 입력) — 후발 쓰기 우선, 문서화.
- R4. fork 변경량(서버 라우트)은 upstream rebase 시 충돌 표면 — autostock 라우트는 별도 파일로 격리.
