# F86 — Business Logic Model (unit: dashboard-endpoint)

## 흐름 1 — 서버 read (`GET /autostock/dashboard`)
```
route(request):
  if !path.endsWith("/autostock/dashboard"): return null          # 체인 통과
  try:
    dir = resolveSteeringDir(env, cwd)                            # BR-1
    raw = {
      snapshot: dir ? readJson(dir,"snapshot.json") : undefined,  # BR-2
      health:   dir ? readJson(dir,"health.json") : undefined,
      monitor:  dir ? readJson(dir,"monitor.json") : undefined,
      pending:  dir ? readJson(dir,"pending_approvals.json") : undefined,
      snapshotMtimeIso: dir ? statMtimeIso(dir,"snapshot.json") : null,
    }
    payload = assembleDashboardPayload(raw)                       # BR-3..BR-8 (never-throw)
    return Response.json(payload, 200)
  catch e:
    return Response.json(EMPTY_PAYLOAD, 200)                      # BR-9 fail-safe
```

`assembleDashboardPayload(raw)` (순수):
- `account`: snapshot.account에서 equity/cash/open_pnl/position_count(유한수만), day_pnl_pct=null, buying_power=null (BR-4)
- `positions`: snapshot.positions(dict)→array, 각 행 return_pct=price 기반(BR-5)
- `health`: health 객체 또는 null
- `pending_approvals`: BR-8
- `market`: BR-7
- `agent`: { current: monitor.current_turn 요약, recent: monitor.decisions→{ts,action,symbol,summary} }
- `published_at`: BR-6

## 흐름 2 — 클라 폴 (mobile-shell C4)
```
onMount:
  poll()                                  # 즉시 1회
  timer = setInterval(POLL_MS, () =>      # BR-11
    (document.hidden || locked()) ? noop : poll())
  onCleanup(() => clearInterval(timer))

poll():
  payload = await fetchDashboard(http)    # BR-15; 실패→null
  if payload == null:
    setModel(toDashboard(null,{offline:true})); setRows([]); return   # BR-13
  setModel(toDashboard(toSnapshotSources(payload)))   # F79 코어 재사용
  setRows(toPositionRows(payload.positions))          # weightPct 계산
  setExtra({ cash, buyingPower, market, agent })
  setStale(isStale(model(), Date.now(), STALE_THRESHOLD_MS))          # BR-14

render:
  <DashboardView model=model() positions=rows() cash=… buyingPower=…
                 market=… agent=… stale=stale() onRefresh=poll />
```
- `toSnapshotSources(payload)` = `{ account, positions, health, pendingApprovals: payload.pending_approvals, publishedAt: payload.published_at }` (F79 `SnapshotSources` 정합).
- `toPositionRows` = payload.positions → `{symbol, marketValue, dayPct: return_pct, weightPct}`; weightPct = market_value / Σ|market_value|.

## Testable Properties (PBT-01 — 필수)

| # | 컴포넌트 | 카테고리 | 속성 |
|---|---|---|---|
| P1 | `assembleDashboardPayload` (C3) | Invariant (never-throw) | 임의 입력(부분/null/타입오염/깨진 중첩)에 대해 예외 없이 스키마-유효 payload 반환. account.position_count≥0, positions는 배열, pending_approvals는 ≥0 정수 |
| P2 | `assembleDashboardPayload` positions | Invariant (보존) | 유효 snapshot.positions dict 입력 시 출력 positions 길이 == dict 키 수, 각 symbol 보존 |
| P3 | return_pct (BR-5) | Invariant (부호) | side=long & current>avg ⇒ return_pct>0; side=short & current<avg ⇒ return_pct>0; avg=0/비유한 ⇒ null (예외 없음) |
| P4 | `isStale` (F79, 재검증) | Invariant (fail-safe) | offline∨asOf=null∨파싱불가∨(now-asOf>threshold) ⇒ true. 신선 입력만 false |
| P5 | `resolveSteeringDir` (C2) | Invariant | 어떤 env/cwd 조합에도 string|null 반환(예외 없음); 우선순위 STEERING_DIR>AUTOSTOCK_ROOT>cwd |
| P6 | `toSnapshotSources`∘`toDashboard` round-trip | Invariant | 임의 payload → DashboardModel 변환이 never-throw, equity/dayPnlPct는 number|null만 |

- **생성기(PBT-07)**: 도메인 생성기 — `genSnapshot`(부분/완전 account+positions), `genMonitor`, `genHealth`, `genBrokenJson`(타입오염). 원시 타입 단독 금지.
- **Example 보완(PBT-10)**: ① 완전 스냅샷 → 풀 payload ② 빈 디렉터리/파일 부재 → 빈 payload(published_at=null) ③ 깨진 JSON → fail-safe ④ short 포지션 return_pct 부호. PBT가 찾은 최소 반례는 example 회귀로 고정.
- **재현성(PBT-08)**: fast-check 기본 shrinking/seed. 실패 시 seed+축소입력 로그.
