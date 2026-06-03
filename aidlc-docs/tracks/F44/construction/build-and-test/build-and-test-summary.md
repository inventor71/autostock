# F44 — Build & Test 요약

## 빌드
- Python: 빌드 단계 없음(인터프리티드). main venv 사용.
- TUI 콘솔: `operator-console/cli` — `bun install --frozen-lockfile`(worktree-setup `--ts`로 완료),
  타입체크는 tsgo(turbo).

## 테스트 실행
```bash
# 1) daemon (Unit1 dedup + 회귀)
venv/bin/python -m pytest -q
#   tests/test_turn_dedup_f44.py        (단위 7 + property-based 1)
#   tests/test_steering_commands.py     (already_running / already_queued 추가 2)

# 2) TUI (Unit2 라벨 포매터)
(cd operator-console/cli/packages/tui-trading && PATH=~/.bun/bin:$PATH bun test)
#   test/progress-label.test.ts         (fmtElapsedClock + fmtTurnLabel, 8)

# 3) 타입체크 (콘솔 전체)
(cd operator-console/cli && PATH=~/.bun/bin:$PATH bun run typecheck)
```

## 결과 (2026-06-03)
| 스위트 | 결과 |
|--------|------|
| pytest (daemon) | **647 passed**, 0 fail |
| bun test (tui-trading) | **52 pass**, 0 fail |
| turbo typecheck (tsgo) | **19/19 successful** |

## 통합/수동 검증(권장, 선택)
데몬 재시작 후(F44 코드 적재) 라이브에서:
1. turn in-flight 중 타임라인 상단에 `● {type} · {elapsed}` 노출(초록 점멸), 경과가 ~매초 증가.
2. 동일 type research 실행 중 `/research` → outcome `already_running`(큐잉 안 됨).
3. 다른 type 실행 중 `/research` 2회 → 1회만 큐잉(2회차 `already_queued`), 라벨에 `+1 queued`.
4. 유휴/과거날짜 선택 시 상태줄 `idle`.

## 머지 핸드오프
- Build & Test green → `state.md` **Status: merge-awaiting**.
- 루트 레지스트리 F44 행은 `active` 유지(`/ai-dlc-merge`가 머지시 `merged`로 플립).
- 동시 트랙 F45(타임라인 12h)와 `timeline-bar.tsx` 영역 겹침 → 리베이스시 재확인.
