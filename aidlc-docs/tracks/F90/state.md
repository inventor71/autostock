# Track F90 — Docker prod 다중 인스턴스 (verify 하네스 패턴 확장)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F90
- **Title**: Docker prod화 — verify 하네스(F10/F15 attach) 패턴으로 다중 인스턴스 동시 운영 + 손쉬운 attach
- **Type**: feature (infrastructure)
- **Status**: merge-awaiting
- **Branch**: feat/F90
- **Worktree**: .claude/worktrees/F90
- **Submodule branch**: — (monorepo)
- **Base commit**: 23212f5 (main @ F86 close)
- **Start Date**: 2026-06-18

## Extension Configuration
- **Security Baseline**: **Enabled** — 적용: SR-1 이중체결 방지(계정 1:1), SR-2 host/컨테이너 동시가동
  금지, SR-3 `.env.<name>` 시크릿 git 제외, SR-4 verify 무영향. N/A: 외부 네트워크 노출면 없음(로컬 docker).
- **Property-Based Testing**: **Disabled** — 인프라/셸 스크립트 위주, PBT 적합 표면 적음(env-override
  파서만 일반 단위테스트).

## Scope
이미 있는 검증 하네스(`docker-compose.verify.yml`의 F15 `attach` 서비스 = 데몬+콘솔 풀 런타임,
TEST 계정, 격리 named volume)를 **prod 다중 인스턴스 런타임**으로 일반화한다. 목표: 인스턴스마다
**계정(env-file) + 워크스페이스/스티어링/로그(volume) + aggressiveness(F85)** 를 분리해 N개를
동시에 long-running으로 띄우고, 실행 중 컨테이너에 **쉽게 attach**해 콘솔 TUI로 관찰.
관련: [[f85-aggressiveness-knob]] [[worktree-live-verification]] (F10/F15/F16 account_farm).

## Stage Progress
- [x] Workspace Detection — brownfield. 기존 docker-verify 자산(Dockerfile.verify, compose, verify-run.sh) 존재 = RE 사실상 완료.
- [x] Requirements Analysis — UAQ 4건 + SR 4건 + **승인 완료** (depth: standard~comprehensive)
- [x] User Stories — skip (운영자 단일, 신규 페르소나 없음)
- [x] Workflow Planning — `inception/plans/workflow-planning.md`
- [x] Infra/Functional Design — `construction/infra-design/infra-design.md` (**승인 완료** — 코드가 설계대로 전부 구현됨)
- [x] Units Generation — skip (단일 응집)
- [x] Construction — feat/F90: `config/config.py`(env override), `docker-compose.prod.yml`, `scripts/prod-run.sh`(up/attach/ls/logs/down/migrate), `config/.env.example`, `.gitignore`, `tests/test_env_overrides.py`, `src/execution/brokers/account_farm_broker.py`(TradeAccount fallback) + `tests/test_account_farm_trade_account.py`. 설계 대비 개선: 계정 env를 `/run/account.env`(코드 마운트 밖)로, alpaca dedup digest 추가.
- [x] Build & Test — unit **7/7** pass, `bash -n`/`compose config`/`py_compile` OK. **실 account_farm 스모크**로 실버그 3건 발견·수정: (1) per-instance env 상대경로→compose가 named volume 오인→절대경로화, (2) verify 이미지 ENTRYPOINT(`verify.sh`)가 command 삼킴→`entrypoint` 오버라이드, (3) account_farm 부팅 크래시(alpaca-py 0.43.x TradeAccount 필수필드 누락)→`_fetch_trade_account` tolerant fallback. **재스모크: 데몬 steady-state 부팅(restarts=0, scheduler/agent turn 구동)**. 잔여: account_farm-only 인스턴스 intraday 수집은 ALPACA_* 마켓데이터 키 필요(비치명, 선재). `build-and-test/build-and-test-summary.md` + `post-merge-guide.md`.
