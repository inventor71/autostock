# Track F82 — Intraday 피처 자동 수집 (유니버스 백필 + EOD append)

> Per-track state. **Single writer = this track's worktree session.**
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F82
- **Title**: Intraday 피처 자동 수집 — 유니버스 갭 백필 + 매 장마감 EOD append
- **Type**: feature
- **Status**: merged → main 2c9ddad (2026-06-14)
- **Branch**: feat/F82 (stacked on feat/F80)
- **Worktree**: .claude/worktrees/F82
- **Submodule branch**: — (monorepo)
- **Base commit**: dd3c784 (feat/F80 HEAD — Parquet store)
- **Start Date**: 2026-06-14T02:14:38Z

## Extension Configuration
- **Security Baseline**: Disabled (N/A) — gitignored 비민감 시장 데이터, 외부입력 경계 없음.
  (Alpaca 자격증명은 기존 설정 재사용, 신규 비밀 도입 없음.)
- **Property-Based Testing**: Disabled — 스케줄링·갭검출 오케스트레이션(부수효과 중심)이라
  example 기반으로 충분. (피처 계산/스토어 라운드트립 PBT는 F1/F80에서 보유.)

## Scope
F80 Parquet `IntradayFeatureStore` 위에 자동 수집을 얹는다. 의존: F80 (stacked).

1. **갭 인지 백필**: 데몬 기동 시 유니버스 각 종목의 스토어 커버리지를 읽어 누락/부족분만
   백필 (없으면 now-N년~now 전체, stale면 last_date+1~now). best-effort 백그라운드 스레드.
   깊이 기본 **3년**, provider **alpaca**.
2. **EOD append**: 장마감 잡(`_eod`)에서 그날 세션을 유니버스 전체에 수집/upsert.
   기존 surge scan과 동일 best-effort 패턴.
3. **설정 게이트**: `settings.yaml`의 `intraday_collection` 블록 + settings 모델. 기본 OFF.

재사용: `collector.collect()`(range=백필 / limit=today 양 경로), `resolve_universe`,
`TradingScheduler`(이미 `_eod` 장마감 잡 등록).

용량 실측(행=세션/일, 22컬럼, parquet snappy ~164 B/행): 3년×100종목 ≈ **~12MB**,
EOD 증가분 ≈ **~16KB/일(~4MB/년)**. 무시 가능.

관련: [[f80-storage-format-rationale]], F1(intraday 패턴분석 소비처).

## Merge Risk Notes
- **공유 파일 (주의)**: `src/trading/modes/agent.py`(_eod + start 배선), `config/settings.yaml`,
  `config/config.py`. agent.py는 다수 트랙 핫스팟.
- **API/시그니처 변경**: 없음(추가만). `collect()` 시그니처 불변.
- **알려진 동시 변경**: F80(스택 베이스, store.py). 머지 순서 F80→F82.

## Stage Progress
- [x] Workspace Detection — brownfield, F80 위 스택
- [x] Requirements Analysis — standard (scope/용량/깊이 UAQ 확정)
- [x] User Stories — skip (운영자 비가시 백엔드 자동화)
- [x] Workflow Planning — 승인됨 2026-06-14 (기본 ON 선택)
- [x] Application Design — skip (기존 컴포넌트 경계: collector/scheduler/agent)
- [x] Units Generation — skip (단일 단위)
- [x] Construction (Code Generation)
  - [x] auto-collect 오케스트레이터 + 갭검출 (`src/data/intraday/auto.py`)
  - [x] agent.py 배선 (startup backfill 스레드 + EOD append, best-effort)
  - [x] config 블록 (`intraday_collection`, 기본 ON)
  - [x] tests (`tests/intraday/test_auto_collect.py`, 13건)
- [x] Build & Test — 13/13 신규 GREEN, 전 intraday 107 GREEN. 실데이터 Alpaca 백필+EOD
      라이브 스모크 통과. 전체 4 fail은 F82 무관(선존 sentiment 3 + worktree env health 1).
