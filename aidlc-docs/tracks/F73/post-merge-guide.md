# Post-Merge Guide — F73 viz-shell

> 장기 브랜치라 머지는 사용자 "안정 선언" 시점. 이 가이드는 그때(또는 vibeshell을
> 직접 돌려볼 때) 적용된다.

## prod 브랜치에서 달라지는 것
- 신규 디렉토리 `viz-shell/`(Next.js 앱) 추가. **기존 Python 데몬/operator-console
  코드 무변경** — 순수 additive, 데몬은 산출물 파일을 평소대로 쓸 뿐.
- 새 런타임 표면: 로컬 웹 대시보드(`http://127.0.0.1:3210`) + 채팅 뷰 생성기.

## 전제조건
- Node ≥ 20, `cd viz-shell && npm install` (최초 1회).
- 트레이딩 데몬이 가동되어 산출물을 쓰고 있을 것:
  `steering/snapshot.json`, `workspace/equity.jsonl`, `workspace/positions/*.md`.
- 채팅 기능: 로컬 `claude` CLI 구독 로그인 상태(별도 키 불필요).
- **데몬 재시작 불필요** — viz-shell은 데몬과 IPC 없음.

## 새 config / env
- `AUTOSTOCK_ROOT`(선택): 데몬 산출물 루트. 미설정 시 `viz-shell/`의 부모.
  worktree/별도 체크아웃에서 메인 데이터를 보려면 절대경로로 지정.
- 신규 비밀키 없음.

## 실사용 검증 체크리스트 (실데이터 스모크)
1. `AUTOSTOCK_ROOT=/abs/autostock npm run dev` → 콘솔 `Ready` + `http://127.0.0.1:3210`.
2. 브라우저로 접속 → **Overview 탭**에 Equity/Cash/Invested/Open P&L 카드가 실수치,
   equity 곡선(7/30/90d 토글), 포지션 테이블. **정상 모습** = 데몬 최신 snapshot과
   숫자 일치. 데몬 꺼져 있으면 위젯별 "snapshot 없음 — 데몬 미가동?" placeholder(전체
   빈 화면이면 버그).
3. 포지션 행 클릭 → 우측 thesis drawer에 마크다운 본문. (오래된 읽기면 ⚠️ stale 배지)
4. 채팅 패널에 "심볼별 미실현 손익 막대차트 만들어줘" → 수 초 내 새 탭 자동 추가·활성.
   ✎ 회색 도구 라인이 흐르고, 끝나면 차트 렌더. **어디서 보나**: 탭바 + 우측 채팅.
5. 탭 ×로 닫기 → 사라지고 상단 "숨긴 뷰 (n)▾"에서 복원(파일은 유지됨 확인).
6. (보안) 채팅에 "workspace의 equity.jsonl을 직접 읽어줘" → 거부(⚠️ 또는 에이전트가
   tRPC 경유 제안). workspace 본문이 채팅에 나오면 안 됨.
7. 턴 진행 중 입력칸 비활성 + "■ 중지" 버튼 노출 → 누르면 중단·입력 복구.

## 튜닝 노브
- 폴링 주기: `src/components/providers.tsx`의 `refetchInterval`(기본 5000ms).
- 포트/바인딩: `package.json` dev 스크립트 — **127.0.0.1 유지**(외부 노출 금지).
- equity tail 상한: `src/server/safe-read.ts` `TAIL_MAX_BYTES`(기본 8MB).

## 롤백
- viz-shell은 격리 디렉토리 → 디렉토리 제거/브랜치 미머지로 즉시 무력화. 데몬·콘솔
  영향 0. 머지 후 되돌리려면 `viz-shell/` 추가 커밋만 revert.

## 알려진 한계 / 범위 외
- **외부 노출 금지** — 채팅 엔드포인트 무인증, 127.0.0.1 바인딩이 유일 방어.
- Turbopack 비호환(require.context) → `--turbopack` 사용 금지(webpack dev 고정).
- 생성 뷰 품질은 에이전트 출력 의존 — 깨지면 해당 탭만 ErrorBoundary, 수복은 채팅 지시.
- 쓰기/스티어링은 전부 기존 operator-console 몫 — viz-shell은 순수 읽기 전용.
