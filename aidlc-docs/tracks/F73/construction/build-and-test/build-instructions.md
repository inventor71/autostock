# Build Instructions — F73 viz-shell

## Prerequisites
- **Build Tool**: npm (Node.js ≥ 20; verified on v24.9.0), Next.js 15.5
- **Dependencies**: `viz-shell/package.json` (Next 15.5, React 19, tRPC 11, zod 4,
  @anthropic-ai/claude-agent-sdk 0.3, ai 6 + @ai-sdk/react 3, recharts 3,
  react-markdown 10; dev: vitest 4, fast-check 4, Tailwind v4, TS 5.9)
- **Environment Variables**: 빌드 자체엔 불필요. 런타임만:
  - `AUTOSTOCK_ROOT` (선택) — 데몬 산출물 루트. 미설정 시 `viz-shell/`의 부모.
  - 채팅 기능은 로컬 `claude` CLI 구독 인증 재사용 (별도 키 불필요).
- **System Requirements**: 로컬 dev/단일 사용자. 외부 노출 금지(127.0.0.1 고정).

## Build Steps

### 1. Install Dependencies
```bash
cd viz-shell
npm install
```

### 2. Type Check
```bash
npm run typecheck    # tsc --noEmit
```

### 3. Production Build (선택 — 보통 dev 모드로 운영)
```bash
npm run build        # next build (webpack)
```
> ⚠️ 운영은 `npm run dev`(HMR=반응성 계층)가 기본. `build`는 정합성 확인용.

### 4. Verify Build Success
- **Expected Output**: `✓ Compiled successfully`, 라우트 표에
  `/`(Static), `/api/chat`·`/api/chat/reset`·`/api/trpc/[trpc]`(Dynamic ƒ).
- **Build Artifacts**: `.next/` (gitignore). 배포 산출물 아님 — 로컬 dev 도구.
- **Common Warnings**: 없음(클린). require.context는 webpack 전용 — Turbopack
  플래그(`--turbopack`) 사용 금지(생성 뷰 자동 발견 깨짐).

## 실행
```bash
npm run dev                                    # http://127.0.0.1:3210
# 라이브 데이터를 메인 체크아웃에서:
AUTOSTOCK_ROOT=/abs/path/to/autostock npm run dev
```
