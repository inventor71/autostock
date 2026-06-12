# F71 — Post-Merge Guide (모바일 operator 기반)

> 이 머지분 = **기반**(서버 + 보안 게이트 + 클라이언트 로직). **폰 화면(UI)은 F72 후속.**
> 따라서 지금은 "API/보안이 동작하는지"까지 검증 가능하고, 풀 앱 사용은 F72 이후.

## 무엇이 바뀌나 (prod 브랜치)
- 신규 런처 서브커맨드 **`autostock serve`**(헤드리스 opencode 서버, tailnet 전용 바인드) / **`autostock qr`**(페어링 QR).
- systemd `autostock-serve.service`(install이 enable; 자동 시작 X — 전제 충족 후 수동/재부팅).
- opencode fork에 **WebAuthn 보안 게이트**: 원격(비-loopback) 뮤테이팅 승인은 패스키 서명 필요.
- **기존 동작 무변화**: `serve` 미기동이면 데몬/데스크톱 TUI는 이전과 동일. 게이트는 원격에만.

## 전제조건 (켜기 전)
1. **Tailscale**: PC·폰 같은 tailnet. `tailscale up`.
2. **서버 비번**: 루트 `.env`에 `OPENCODE_SERVER_PASSWORD=<강한 비번>` (없으면 serve 기동 거부).
3. **HTTPS(WebAuthn 필수)**: `tailscale serve`로 `:4096`을 TLS *.ts.net에 프록시 →
   `.env`에 `AUTOSTOCK_WEBAUTHN_ORIGIN=https://<pc>.<tailnet>.ts.net`. 미설정 시 서명 검증 fail-closed.
4. 데몬 가동(serve가 데몬 ensure를 거침 — TUI와 동일).

## 실사용 검증 체크리스트 (현 머지분 = API/보안 수준)
1. `OPENCODE_SERVER_PASSWORD` 없이 `autostock serve` → **기동 거부**(fail-closed) 확인.
2. tailscale 미가동 시 → **tailnet IP 못 찾음**으로 거부 확인(0.0.0.0 폴백 없음).
3. 정상 기동: 로그에 `autostock serve: http://<ts-ip>:4096 (tailnet 전용 바인드…)`.
4. `autostock qr` → 터미널에 QR + 서버 URL. (표시 후 화면 정리.)
5. 폰(tailnet)에서 `curl -u opencode:<비번> https://<pc>.ts.net/autostock/webauthn/assert-options -X POST`
   → 패스키 미등록이면 400(등록 먼저), 등록 후 challenge 반환.
6. **뮤테이팅 게이트 증명**(UI 전이라 수동): 원격에서 `permission.reply`를 서명 헤더 없이 호출 →
   거부, `x-autostock-webauthn` 유효 서명 첨부 → 통과. (F72 UI가 이 흐름을 자동화.)
7. **정상 모습**: 읽기(steer_read/account)는 서명 없이, 취소/청산/긴급정지/steer는 서명 요구.

## 튜닝 / 노브
- `AUTOSTOCK_WEBAUTHN_ORIGIN` — https origin(필수). 패스키 rpID는 이 hostname.
- 서버 포트 4096 고정(현재). tailnet ACL로 접근 기기 제한 권장.

## 롤백
- 즉시 무력화: `systemctl --user stop autostock-serve` (+ disable). 데몬/TUI 무관.
- 완전 제거: feat/F71 revert. 추가형 변경이라 다른 경로 영향 없음.

## 알려진 한계 / 범위 밖 (이 머지분)
- **UI 없음** — 대시보드/트레이스/QR스캔/confirm 시트/세션목록은 **F72**(실기기 검증과 함께).
- 자동detect(계정 로그인→세션 자동등장)=경로 B 후속. 푸시 알림=후속. 신규 수동 주문=범위 밖.
- WebAuthn은 https/secure-context 필수(위 전제 3). http로는 폰에서 패스키 API 미동작.

## 라이브 스모크 메모
- 현재 fake 단위테스트(51)로 로직·게이트 분기 증명. **서버 실기동 + 폰 접속 end-to-end는 UI(F72)
  완성 후** 위 체크리스트로 1회 수행 권장. 그 전까지는 §검증 1~6의 curl 수준으로 보안/기동을 확인.
