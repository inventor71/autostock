# F5 Functional Design — Business Logic Model (유닛 `console-native-launcher`)

## 1. 최상위 기동 시퀀스 (`autostock` 실행 → 콘솔)
런처(E5)가 아래를 순서대로 수행. 어느 단계든 `blocking` 실패면 **fail-closed**: 명확한 한 줄 진단 +
해결법 출력, 비-0 종료. **silent exit 금지** (BR-1).

```text
autostock (~/.local/bin, S5)
  │ 1. resolve LauncherConfig (E5): AUTOSTOCK_ROOT, STEERING_DIR, tokens(메모리), mcp path, env export
  ▼
  2. PREFLIGHT (E2)  ── blocking 실패 ──▶ 진단+remediation 출력 → exit≠0 (no TUI)
  │   - token_match (E1): daemon_token == console_token ?  [값 미출력, BR-6]
  │   - steering_dir  : STEERING_DIR 존재/쓰기가능 ?
  │   - mcp_path      : mcp-server.ts 절대경로 존재 ? AUTOSTOCK_ROOT set ?
  │   - daemon_health : (3에서 보장) — 여기선 서비스 존재만 점검
  ▼
  3. DAEMON ensure (E3.ensure_running)
  │   ├ not-installed → ensure_installed (유닛 생성+enable+linger, 최초 1회)
  │   ├ inactive      → systemctl --user start → health-wait(E4)
  │   │                    └ health-wait 타임아웃/failed → 진단(BR-2) → exit≠0
  │   └ active        → health 확인만 (중복 start 금지, BR-3)
  ▼
  4. CONSOLE 실행 (bun, 포크) — AUTOSTOCK_LOCKDOWN=on, env 주입
  │   - 세션 뷰 직행 + autostock 사이드바 기본 표시 (S2/BR-7)
  ▼
  5. RUNTIME WATCH (E6, Q6=B) — MCP/채널 끊김 → 배너 경고 (BR-8)
  ▼
  콘솔 종료 → 런처 종료. 데몬은 계속 실행 (Q3=A, BR-4).
```

## 2. 데몬 ensure_running 상태기계 (E3)
```text
            ┌──────────────┐
   start →  │ not-installed│ ──ensure_installed──▶ inactive
            └──────────────┘
   inactive ──systemctl start──▶ activating ──health-wait──▶ active(attach)
                                      │ timeout/failed
                                      ▼
                                  진단 + abort (BR-1/BR-2)
   active ──(이미 실행)──▶ attach (no start, BR-3)
```
- **attach** = 별도 IPC 핸드셰이크 아님. 같은 `STEERING_DIR`/토큰으로 파일드롭 채널을 공유하는 것
  (계약 불변, NFR-4). 콘솔은 snapshot 읽기 + MCP로 command append.
- **health-wait**: `snapshot.json` mtime이 `health_window`초 내로 신선해질 때까지 폴(상한 타임아웃).
  타임아웃 = 서비스는 떴으나 발행 없음 → wedged 진단.

## 3. 프리플라이트 평가 (E1/E2)
- 각 체크는 순수 판정 → `PreflightCheck`. `blocking` 하나라도 `fail`이면 `report.ok=false` → `abort`.
- **token_match**: 런처가 root `.env`(데몬)와 콘솔 env의 `STEERING_OPERATOR_TOKEN`을 읽어 **상수시간 비교**,
  **boolean만** 산출(BR-6). 불일치 진단: "콘솔/데몬 토큰 불일치 → 채널이 모든 명령을 거부합니다. 두 .env의
  STEERING_OPERATOR_TOKEN을 동일하게 맞추세요." (값 미표시.)
- **mcp_path**: 상대경로 회귀(메모리 기록: "Module not found→MCP 미기동→모델이 주문 못함") 사전 차단 —
  `AUTOSTOCK_ROOT` 미설정 or `mcp-server.ts` 부재면 fail + remediation.

## 4. 리브랜딩 적용 (E7, S1/FR-2)
- `cli/logo.ts`: `logo`/`go` 글리프를 **2줄 스택 "auto"/"stock"** 블록폰트로 교체 (시머 렌더 `component/logo.tsx`
  그대로 동작). 폭이 좁아도 안전한 레이아웃(Q1=B).
- `visible_strings`: 푸터/스플래시/창 타이틀/팁/about의 "opencode" → "autostock" (대소문자/표기 일관).
- 비노출 식별자(패키지명/import)는 손대지 않음(회귀 위험 회피, §비범위).

## 5. 사이드바 우선 시작 (S2/FR-1)
- 홈 화면(`feature-plugins/home/` tips/footer)을 거치지 않고 세션 뷰로 직행하도록 기동 경로/기본 상태 조정.
- 사이드바(`autostock.tsx` `sidebar_content()`)를 **기본 표시**; `<leader>b` 토글은 보존(끄고 켤 수 있음).
- opencode 정상 입력 흐름(프롬프트/명령) 무파손 (BR-7).

## 6. 런타임 끊김 배너 (S6/FR-5/Q6=B)
- 콘솔이 주기적으로 `RuntimeHealthSignal`(E6) 갱신: snapshot/events 신선도 + MCP 응답.
- 끊김 감지 → 사이드바/상단 배너에 사람용 경고(원인+조치 힌트). **토큰 등 비밀 미포함**(BR-6).

## 7. 메인 재사용 / 변경 표면
- **재사용(불변)**: `steering/` 계약, Unit A 엔진, RiskManager→Broker, `src/filedrop.ts`, MCP `autostock_steer`, 락다운.
- **신규**: `autostock` 런처 + 설치 스크립트 + systemd user 유닛(템플릿/생성) + 프리플라이트(E1/E2) + 배너(E6).
- **포크 편집(재핀 필요)**: `logo.ts`, `component/logo.tsx`(필요 시), `feature-plugins/home/*`(우회), `sidebar` 기본표시, 보이는 문자열.
- **파이썬**: 코드 변경 목표 0 (systemd 유닛이 기존 `main.py --steering`을 그대로 기동; 헬스 = snapshot mtime).
