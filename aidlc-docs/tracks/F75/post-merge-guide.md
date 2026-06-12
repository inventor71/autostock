# F75 post-merge guide — WebAuthn 게이트 강화 (F71 후속)

## 무엇이 바뀌나
1. **게이트 판정 정제**: loopback 무조건 신뢰 제거. in-process(임베디드 TUI)와 *신원헤더 없는*
   loopback(로컬 attach TUI)만 신뢰. **`Tailscale-User-Login` 헤더가 붙은 loopback(= tailscale
   serve 프록시 경유 폰)과 모든 비-loopback 소켓은 mutating 승인 시 WebAuthn 필수.**
2. 챌린지 값-키 저장(동시 승인 안전, 만료 sweep).
3. basic-auth 상수시간 비교.
4. **등록 잠금**: 패스키 ≥1이면 신규 등록에 기존 패스키 서명(x-autostock-webauthn) 필요 —
   서버 비밀번호 단독으론 서명권한 발급 불가.

## ⚠️ 현재 상태 — PWA 클라이언트 미배선 (verifier 발견)
서버 게이트는 살아있지만 **PWA가 `x-autostock-webauthn` 헤더를 붙이는 코드가 아직 없다**
(`obtainAssertionHeader`는 정의·테스트만, 호출부 0 — F71이 UI를 후속으로 연기한 부분).
**순효과: 폰의 mutating 승인은 전부 거부(fail-safe)** — 읽기/reject는 정상, 위험한 건 안 열림.
아래 스모크 중 3·5번(서명 통과 경로)은 **클라이언트 배선 후속 트랙 전까지 실행 불가**;
2·3(거부 확인)·4번은 지금도 가능하며 여전히 필수.

## 추가 — 첫 패스키 등록(부트스트랩)
첫 등록은 tailscale 프록시 경유가 코드로 차단됨(403). **호스트에서 등록**하라(임베디드/로컬).
잔여 구멍: tailnet IP 직결 + 비밀번호만으로 첫 등록은 route()가 소켓을 못 봐 막지 못함 —
**서버 첫 기동 직후 빈 스토어 상태로 방치하지 말 것**(첫 키를 즉시 등록).

## 라이브 토폴로지 스모크 (필수 1회 — 이번 트랙의 존재 이유)
1. PC: `autostock serve` + `tailscale serve` 구성, `AUTOSTOCK_WEBAUTHN_ORIGIN=https://<pc>.ts.net`.
2. **헤더 확인**: 폰 브라우저로 PWA 접속 후 서버 로그/임시 echo로 요청에
   `tailscale-user-login` 헤더가 실제로 붙는지 확인. *안 붙으면* (구버전 tailscale 등) 폰이
   loopback+무헤더로 분류될 수 있음 → tailscale 업데이트 또는 보고.
3. **게이트 발화**: 폰에서 mutating 승인(예: place_order ask)을 패스키 없이 시도 →
   "WebAuthn 패스키 서명이 필요합니다" 거부 확인. 지문 서명 후 → 통과 확인.
4. **attach 보존**: PC에서 `opencode attach http://127.0.0.1:4096` TUI로 mutating 승인 →
   서명 없이 통과 확인(호스트-로컬 신뢰).
5. **등록 잠금**: 두 번째 패스키 등록 시도(서명 없이) → 403 확인.
   (adb+CDP 자동화는 aidlc-docs/research/mobile-ai-debugging.md 참조)

## 롤백 / 복구
- revert -m 1 1회. 패스키 분실 시: 호스트에서 `autostock-passkeys.json` 삭제 → 등록 잠금 해제
  (물리 접근 = 신뢰 경계 안).

## 알려진 한계
- 신원헤더 기반 판정은 tailscale serve가 헤더를 주입/덮어쓴다는 동작에 의존 — 스모크 2번이
  이를 검증한다. tailscale 외 다른 프록시를 끼우면 그 프록시는 직접 비-loopback으로 dial하거나
  헤더를 보존해야 함.
