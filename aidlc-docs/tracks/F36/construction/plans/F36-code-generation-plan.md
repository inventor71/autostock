# F36 — Code Generation Plan (Unit: timeline-historical-overlay-fix)

> 승인 후 Construction은 자율 진행([[feedback-autonomy-construction]]). **F35 이후 monorepo** —
> `operator-console/cli` 는 일반 in-repo 디렉터리(서브모듈/gitlink 없음). 단일 `feat/F36`
> worktree 하나가 Python+TS 전부 커버. 모든 코드 편집은 worktree 안에서.

## Step 0 — Worktree 게이트 (코드 전 필수)
- [x] `git worktree add .claude/worktrees/F36 -b feat/F36 2253029` (현재 main, post-F35 monorepo).
      서브모듈 체크아웃 단계 없음 — `operator-console/cli/...` 는 이 worktree 안의 일반 경로.
      모든 TS 편집은 worktree 안에서. **DONE 2026-06-03** (worktree @ 2253029).

## Step 1 — `use-session-data.ts`: decisions 복원 + 상관  ✅ DONE
- [x] `SessionData` 에 `decisions: MonitorDecision[]` 필드 추가.
- [x] live 분기 반환에 `decisions: monitor.decisions ?? []` 추가.
- [x] historical 분기: `decisions.jsonl` 읽기(`readJsonl`) → `recordEtDate(r)===etDate` 필터 →
      `turnIdx = rawTurns.map(r => [r.started_at??r.ts, r.turn_id??r.id])` (그 날짜 turns 기준) →
      각 결정에 `r.turn_id ?? correlateTurnId(r.ts, turnIdx)` 부여 → `MonitorDecision` 매핑
      (`normalizeAction` 대문자 정규화 + 화이트리스트, confidence/reason/source 기본값).
      `rawTurns` 를 분리해 `started_at` 보존(매핑된 MonitorTurn 에는 started_at 없음).
- [x] `correlateTurnId(ts, turnIdx)` 헬퍼(export): reversed-first `started<=ts`,
      둘 다 parse되면 `Date.parse` instant 비교, 아니면 lexical(=runtime.py 동일).

## Step 2 — `use-overlay.ts`: turn 객체 보유  ✅ DONE
- [x] `OverlayState` 에 `turn: MonitorTurn|null`, `decisions: MonitorDecision[]` 추가;
      `turnId` 제거(잔재 없음). `CLOSED` 기본값 갱신.
- [x] `openTurn(turn, decisions, x, y)` 토글 비교 `cur.turn?.id===turn.id`;
      openSymbol/openIntervention 도 turn/decisions 리셋.

## Step 3 — `turn-overlay.tsx`: props 소스 교체  ✅ DONE
- [x] props: `monitor`/`turnId` 제거 → `turn: MonitorTurn` + `decisions: MonitorDecision[]`.
- [x] `turn()=>props.turn`, `decisions()=>props.decisions`; fallback "Turn not found" 유지.

## Step 4 — `timeline-bar.tsx`: 클릭 콜백이 전체 객체 전달  ✅ DONE
- [x] `onMarkerClick` → `(turn, decisions, x, y)`, `onInterventionClick` → `(iv, x, y)`.
- [x] MarkerRow 에 `decisions={session().decisions}` 전달 + `decisionsFor(id)` 헬퍼.
- [x] 마커 직접 핸들러 / 개입 직접 핸들러 / F34 라벨셀(`:282`,`:284`) 모두 전체 객체 전달.
- [x] `session` 메모·F34 z-order/렌더 로직 불변(회귀 없음).

## Step 5 — `index.tsx`: 배선 + 마운트 교체  ✅ DONE
- [x] `onMarkerClick={(turn,dec,x,y)=>overlay.openTurn(turn,dec,x,y)}`.
- [x] `onInterventionClick={(iv,x,y)=>overlay.openIntervention(iv,x,y)}` (라이브 `find` 삭제).
- [x] TurnOverlay 마운트: `turn`/`decisions` props, `Show when=…overlay.state().turn` (monitor 의존 제거).

## Step 6 — 빌드/타입체크/테스트  ✅ DONE
- [x] `tsgo --noEmit` (opencode, @tui-trading/core 그래프 포함) — **0 errors, exit 0**.
- [x] `test/session-data.test.ts`: correlateTurnId(이전/경계/빈/lexical) + readSessionData
      historical(turns et_date 필터, decisions 복원·상관 W12/W13/null, action/confidence 정규화,
      오버레이 per-turn 필터, live 패스스루). **bun test 35 pass / 0 fail**.
- [ ] `bun test` 해당 패키지 그린.

## Step 7 — 라이브 검증(사용자 직접) + 핀
- [~] **docker-verify `attach` 준비 완료** — 사용자가 직접 확인. ([[worktree-live-verification]])
  - 호스트 prep DONE: `scripts/worktree-setup.sh F36 --docker-verify` → `.env.test` 복사(main TEST 계정).
  - 과거 세션 시드: `scripts/seed_timeline.py` (NEW, 재사용 타임라인 시더) — 과거 ET 날짜에
    turns+**decisions**(turn_id 없음 → 상관 경로 실측)+interventions를 기록. `--days N` 로 연속 N일을
    한 번에, 날짜별로 시각/턴수를 결정론적으로 변형(date 기반 RNG). 결정은 턴 윈도 안에 찍혀 상관 보존.
  - 실행(워크트리 dir에서):
    ① `scripts/verify-run.sh build`
    ② 시드(named volume에 기록): `scripts/verify-run.sh run --rm --entrypoint python attach scripts/seed_timeline.py --workspace /app/workspace --date 2026-06-02 --days 6 --overwrite`
    ③ `scripts/verify-run.sh run --rm -it attach` → 콘솔에서 `[ < ]` 로 어제 이동 →
       turn 마커 클릭=결정 목록 표시("not found" 사라짐), ◆ 개입 마커 클릭=오버레이 오픈,
       `[ Today ]` 복귀 시 라이브 오버레이 회귀 없음.
- [ ] (선택) critic 스킬로 상관 로직·경계(day boundary, started_at 부재 turn) 리뷰.
- [ ] feat/F36 커밋(단일 브랜치, monorepo) → 머지 시 main 으로. gitlink/서브모듈 단계 없음.

## Risk / Notes
- started_at 포맷 불일치 시 Step1 fallback 가동(Date.parse). turns.jsonl 일부 레코드에
  started_at 없을 수 있음(그땐 `ts` 사용 — Step1에 명시).
- live monitor.decisions 는 tail(N) — 오늘 오버레이가 일부 결정만 보이는 기존 동작 유지(회귀 아님).
- 0 new deps. Python/데몬 발행 경로 불변(콘솔은 읽기 전용 NFR 유지).
