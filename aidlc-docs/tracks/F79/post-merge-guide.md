# F79 Post-Merge Guide — 모바일 PWA 실화면 (백본 + 라이브 배선)

> ⚠️ **정직한 범위 고지(먼저 읽기)**: 이 머지분은 **보안/데이터 백본 + 라이브 FR-3 배선 +
> 뷰 컴포넌트**까지다. **뷰가 아직 앱 내비/라우터에 마운트되지 않았다**(C8 세션 입력 서명 +
> C10 셸/라우팅 통합은 후속). 즉 **폰에서 새 대시보드/시트 화면은 아직 안 보인다.** 단,
> **서버 게이트(S1)는 라이브로 동작이 바뀐다**(아래). 컴포넌트·게이트·코어는 전부
> 테스트/typecheck 그린.

## 무엇이 바뀌나 (prod 브랜치)

### 1. ★ 동작 변화 — S1 서버 게이트 (라이브)
- **원격 `session.prompt`(및 promptAsync)가 WebAuthn 서명을 요구**한다. 원격 = 비-loopback
  소켓 또는 tailscale-serve 프록시 홉(폰). **호스트-로컬/in-process는 영향 없음**:
  - 데몬이 스폰한 에이전트의 in-process 프롬프트 → 게이트 안 됨(정상).
  - 데스크톱 attach TUI(loopback, 무 tailscale 헤더) → 게이트 안 됨(정상).
  - 폰(tailscale 경유) → 서명 없으면 거부(fail-safe). **폰 PWA가 아직 프롬프트 서명을 안 붙이므로
    현재 폰发 원격 프롬프트는 거부된다** — F75의 "클라 미배선 → mutating 거부"와 같은 안전 패턴.
- 순효과: 외부에서 서명 없이 에이전트를 스티어하던 구멍을 선제적으로 닫음. 기존 데몬/TUI 흐름 무변화.

### 2. 신규 코드 (아직 화면엔 안 보임)
- `app/.../addons/autostock/`: `snapshot.ts`(C2) · `signed-mutation.ts`(C3) · `webauthn-fetch.ts` ·
  `approval-queue.ts`(C4) · `lock.ts`(C9) · `confirm-sheet.tsx`(C5) · `dashboard-view.tsx`(C6) ·
  `detail-views.tsx`(C7).
- `context/permission.tsx`: **`respondSigned()`** — 승인 시 패스키 서명을 `x-autostock-webauthn`
  헤더로 붙여 응답(FR-3 라이브 배선). **단 이 메서드를 호출하는 UI(ConfirmSheet 마운트)는 후속.**
- 신규 devDependency: `fast-check`(PBT).

## 전제 조건
- 콘솔/앱 재빌드 + `autostock serve`(및 데몬) 재시작 — 서버 코드(S1) 반영.
- 신규 env/config 키 없음. WebAuthn 전제(HTTPS origin/패스키)는 F71/F75 그대로.

## 실사용 검증 체크리스트
1. **서버 테스트(필수, 머지 후 1회)**:
   `cd operator-console/cli/packages/opencode && bun test test/autostock-webauthn.test.ts` → 40 pass.
   addon 코어: `cd ../app && bun test --preload ./happydom.ts src/addons/autostock` → 41 pass.
2. **호스트 프롬프트 보존(중요)**: 데스크톱 TUI(attach/임베디드)에서 에이전트에 평소처럼 프롬프트/
   스티어 → **정상 동작**(게이트 안 됨). 데몬 자동 턴도 정상.
3. **원격 게이트 발화(폰/원격)**: tailscale 경유로 `POST /session/<id>/prompt`를 `x-autostock-webauthn`
   없이 호출 → **400 거부**(서버 로그에 `autostock: remote prompt gated`). 정상.
4. typecheck: `bun run --cwd packages/app typecheck` + `--cwd packages/opencode typecheck` 클린.

### "정상"의 모습
- 호스트/데몬: 무변화. 원격 무서명 프롬프트: 거부. 폰에 새 화면: 아직 없음(후속 통합 전).

## 튜닝 / 노브
- mutating 분류·원격 판정은 `opencode/.../autostock/webauthn.ts`(`isRemoteOrigin`/`checkPrompt`).
- 잠금 타임아웃 기본 5분: `app/.../addons/autostock/lock.ts` `DEFAULT_LOCK_TIMEOUT_MS`(셸 배선 시 사용).

## 롤백
- `git revert -m 1 <merge>` 1회. S1 외엔 추가형(미마운트 컴포넌트)이라 다른 경로 영향 없음.
- S1만 빼고 싶으면 session.ts의 `gateRemotePrompt()` 호출 2곳 제거(컴포넌트는 그대로 둬도 무해).

## 알려진 한계 / 범위 밖 (이 머지분)
- **셸/라우터 통합 미완(C10)**: DashboardView/ConfirmSheet/DetailViews가 앱 내비에 안 떠 있음 →
  폰에서 아직 사용 불가. **후속 트랙(실기기 실행하며 통합·다듬기) 필요.**
- **세션 입력 클라 서명 미배선(C8)**: 서버 게이트는 닫혔으나, 폰에서 프롬프트를 *보내* 통과시키려면
  세션 composer에 `withWebAuthn(session.prompt headers)` 배선 필요(후속).
- **데스크톱 가짜-패스키 e2e 시뮬 / 실기기 토폴로지 스모크 미실행**(셸 통합 후 의미 있음).
- 범위 밖(요구사항): PWA 설치성/오프라인 셸, 푸시 알림, 신규 수동 주문, 계정 자동detect.
