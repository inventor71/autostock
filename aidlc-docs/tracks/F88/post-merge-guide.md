# F88 Post-Merge Guide — Agent self-authored long-horizon triggers

## prod 브랜치에서 무엇이 바뀌나
- 새 패키지 `src/agent/triggers/` (store/models/ast_screen/sandbox/fetch/evaluator/settings/schema).
- agent 툴에 `python -m src.agent.tools trigger {register,list,inspect,cancel}` 추가.
- daemon이 (steering on + `triggers.enabled: true`일 때만) `trigger_eval` 스케줄러 잡을 돈다.
- **기본 OFF**: `triggers.enabled`가 false면 daemon 동작은 머지 전과 100% 동일(코드 경로 inert).
- `WakeKind`에 `agent_trigger` 추가, `run_wake`/`wake_prompt`에 macro 분기(기존 wake 동작 보존).

## 활성화 전제조건
1. **Docker**: prod daemon(systemd `--user` 유닛)에서 `docker run`이 가능해야 함.
   - 확인: 데몬 실행 사용자로 `docker version` 성공해야. 안 되면 유닛에 docker 그룹 접근 부여
     (`SupplementaryGroups=docker`) 또는 rootless docker. **불가 시 daemon 부팅 로그에 loud error +
     triggers 비활성**(daemon 자체는 정상). 조용히 죽지 않음(critic#5).
   - 베이스 이미지 사전 pull 권장: `docker pull python@sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9`
2. **settings.yaml `triggers:` 블록** (예시):
   ```yaml
   triggers:
     enabled: true
     tick_seconds: 300            # 평가 루프 주기(due 트리거만 샌드박스 실행)
     max_consecutive_errors: 5    # 연속 에러 시 자동 비활성화
     min_fire_gap_s: 21600        # 동일 트리거 재발화 최소 간격(6h)
     sandbox_timeout_s: 8
     sandbox_memory: "256m"
     webfetch_allowlist:          # daemon이 GET 허용할 도메인(SSRF 가드). 비우면 webfetch 불가.
       - stlouisfed.org
       - sec.gov
   ```
3. daemon 재시작 필요(설정/코드 반영).

## 실사용 검증 체크리스트 (라이브 스모크)
1. **부팅 로그**: `F88 triggers: docker server <ver>` + `F88 triggers wired (tick=...)` 보이는지.
   (Docker 불가 시 `... docker unavailable ...` error — 그러면 위 전제조건 1 수정.)
2. **계약 시드 확인**: `workspace/triggers/ctx-schema.md` 생성됐는지(agent가 읽는 predicate 계약).
3. **수동 등록**(데몬 venv로):
   ```
   echo 'def should_fire(ctx):
       v = ctx.get("macro", {}).get("vix")
       return {"fire": v is not None and v > 100, "why": f"vix={v}"}' > /tmp/pred.py
   AGENT_JOURNAL_ROOT=<workspace> python -m src.agent.tools trigger register \
     --id smoke-vix --thesis "smoke" --cadence hourly --ttl-days 1 \
     --sources-json '[{"kind":"signal","name":"macro"}]' --predicate-file /tmp/pred.py
   ```
   → `{"ok": true, "id": "smoke-vix"}`. `workspace/triggers/smoke-vix/{spec.json,predicate.py,state.json}` 확인.
4. **평가 발생 확인**: `tick_seconds` 후 `workspace/triggers/smoke-vix/state.json`의 `last_run`이
   채워지는지(평가됨). vix>100은 거의 안 fire하니 `fired_count`는 0이 정상.
5. **fire→wake 확인**(원하면): 임계를 현재값 아래로 낮춘 트리거를 등록하면 다음 tick에 wake turn이
   떠야 함 — agent-trace(`/agent-trace`)나 데몬 로그에서 `trigger wake fire: id=...` + macro wake turn.
   매매 결정은 기존 supervisor gate를 그대로 통과(트리거 자체는 매매 0).
6. **정리**: `... trigger cancel smoke-vix`.

## "정상"의 모습
- 평소 tick 로그는 조용함(due 트리거 없거나 fire 안 함). fire 시에만 wake turn 1회.
- 깨진 predicate는 `state.json`의 `consecutive_errors` 증가 → 임계 도달 시 `disabled: true` +
  `disabled_reason`. `trigger inspect <id>`로 확인.

## 튜닝 노브
- `tick_seconds`(반응성 vs 부하), `min_fire_gap_s`(wake 빈도), `max_consecutive_errors`(관용도),
  `sandbox_timeout_s`/`sandbox_memory`(predicate 자원), `webfetch_allowlist`(데이터 도달 범위).

## 롤백
`triggers.enabled: false` + 데몬 재시작 → 즉시 inert(코드 잔존하나 비활성). 완전 롤백은 머지 revert.

## 알려진 한계 / 범위 밖
- **websearch 소스 미지원**(후속): signal(macro/movers/earnings/holdings) + webfetch(allowlist)만.
  `sentiment` signal도 후속(현재 `_error` 반환, fail-honest).
- 평가는 단일 daemon 프로세스의 스케줄러 풀 워커에서 동기 `docker run` — hourly+ cadence엔 충분하나
  매우 많은 트리거가 한 tick에 due면 직렬 실행.
- predicate 격리의 신뢰 경계는 Docker. AST 스크린은 보조(defense-in-depth)일 뿐.
- 무관 기존 실패: `tests/signals/test_sentiment_sweep.py` 3건은 wallclock-drift(ET_NOON 하드코딩)로
  F88과 무관 — 별도 fix 권장.
