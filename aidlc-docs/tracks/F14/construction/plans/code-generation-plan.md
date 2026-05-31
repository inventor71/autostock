# F14 Code Generation Plan (Part 1)

> Part 2 진입(실제 코딩)의 **첫 동작 = worktree 생성**. 그 전까지 코드 변경 0.
> 단일 worktree(parent `feat/F14` + 서브모듈 `feat/F14`)에서 U1→U2 순차.

## Step 0 — worktree 게이트 (Part 2 첫 동작, 아직 안 함)
- [ ] `scripts/worktree-setup.sh F14 --py` (parent worktree + 서브모듈 feat/F14 브랜치 + main .env 링크)
- [ ] 서브모듈 변경(U2) 위해 `git -C operator-console/cli switch -c feat/F14` 확인(detached HEAD 금지)

## U1 — Python 데몬 복원력 (검증 pytest)
- [ ] **A1** `src/execution/brokers/alpaca_broker.py`: `_install_session_timeout()` 헬퍼(멱등 가드:
      이미 래핑된 세션이면 skip). ctor의 `self._client`에 적용 **+ `get_latest_prices`의
      `if self._data_client is None:` 블록 내부 생성 직후(:363-365)에도 적용** (critic HIGH — ctor 훅은
      lazy 클라이언트에 안 닿음; 호출자 runtime.py:319 단일이라 레이스 없음). graceful no-op(속성 부재 시 경고).
- [ ] **A2** `src/data/providers/alpaca_provider.py`: ctor의 `self._client`에 동일 헬퍼 적용.
- [ ] **A3** 타임아웃 값을 ctor 인자로 노출(하드코딩 회피).
- [ ] **B1** `src/agent/intraday/bars.py`: `peek_price`/`peek_bars`(캐시 전용, miss→None) 추가.
- [ ] **B2** `src/agent/intraday/wake.py`: `_abnormal_events`/`_watch_events`/`_watch_met`가 `peek_*` 사용.
      **`_abnormal_events`: detect-first 2단계**(critic R3) — `sig=detect_abnormal(...)` 먼저 호출(price만
      None이어도 volume 신호 가능); 신호 있으면 기존 latch/fire; 신호 없을 때 `price is not None and
      bars is not None and len(bars)>0`이면 `discard`(re-arm), 아니면 `continue`(데이터 부족=보류, latch
      유지). (`and`/`or` 둘 다 결함 → 2단계 확정.) detect_wakes 스케줄러-스레드 fetch 0 보장.
- [ ] **B3** prefetch 메서드 추가(가격 5s/바 60s, 심볼=held_and_watched) — WakeDetector 또는 modes/agent.
- [ ] **B4** `src/trading/modes/agent.py`: `agent_prefetch` seconds job(5s) 등록(`start()` 스케줄러 배선,
      steering on일 때만, agent_wake 옆).
- [ ] **B5** `src/trading/scheduler.py`: ThreadPoolExecutor `max_workers=16`으로 상향(critic LOW, 풀 여유).
- [ ] **T-U1** 테스트: 타임아웃 주입(`_client` **및 lazy `_data_client`** 둘 다 세션 request에 timeout
      전달 검증, 모킹) / peek miss→None / **abnormal latch가 캐시 미스(peek None)에도 유지(re-arm 안 됨)** /
      detect_wakes 네트워크 호출 0(모킹 provider call count=0) / prefetch가 캐시 채움 / 기존 wake 회귀.

## U2 — 런처 self-heal (검증 bun test, 서브모듈) — critic R1+R3 반영 (advance-only 폐기)
- [ ] **C1** `operator-console/launcher/daemon.ts`: `WEDGE_PATIENCE_MS=180_000`, `RESTART_HEALTH_MS=180_000` 신규.
      **기존 `healthWait`(fresh&&advanced) 그대로 재사용 — fresh 게이트 유지(R3: 제거하면 죽은-데몬 attach
      레이스).** active(wedge 후보) 경로를 **별도 헬퍼로 빼 early-return**(critic R3: 그냥 끼우면 restart 후
      공통 :267 healthWait가 또 돌아 이중 실행): ① `healthWait(WEDGE_PATIENCE_MS)` healthy면 return →
      ② unhealthy면 **restart 직전 `isFreshNow()` 레이스 가드(active 경로 신규)** → `systemctl --user
      restart` 1회 → ③ `healthWait(RESTART_HEALTH_MS)` → return / fail-closed throw. inactive는 기존
      start→:267 `healthWait(60s)` 유지(회귀 0). **새 advanceOnlyWait/detectWedge 추가 금지.**
- [ ] **C2** `operator-console/test/launcher.test.ts`: active+정지(advance 0)→180s 후 restart 1회→attach /
      active 도중 advance(busy/slow, 1 publish 주기 내)→restart 안 함 / restart 후에도 정지→fail-closed
      throw(이중 healthWait 없음 확인) / 기존 fresh+advance(`:198,:218`) 회귀 / inactive start 60s 유지 회귀.

## Build & Test
- [ ] pytest 전체 회귀 + U1 신규.
- [ ] launcher 테스트 러너로 U2.
- [ ] worktree live-verify(paper, read-only): 타임아웃 실제 적용 + detect_wakes skip 소멸 관찰.
- [ ] (선택) `/critic` — self-heal 잔여 리스크(대형 bus 배치 점유 vs 3분 patience) 검토.

## 미해결/확인 항목
- alpaca-py `_session` 속성명 worktree 재확인(버전 변동 대비 graceful no-op로 방어). 현 0.43.2=확인됨.
- self-heal patience 3분 vs bus 배치 최악 점유(현 규모 안전; 유니버스 확장 시 재검토).
