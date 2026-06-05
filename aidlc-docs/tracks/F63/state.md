# Track F63 — Health Check Loop (AI-driven 시스템 모니터링)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F63
- **Title**: Health Check Loop — AI-driven 시스템 모니터링
- **Type**: feature
- **Status**: merged → main 58e1dda (2026-06-06)  <!-- /ai-dlc-merge: rebased onto 4f2b1b2(F30/F62/F65/F64/F66/F67 머지 반영, 충돌 없음 — health 모듈 신규 파일 위주), verify green (977 passed + 9 health 모듈 import 클린), --no-ff merged -->
- **Branch**: feat/F63
- **Worktree**: .claude/worktrees/F63
- **Submodule branch**: —
- **Base commit**: b89735d
- **Start Date**: 2026-06-06

## Extension Configuration
- **Security Baseline**: Disabled — N/A (운영 도구, 새 보안 민감 기능 없음)
- **Property-Based Testing**: Disabled — N/A (단순 데이터 수집, 결정적 출력)

## Scope
autostock 시스템의 건강 상태를 9개 차원(프로세스, 브로커, 데이터, LLM, 계좌, 리스크, 로그, 설정, 리소스)에서 주기적으로 점검하는 health check 모듈과 Claude-driven 실행 루프 구축.

- `src/monitoring/health/` 모듈 신규 생성 (report.py, checker.py, dimensions/*.py)
- `scripts/health.py` 독립형 진입점
- Claude CronCreate로 1시간마다 실행
- 기존 AlertManager 재사용 (CRITICAL 시 Slack/Telegram)
- 읽기 전용, 비차단, graceful degradation

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성.

- **공유 파일 (주의)**: `src/monitoring/` 디렉토리에 새 모듈 추가 (기존 alerts.py, logger.py와 충돌 없음 — 신규 파일만)
- **API/시그니처 변경**: 없음 (신규 모듈만 추가, 기존 코드 변경 없음)
- **알려진 동시 변경**: 없음 (F62/F64/F65는 agent 전용, F30은 KIS 브로커)
- **path 의존성**: `_root` 계산이 `Path(__file__).parent.parent.parent.parent.parent` — 모듈 트리 깊이에 의존. 디렉토리 구조 변경 시 확인 필요.
- **config 의존성**: `settings.signals`가 dict 타입임을 가정 (Pydantic 모델 아님). Settings 모델 변경 시 주의.

## Stage Progress
- [x] Workspace Detection
- [x] Requirements Analysis — standard (plan.md 기반)
- [x] User Stories — skip (순수 운영 도구, 사용자 페르소나 불필요)
- [x] Workflow Planning
- [x] Application Design — skip (아키텍처 단순, 1개 모듈)
- [x] Units Generation — skip (단일 유닛)
- [x] Construction (Code Generation)
  - [x] Unit 1 — Health Check Module + Script (14 files, 980d37d)
- [x] Build & Test
