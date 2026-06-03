# Track F42 — F37 리네임 누락 핫픽스 (alpaca_secret_key → alpaca_api_secret)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F42
- **Title**: F37 escape 핫픽스 — main.py + scripts에 남은 `settings.alpaca_secret_key` 잔여 참조 제거
- **Type**: feature (hotfix)
- **Status**: merged
- **Branch**: feat/F42 → main b0b1275 (fast-forward)
- **Worktree**: .claude/worktrees/F42 (머지 후 제거)
- **Base commit**: 72aba01
- **Start Date**: 2026-06-03

## Extension Configuration
- **Security Baseline**: Disabled (기계적 식별자 리네임, 새 표면 없음)
- **Property-Based Testing**: Disabled (로직 없음)

## Scope
F37(`ALPACA_SECRET_KEY`→`ALPACA_API_SECRET`)이 Settings 필드와 3개 모듈만 고치고
**컴포지션 루트 main.py와 운영 스크립트 2개를 누락** → 제거된 `settings.alpaca_secret_key`를
참조해 런타임 `AttributeError`. 데몬이 Alpaca 경로 startup에서 크래시(F38 docker `attach` 검증 중 발견).

수정 7곳 (모두 `alpaca_secret_key` → `alpaca_api_secret`):
- `main.py`:19,42,314 — create_data_provider / create_broker[alpaca] (데몬 startup 크래시)
- `scripts/verify.sh`:115,121 — smoke 라이브 키 체크
- `scripts/status.py`:180,184 — status 대시보드

검증: 잔여 참조 0, py_compile OK, `Settings().alpaca_api_secret` 존재 + 구 필드 제거 확인.

> ⚠️ 발견 경위: F38 docker-verify `attach`에서 데몬이 `AttributeError: 'Settings' object has no
> attribute 'alpaca_secret_key'`로 죽음. `.env.test`(환경변수 이름)는 별개로 이미 정합됨.
> ⚠️ ID 주의: 동시 세션이 F39/F40/F41을 선점해 핫픽스는 F42로 채번(최초 F39 시도는 진행 중 트랙과 충돌→롤백).

관련: F37(원 리네임), F38(발견 트랙), [[feedback-refactor-merge-resweep]].

## Stage Progress
- [x] Requirements/Design — minimal (기계적 식별자 리네임, 신규 로직 없음)
- [x] Code Generation — 7곳 리네임 (worktree feat/F42, commit b0b1275)
- [x] Build & Test — 잔여 0 / py_compile / Settings attr smoke 통과
- [x] Merge — feat/F42 → main b0b1275 (FF); feat/F38 리베이스로 전파
