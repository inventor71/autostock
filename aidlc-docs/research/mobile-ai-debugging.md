# 리서치 노트 — AI가 모바일(안드로이드) 앱을 "보며" 디버깅하는 방법

> 상태: 조사(reference). 작성 2026-06-12. F71(모바일 operator 기반, main fdfc041 머지)의
> **UI 후속 트랙**(SolidJS 뷰 마감)을 위한 디버깅 워크플로 레퍼런스.
> ※ "F72 후속"은 오기 — F72/73/74는 이미 다른 트랙이 사용. **UI 후속은 다음 가용 ID(F75~)**.

## 0. 핵심 구분: 미러링(사람) vs 프로그래밍 제어(AI)

| 층 | 도구 | 누가 |
|---|---|---|
| 화면 미러링(눈으로) | **scrcpy**, Android Studio "Running Devices"(내부 scrcpy) | 사람 |
| 프로그래밍 제어(캡처→판단→조작→로그) | **adb + CDP + Playwright** (또는 래퍼) | **AI** |

IDE에 폰이 떠 있는 것 = scrcpy/Android Studio 미러링(사람이 봄). AI는 직접 못 읽으므로 아래
프로그래밍 경로로 캡처/조작한다.

## 1. 기반 = adb (Android platform-tools)

- `adb exec-out screencap -p > s.png` — 스크린샷(AI가 Read로 관찰)
- `adb shell uiautomator dump` — UI 트리(클릭 가능 요소 + bounds + 텍스트/콘텐츠 설명)
- `adb shell input tap X Y` / `input text "..."` / `input swipe` — 터치/입력 주입
- `adb logcat` / `adb shell dumpsys` — 로그/시스템 상태
- 무선: `adb tcpip 5555` → `adb connect <폰ip>` (USB 없이; F71은 폰이 tailnet에 있으면 편함)

## 2. PWA(= F71 앱)엔 최강: CDP over adb

autostock 모바일 앱은 **폰 Chrome의 PWA**라, 데스크톱 브라우저처럼 CDP로 붙는 게 정석.

```bash
# 폰 USB 디버깅 + Chrome에서 PWA 연 상태
adb forward tcp:9222 localabstract:chrome_devtools_remote
```
```js
import { chromium } from "playwright"
const browser = await chromium.connectOverCDP("http://localhost:9222")
// 실폰 Chrome 탭의 DOM·console·network·스크린샷을 AI가 그대로 조작/관찰
```
→ 실제 폰에서 도는 PWA의 **DOM/콘솔 에러/네트워크/스크린샷**을 프로그래밍으로 다룸.
참고: [Chrome 원격 디버깅](https://developer.chrome.com/docs/devtools/remote-debugging) ·
[Playwright Android](https://playwright.dev/docs/api/class-android) ·
[CDP 원격제어 해설](https://dev.to/timtech4u/your-browser-has-a-remote-control-and-nobody-told-you-5e97)

## 3. AI 친화 래퍼 (설치형)

- **callstack/agent-device** — AI 에이전트용 iOS/Android 제어 CLI(adb 래핑, 세션 인지).
  https://github.com/callstack/agent-device
- **Android MCP 서버** — `get_screenshot()` / `get_uilayout()`(클릭요소+bounds) / `tap` 을
  **MCP 툴로** 노출 → Claude Code MCP로 등록하면 Claude가 직접 호출하며 디버깅.
  예: https://mcpservers.org/servers/IngaleChinmay04/android-mcp-server
- 사례: `screencap`+CDP로 25개 화면을 ~90초에 스윕해 레이아웃 깨짐/빈 화면/상태바 겹침 자동 검사
  (https://christophermeiklejohn.com/ai/zabriskie/development/android/ios/2026/03/22/teaching-claude-to-qa-a-mobile-app.html)

## 4. autostock 앱(F71 PWA) 권장 2단계 워크플로

**1단계 — 디바이스 없이 빠른 루프 (뷰 로직 90%):**
Playwright **데스크톱 + 모바일 뷰포트 에뮬**을 `bun run dev`(packages/app, serve 가리킴)에 붙임.
대시보드/트레이스/페어링-파싱/오프라인 배너 등 UI 로직을 디바이스 없이 AI가 반복 검증. 빠르고 저렴.
(F71에서 이미 분리해둔 `addons/autostock/*` 순수 로직이 뷰가 바인딩할 안정 표면.)

**2단계 — 실폰 필수분만 (adb+CDP):**
다음 셋은 **실폰에서만** 증명됨:
- **WebAuthn 패스키 ceremony**(지문) — 에뮬 불가. *https/secure-context 필요* →
  `tailscale serve`(TLS *.ts.net) + `AUTOSTOCK_WEBAUTHN_ORIGIN`(F71 post-merge-guide 참조).
- **카메라 QR 스캔**(`BarcodeDetector`)
- 실제 터치/스크롤 + Chrome 콘솔 에러(`adb logcat` 병행)

## 5. 설치 스택 (한 번 깔면)

1. `android platform-tools`(adb) — 폰 USB 디버깅 ON.
2. Playwright (`bun add -d playwright` / `npx playwright install chromium`).
3. (선택, 가장 편함) **Android-MCP 서버를 Claude Code MCP로 등록** → Claude가
   `get_screenshot`/`get_uilayout`/`tap` + CDP를 툴로 호출하며 디버깅.
4. (사람 병행용) scrcpy로 미러링 — AI 조작을 눈으로 동시 확인.

## 6. 한 줄 요약
scrcpy/Android Studio = 사람이 보는 미러링. **AI는 `adb`(스샷+UI트리+입력+logcat) +
PWA엔 `CDP→Playwright`**, 더 편하게는 **Android-MCP 서버**를 Claude Code에 물려 툴 호출.
autostock은 **1단계 Playwright 에뮬로 뷰 대부분**, **2단계 adb+CDP 실폰으로 WebAuthn·카메라**만.

## 참고
- Chrome 원격 디버깅: https://developer.chrome.com/docs/devtools/remote-debugging
- Playwright Android: https://playwright.dev/docs/api/class-android
- agent-device(CLI): https://github.com/callstack/agent-device
- Android MCP 서버: https://mcpservers.org/servers/IngaleChinmay04/android-mcp-server
- QA 사례(스샷+CDP 스윕): https://christophermeiklejohn.com/ai/zabriskie/development/android/ios/2026/03/22/teaching-claude-to-qa-a-mobile-app.html
- 관련: [[mobile-app-investigation]] (경로 A 조사), F71 post-merge-guide(전제·검증 체크리스트)
