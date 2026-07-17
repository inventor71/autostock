# F97 Post-Merge Guide — Daily 성과 평가 (에이전트 vs S&P500)

## prod 브랜치에서 무엇이 바뀌나
매일 장마감 후, "이 에이전트가 그냥 S&P500(SPY)에 같은 돈을 넣어둔 것보다 잘하고 있나?"를
**누적수익 · SPY 누적수익 · 초과수익(alpha) · 오늘 델타** 헤드라인으로 4곳에서 볼 수 있다:
1. **모바일 대시보드**(F86) — Hero 카드 "총 자산" 아래 `vs S&P500 나 +X% · SPY +Y% · α +Z% · 오늘 …p`
2. **터미널 콘솔 TUI 사이드바** — 계좌 라인 아래 `vs SPY  me +X%  spy +Y%  α +Z%`
3. **`scripts/status.py`** — 요약 패널에 `vs S&P500 (since …) me … SPY … α …` 라인
4. **`python -m src.agent.logs.performance`** — 헤드라인 단독 출력(검증/수동 확인용)

데이터는 **이미 쌓이고 있던** `workspace/equity.jsonl`(EOD마다 equity + SPY 기록)에서 read-time에
파생한다. 새 영속 파일/새 EOD 작업 없음.

## 전제조건
- **데몬 재시작 필요**: `src/agent/steering/runtime.py`(스냅샷 발행)가 바뀌었으므로, 콘솔 TUI/모바일에
  perf가 나오려면 데몬이 새 코드로 스냅샷을 다시 발행해야 한다. (런처의 버전-스큐 자가치유(F43)가
  감지해 재시작하지만, 확실히 하려면 데몬 수동 재시작.)
- **새 env/config 없음.** 시크릿·외부 노출 추가 없음.
- **TS 콘솔 재빌드**: 모바일/사이드바 표시는 콘솔(opencode/app) 빌드에 포함. 기존 배포 절차대로
  `bun install && bun run typecheck`(+빌드) 후 배포.

## Real-usage 검증 체크리스트
장마감(EOD) 이후 또는 즉시:
1. **CLI (가장 빠름)**: prod 계좌 workspace에서
   `python -m src.agent.logs.performance` → `Agent +…% | SPY +…% | Alpha …%` 출력 확인.
   - equity.jsonl에 SPY 벤치마크 기록이 아직 없으면 "성과 데이터 부족" 메시지(정상, fail-honest).
2. **status.py**: `python scripts/status.py` → 요약 패널에 "vs S&P500" 라인 존재.
3. **스냅샷 발행 확인**: 데몬 재시작 후 `steering/snapshot.json`에 `perf_vs_benchmark` 키가 존재하고
   `agent_return_pct/spy_return_pct/alpha_pct`가 채워졌는지 확인
   (`jq '.perf_vs_benchmark' steering/snapshot.json`).
4. **콘솔 TUI**: `autostock`로 콘솔 실행 → 사이드바 계좌 아래 `vs SPY …` 라인.
5. **모바일**: PWA 대시보드에서 총자산 카드 아래 `vs S&P500 …` 라인.

### "정상"이란
- alpha = agent_return − spy_return. 값들이 손계산과 일치(예: agent 100040→100128 = +0.09%,
  SPY 750.35→754.94 = +0.61% → α −0.52%).
- 초기 며칠은 표본이 작아 값이 작거나(≈0) `since_date`가 첫 SPY 기록일로 잡힌다(equity.jsonl 첫 줄에
  SPY가 없으면 자동 제외됨 — 의도된 동작).
- 데이터/네트워크 문제 시 라인이 **숨겨지거나 "—"** 로 나오고, 대시보드/EOD는 정상 동작(막지 않음).

## 튜닝 노브
- **벤치마크 심볼**: 현재 SPY 고정(`compute_performance(..., benchmark_key="SPY")`). QQQ 등으로 바꾸려면
  이 인자만 변경(단, equity.jsonl `benchmark`에 해당 키가 기록돼 있어야 함 — 현재 SPY/QQQ/VIX 기록됨).
- **정규화**: 시작자본에 무관한 비율 기반(입출금 없음 전제). 도중 입출금이 생기면 값이 왜곡될 수 있음
  (아래 한계 참조).

## 롤백
- 순수 additive: 되돌리려면 커밋 revert. 신규 파일(performance.py) 삭제 + `perf_vs_benchmark` 라인/필드
  제거. 구버전 콘솔/앱은 새 키를 무시하므로 부분 롤백도 안전.

## 알려진 한계 / 범위 밖
- **외부 현금흐름(입출금) 미보정**: 계좌에 도중 입출금이 있으면 누적수익이 왜곡된다. 현재 전제는
  "고정 자본". 필요 시 입출금 보정(time-weighted) 후속 트랙.
- **리스크 지표 없음**: Sharpe/MDD/변동성 미표시(헤드라인만). 코어는 확장 가능하게 두었으나 UI 미노출.
- **롤링 윈도우 없음**: 7d/30d 미표시(누적 + 오늘 델타만).
- **일별 리포트 파일 없음**: 디스크 성과 리포트는 이번 범위 밖(요청 시 후속).
- **표본 초기**: 며칠 데이터로는 통계적 의미 제한적 — 표시 자체는 정상.
