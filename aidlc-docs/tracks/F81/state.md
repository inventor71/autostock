# Track F81 — 13F 보유종목 시그널 소스 (Situational Awareness LP 등 기관 13F)

> Per-track state. **Single writer = this track's worktree session.** Never edit another
> track's state, and do not put this detail in the root `aidlc-state.md` (registry only).
> See `.aidlc-rule-details/common/concurrent-tracks.md`.

## Track Info
- **Track ID**: F81
- **Title**: 13F 보유종목 시그널 소스 — Situational Awareness LP(Aschenbrenner) 등 기관 13F를 주기적으로 따와 리서치 브리프에 공급
- **Type**: feature
- **Status**: merged → main 1e2b9b9 (2026-06-14)
- **Branch**: feat/F81
- **Worktree**: .claude/worktrees/F81
- **Submodule branch**: — (parent-repo Python only; operator-console/cli not touched)
- **Base commit**: 1a7645e
- **Start Date**: 2026-06-13

## Extension Configuration
| Extension | Enabled | Decided At |
|---|---|---|
| Security Baseline | **Yes** | Requirements Analysis (approved 2026-06-14) |
| Property-Based Testing | **Yes** — pure-functions/round-trip mode | Requirements Analysis (approved 2026-06-14) |

> 사용자가 요구사항 승인 시 확장 제안(둘 다 Enabled)을 함께 승인. Security Baseline은 SEC HTTP
> fetch/XML 파싱/CIK 입력에 적용; PBT는 holdings 파싱·diff·정규화 순수 로직에 적용.

## Scope
공개 보유내역(disclosed holdings)을 주기적으로 따와 봇 유니버스/브리프에 공급하는 신규 기능.
**소스-무관 2층 추상화**: `src/signals/holdings/` 에 `HoldingsProvider` 프로토콜 +
`HoldingsSnapshot` 정규화 레코드를 두고, **SEC EDGAR 13F는 첫 구현**(`providers/sec_13f.py`)일 뿐.
오버레이/브리프/방향게이트는 `HoldingsSnapshot`만 의존 → 후속에 다른 공시(13D/G 등)를 provider
추가만으로 plugin. 1차 대상 = Situational Awareness LP (CIK 0002045724). 롱→유니버스 편입,
풋/숏-사이드는 기존 숏 게이트(F54/F60 `risk.shorting_enabled`)와 comply. 자동 미러링 ❌.
관련: [[f61-market-signals]], F54/F60(숏), F77(소스 추가 선례).

## Merge Risk Notes
> 트랙이 `merge-awaiting` 전환 시 작성. `/ai-dlc-merge`가 큐 구성·충돌 해결 시 참조.
> 비워두면 `/ai-dlc-merge`가 `git diff --name-only`로 자동 추론.

- **공유 파일 (주의)**: `src/signals/records.py`(+disclosed_holdings 필드+import),
  `src/signals/collector.py`(+root 파라미터·_disclosed_holdings 단계·6번째 collect 단계),
  `src/signals/brief.py`(assemble_brief 시그니처+to_prompt_text 섹션),
  `src/signals/settings.py`(+DisclosedHoldingsConfig+필드), `src/universe/factory.py`
  (resolve_universe 끝부분 overlay union), `src/trading/modes/agent.py`(start()에 _setup_holdings_refresh
  호출 1줄 + 메서드 추가; F77 sweep/F82 collection 인접), `config/settings.yaml`(signals 블록).
- **API/시그니처 변경**: `assemble_brief(...)` keyword `disclosed_holdings` 추가(기존 호출 호환),
  `SignalCollector.__init__`에 `root=None` 추가(기존 호출 호환), `MarketSignalBrief`에 필드 추가
  (round-trip 호환). 모두 **additive** — 기존 호출부 무수정.
- **알려진 동시 변경**: 같은 `signals`/`universe`/`agent.py` 영역을 F61/F77/F78/F82가 건드림.
  agent.py `start()` 시퀀스와 settings.yaml `signals:` 블록은 rebase 시 인접 추가라 충돌 가능 —
  추가 위치(sweep 다음 / sentiment 블록 다음)만 맞추면 됨.

## Stage Progress
- [x] Workspace Detection
- [x] Requirements Analysis — standard (2 UAQ rounds; **approved 2026-06-14**)
- [x] User Stories — SKIP (단일 운영 자동화, 다중 페르소나/UX 표면 없음)
- [x] Workflow Planning — execution-plan.md (approved 2026-06-14)
- [x] Application Design — application-design.md (approved 2026-06-14)
- [x] NFR Requirements + Design — folded into application-design (fail-honest + SEC fair-access + Security Baseline)
- [x] Units Generation — SKIP (단일 응집 유닛 = `src/signals/holdings/` 서브패키지)
- [x] Construction (Code Generation)
  - [x] holdings 서브패키지 + sec_13f provider + overlay + 배선
  - [x] 테스트 40 passed + 라이브 SEC 스모크(SA LP 실데이터 32/37 mapped, 방향 정확)
- [x] Build & Test — ALL GREEN (build-and-test-summary.md + post-merge-guide.md)
