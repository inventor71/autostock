# F79 Requirements — 모바일 PWA 실화면(SolidJS 뷰) 완성

> Track F79 · 단일 작성자 = F79 worktree 세션. F71(모바일 기반)·F75(WebAuthn 게이트 강화) 후속.

## Intent Analysis
- **User Request (원문)**: "응 실제 화면을 완성하는 후속트랙만들자" (직전 맥락: 모바일 PWA가
  로직만 있고 SolidJS 뷰 미배선 → 실제 화면 완성 요청).
- **Request Type**: New Feature (기존 미배선 로직을 사용자-대면 화면으로 완성).
- **Scope Estimate**: Single Component (`operator-console/cli/packages/app` 내부; 서버측 게이트는
  F75에서 완료되어 변경 최소).
- **Complexity Estimate**: Moderate — UI 다수 화면 + 보안 민감(WebAuthn 서명) 흐름 배선.
- **Depth**: Standard.

## 배경 (현 상태)
F71/U3는 **로직만** 출고하고 SolidJS 뷰 배선을 "실기기 검증분"으로 분리했다. 현재 자산
(`packages/app/src/addons/autostock/`):
- `dashboard.ts` — `toDashboard(snapshot)` / `dashboardSummary(model)` 순수 변환 + `DashboardModel`.
- `webauthn-client.ts` — `obtainAssertionHeader({fetcher, credentialsGet})` 페이키 어서션 의식;
  결과는 `x-autostock-webauthn` 헤더 값(base64(JSON)). **호출부 0.**
- `pairing.ts` — `parsePairingPayload(text)` → `ServerConnection.Http`.

서버측(`packages/opencode/src/server/autostock/webauthn.ts` 등) WebAuthn 게이트는 F75로 강화 완료.
**순효과(현재)**: PWA가 서명 헤더를 붙이는 코드가 없어 폰의 mutating 승인은 전부 거부(fail-safe).

## 확정 결정 (Requirements 단계 UAQ + F71 승계)
| 항목 | 결정 |
|---|---|
| UI 플랫폼 | PWA (opencode SolidJS 앱, `autostock serve`가 호스트) |
| 제어 범위 | 기존 뮤테이팅 도구만(취소/청산/긴급정지/steer 등). **신규 주문 작성 제외** |
| 홈 | 대시보드 우선 |
| 검증 범위 | **데스크톱 시뮬까지 포함** — 뷰/서명헤더 배선 + 단위·컴포넌트·PBT + typecheck + 데스크톱 브라우저 가짜 패스키로 mutating e2e 시뮬. 실 tailscale serve+실기기 토폴로지 스모크는 사용자가 폰에서 1회(post-merge-guide) |
| UI 완성도 | 모바일 우선 다듬기(mobile-first polished) — 기존 opencode 디자인 토큰 재사용 |
| 세션 뷰 | 기존 `session.tsx` 대화형 뷰 풀 재사용(폰 라이브 이어보기) |
| 확장 | Security Baseline(Full) + Property-Based Testing(Full) 둘 다 Enabled |

## Functional Requirements

### FR-1 — 연결/페어링 진입 (지원)
- 폰에서 처음 접속 시 QR 스캔 또는 수동 입력으로 서버 연결을 구성한다. `parsePairingPayload`를
  사용해 스캔 텍스트 → `ServerConnection.Http`로 변환하고 앱 server 컨텍스트에 저장한다.
- 연결 실패/잘못된 QR은 `parsePairingPayload`가 돌려주는 한국어 사유를 그대로 표시한다.
- (카메라 스캐너 UI는 가능하면 포함, 최소한 디코드된 텍스트 붙여넣기 경로는 제공.)

### FR-2 — 홈 대시보드 화면
- `steer_read` 상태 스냅샷을 가져와 `toDashboard()`로 뷰모델을 만들고 렌더링한다:
  equity, 당일손익%(부호·색), 포지션 수 + 심볼 목록, 건강 상태(●/✗/?), 승인대기 수, `asOf`.
- 스냅샷 없음/연결 끊김 → `offline` 상태("오프라인 — 서버에 연결되지 않음") 표시.
- 주기적 갱신(폴링 또는 기존 SDK 이벤트 스트림). 갱신 주기는 NFR에서 정의.
- 승인대기 N>0이면 대시보드에서 명확히 강조(다음 FR-3로 진입 동선).

### FR-3 — WebAuthn confirm 시트 (mutating 승인 배선) ★핵심
- 서버가 mutating permission ask를 보내면, 폰 UI에 **승인 시트**를 띄운다(요청 도구/요약 표시).
- 운영자가 "승인"을 탭하면 `obtainAssertionHeader({fetcher, credentialsGet})`를 호출 —
  `navigator.credentials.get`로 패스키 어서션을 받고, 결과를 **permission-reply 요청의
  `x-autostock-webauthn` 헤더**에 실어 보낸다(F75 게이트 통과 경로 활성화).
- "거절"은 서명 없이 reject(읽기/거절은 서명 불필요 — F75 토폴로지).
- 패스키 취소/오류(`WebAuthnError`) → 한국어 사유 표시, 승인은 미전송(fail-closed, 재시도 가능).
- 어서션 헤더가 없거나 서버가 거부하면 승인은 통과되지 않음을 UI가 분명히 보여준다.

### FR-4 — 세션 이어보기 뷰 (US-8)
- 폰에서 현재/최근 에이전트 세션을 기존 `session.tsx` 대화형 뷰로 그대로 이어본다.
- 모바일 레이아웃에 맞게 진입 동선(세션 목록 또는 현재 세션 바로가기)을 제공.
- **입력 경계 (Application Design 단계 UAQ 결정)**: 폰에서 에이전트에 프롬프트/스티어링 **입력
  허용 + WebAuthn 게이트**. 입력 전송(mutating)은 패스키 서명 필요(읽기/이어보기 스크롤은 무서명).
  → 결과: 서버 WebAuthn 게이트를 원격 `session.prompt`까지 **확장**(아래 Scope 갱신).

### FR-5 — 모바일 셸/내비게이션
- 홈(대시보드) ↔ 세션 ↔ (연결설정) 간 모바일 우선 내비게이션.
- 읽기 동작(대시보드/세션 조회)은 서명 없이, mutating만 FR-3 시트를 거치도록 일관 적용.

### FR-6 — 승인 큐 배지 + 자동 시트 (UAQ 추가)
- pending mutating 승인이 생기면 셸에 **실시간 배지**(개수)를 띄우고, FR-3 confirm 시트를
  **자동 팝업**한다(여러 건이면 큐로 순차 처리). 사용자가 폰을 보고 있지 않아도 다음에 열 때 즉시 인지.
- 배지/큐 카운트는 `toDashboard().pendingApprovals` 및 권한 이벤트 스트림과 일관.

### FR-7 — 상세 탭 패리티 (thesis + health) (UAQ 추가)
- **포지션 탭** → 해당 심볼의 position thesis 표시(F53 TUI 노출과 동등; `steer_read` thesis 조회).
- **건강 글리프 탭** → 9차원 health 오버레이(F69 TUI와 동등; `steering/health.json` 파생 스냅샷).
- 둘 다 읽기 전용 — 서명 불필요.

### FR-8 — Pull-to-refresh 수동 갱신 (UAQ 추가)
- 대시보드/세션 화면에서 아래로 당겨 즉시 스냅샷 재요청. 자동 갱신(NFR-2)과 병행.

## Non-Functional Requirements

### NFR-1 — 보안 (Security Baseline Enabled — 해당 규칙)
- **SECURITY-08 (앱 접근제어)**: mutating 승인은 반드시 WebAuthn 서명 경로를 거친다(클라이언트가
  서명을 못 붙이면 통과 불가 — 서버가 최종 강제, 클라이언트는 우회로를 만들지 않는다).
- **SECURITY-12 (인증/자격)**: 패스키 자격증명·서버 비밀번호를 코드/로그에 하드코딩·노출하지 않는다
  (QR 페어링 비밀번호는 server 컨텍스트에만, 로그·예외 메시지에 미출력).
- **SECURITY-15 (fail-safe)**: 서명 실패/취소/네트워크 오류 시 승인은 **fail-closed**(미전송),
  사용자에겐 일반화된 한국어 사유만. 외부 호출(fetch/credentials.get)은 모두 명시적 try/catch.
- **SECURITY-04/05 (헤더/입력검증)**: 서버 응답(assert-options, steer 스냅샷)은 방어적 파싱
  (`toDashboard`는 이미 never-throw). HTML-serving 보안헤더는 서버측 책임 → **N/A(이 트랙)**,
  단 신규 외부 스크립트/CDN 미도입 원칙(SRI 불필요하도록 self-host).
- N/A: SECURITY-01/02/06/07(데이터스토어·LB·IAM·네트워크 인프라 없음), SECURITY-10은 의존성
  추가 시 lockfile 고정으로 충족.

### NFR-2 — 성능/반응성
- 대시보드 갱신 주기: 기본 폴링 5–15초(또는 기존 이벤트 스트림 활용 시 push). 폰 배터리/네트워크
  고려해 과도한 폴링 금지. 화면 전환 체감 지연 최소화.

### NFR-3 — 호환성
- 대상: 폰 모바일 브라우저(WebAuthn/패스키 지원). HTTPS(tailscale serve) 전제 — WebAuthn은
  secure context 필수. 데스크톱 브라우저에서도 동일 코드로 동작(시뮬 검증용).

### NFR-4 — 테스트 (PBT Enabled — Full)
- **PBT-09 프레임워크**: TS는 **fast-check**(Vitest 통합) — 의존성에 추가.
- **PBT-02 라운드트립**: `b64urlToBuf`↔`bufToB64url` 라운드트립; 페어링 payload
  build(런처)↔`parsePairingPayload` 라운드트립.
- **PBT-03 불변식**: `toDashboard`는 임의 스냅샷에도 never-throw + `offline` 일관성 +
  `positionCount === symbols.length(유효심볼)`; `dashboardSummary`는 모델→문자열 전사상 안전.
- **PBT-10 보완**: 핵심 시나리오(서명 통과/취소/거부, 오프라인)는 예시 기반 컴포넌트 테스트로도 고정.
- 데스크톱 시뮬 e2e: 가짜 `credentialsGet`/`fetcher` 주입으로 FR-3 전체 의식(승인→서명→헤더 첨부)
  를 헤드리스로 검증.

### NFR-5 — 유지보수성
- 순수 로직(dashboard/pairing/webauthn-client)과 뷰(.tsx) 분리 유지 — 뷰는 주입형 의존성에 바인딩.
- 기존 opencode 앱 구조/디자인 토큰 관례를 따른다(새 디자인 시스템 도입 금지).

### NFR-6 — 비활성 자동잠금/재인증 (UAQ 추가 · Security)
- 일정 미조작 시간(기본 5분, 조정 가능) 경과 시 PWA를 **잠금** — 재접근 시 패스키 또는 서버
  비밀번호 재인증 요구. 폰을 열어둔 채 둔 상태의 오조작·무단 mutating 방지.
- **SECURITY-12 (세션 관리)**: 잠금은 클라이언트 세션 상태를 무효화하고, mutating 경로는 잠금
  해제 전까지 fail-closed. 잠금 타임아웃·자격은 코드/로그에 비노출.

### NFR-7 — 자동 재연결 + stale 표시 (UAQ 추가 · 견고성)
- 연결 끊김 감지 시 백오프 자동 재연결 시도, 복구 전까지 `offline`(FR-2) 표시.
- 마지막 스냅샷 `asOf` 기준 데이터가 오래되면(임계 초과) 화면에 **stale 명시**(예: "n초 전").
- **SECURITY-15 (fail-safe)**: 재연결/스냅샷 실패는 절대 오래된 값을 신선한 것처럼 보이지 않게 함.

## Scope / Out-of-Scope
**In**: FR-1~8 뷰 배선 + WebAuthn confirm 실배선 + 승인 큐 배지/자동시트 + 상세 탭 패리티
(thesis+health) + pull-to-refresh + 비활성 자동잠금/재인증 + 자동 재연결/stale + 세션 뷰 재사용 +
PBT/컴포넌트 테스트 + 데스크톱 시뮬 e2e + post-merge 실기기 스모크 가이드.
**Out**: 계정 자동detect(경로 B), 푸시 알림, 신규 수동 주문 작성, opentui 대시보드 전체 포팅,
네이티브 앱, **PWA 설치성/오프라인 셸(manifest+SW)**, **승인 감사 로그 전용 뷰** —
(UAQ에서 제외; 추후 트랙 가능).

**Scope 갱신 (Application Design)**: FR-4 "입력 허용+게이트" 결정의 결과로, 서버 WebAuthn
게이트를 **원격 `session.prompt`까지 확장**(S1)하는 최소 서버 변경이 **in-scope**가 됨
(요구사항 초안의 "서버측 WebAuthn 변경 out-of-scope"를 이 한 지점에 한해 의도적 확장 —
F75의 `verifyAssertionHeader`/`isRemoteOrigin` 재사용, 새 검증 로직 아님).

## 핵심 요구 요약
- 폰에서 **보이는 홈 대시보드**가 뜨고(FR-2), **mutating 승인이 패스키 서명으로 실제 통과**(FR-3,
  현재 막힌 핵심 해소)하며, **세션을 이어본다**(FR-4). 모바일 우선으로 다듬되 서버 보안 게이트는
  그대로 신뢰하고 클라이언트가 우회로를 만들지 않는다(fail-closed).
