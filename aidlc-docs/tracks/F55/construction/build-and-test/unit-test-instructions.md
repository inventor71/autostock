# Unit Test Instructions — F55

## 사전 준비 (worktree 1회)
```bash
cd /home/jihoonpark/Project/autostock/.claude/worktrees/F55/operator-console/cli
bun install            # 워크스페이스 의존성 (solid-js 등) 설치
```

## 실행
```bash
cd packages/tui-trading
bun test                              # 전체 (77 pass 기대)
bun test test/timeline-layout.test.ts # F55 핵심 파일 (51 pass)
```

## 기대 결과
- `77 pass / 0 fail`.
- F55 `describe("F55 overnight (데이마켓) session")`의 E1~E6 모두 통과.
- 특히 **E4**: `now=02:00 ET`의 라이브 오프마켓 윈도우에서 `regions`의 `kind:"day"` 밴드가
  폭>0으로 정확히 1개 — critic이 찾은 "야간 라이브 밴드 미표시" 회귀 가드.

## 대안: 컨테이너 격리 검증 (F10 harness, 선택)
```bash
# 프로젝트 표준 격리 검증(TEST 계정, 운영 무영향)
.claude/worktrees/F55/... worktree-setup.sh --docker-verify
docker compose ... run --rm verify typecheck   # 패키지 tsconfig 한계로 fs/path 잔여(F55 무관)
docker compose ... run --rm verify unit
```
