# F85 Post-Merge Guide — Aggressiveness 노브

## 무엇이 바뀌나 (prod 브랜치)
- **신규 설정 키**: `config/settings.yaml` → `agent.aggressiveness: conservative | balanced | aggressive`
  (기본 `balanced`). **`balanced` = 기존 동작과 100% 동일** — 키를 안 건드리면 배포 영향 0.
- **신규 모듈**: `src/agent/aggressiveness.py` (레벨→파라미터 SSOT). 다른 모듈은 여기서 읽기만.
- **한 다이얼이 세 레이어에 팬아웃**:
  1. **프롬프트 성향** — conservative/aggressive만 per-turn 성향 블록 주입(balanced=무주입).
     intraday "do not churn" 문구도 레벨화. (CLAUDE.md 템플릿은 **안 건드림** → 기존 워크스페이스 무영향.)
  2. **리스크 게이트** — `RiskManager`에 named-field overlay(사이즈/스톱/포지션수/R:R/할트). 에이전트
     경로에만 적용. `shorting_enabled` 등 안전 게이트·`use_bracket_orders`는 불변(테스트로 보증).
  3. **학습 시간축** — 각 결정에 `aggressiveness`+`grading_horizon_days` 스탬핑. efficacy는 **성숙
     결정만**(horizon 경과/청산) 채점하고 excess를 **per-day 정규화**. 신규 ledger
     `workspace/grades.jsonl`(성숙 시점 1회 확정채점, EOD 전용 writer).
- **신규 prod 파일**: `workspace/grades.jsonl` (append-only 감사/freeze ledger).
- **의미 변경(주의)**: `efficacy.avg_excess`가 이제 **per-holding-day** 기준(이전엔 전체 보유기간 누적).
  win_rate(부호)는 불변. F64 자가재작성 비교가 horizon 간 비교가능해짐.

## 전제 조건
- **데몬 재시작 필요** (정적 config). 변경 후 `agent` 모드 데몬 재가동.
- 신규 외부 의존성 없음. 키 미설정 시 자동 `balanced`.

## 실사용 검증 체크리스트 (머지 후 1회)
1. **기본(balanced) 무영향 확인**: 키 없이 데몬 기동 → startup 로그에
   `Aggressiveness: balanced (grading_horizon=20d, max_position_pct=0.05, recall_recency=0.5)` 1줄.
   리스크/프롬프트 동작이 이전과 동일한지(평소 턴) 관찰.
2. **레벨 전환**: `settings.yaml`에서 `agent.aggressiveness: aggressive` → 재시작 → startup 로그가
   `max_position_pct=0.08, grading_horizon=3d`로 바뀌는지. 모닝/intraday 프롬프트에 "Posture —
   aggressive" 블록이 실리는지(steering 또는 turn 로그).
3. **오타 fail-safe**: `aggressiveness: agressive`(오타) → 데몬이 **크래시 없이** 경고 로그
   `unknown aggressiveness 'agressive'; falling back to 'balanced'` 후 balanced로 기동.
4. **학습 ledger**: 며칠 운용 후 EOD에 `workspace/grades.jsonl`이 생기고, 성숙 결정만 1줄씩
   누적되는지(같은 결정 중복 없음). conservative(45d)는 초기 ~45일간 대부분 "pending"(미성숙)이라
   ledger가 천천히 차는 게 **정상**.

## 튜닝 노브
- 레벨별 숫자 전부 `src/agent/aggressiveness.py` `PROFILES` 한 곳. 운영 데이터로 보정 시 여기만 수정.
- 핵심: `grading_horizon_days`(45/20/3), `recall_recency`(0.25/0.5/1.0), `max_position_pct`(0.03/0.05/0.08).

## 롤백
- 즉시: `settings.yaml`에서 `agent.aggressiveness: balanced`(또는 키 삭제) → 재시작. 동작 원복.
- 코드 롤백 시: `Decision`의 신규 두 필드·`grades.jsonl`은 append-only라 잔존해도 무해(legacy 파싱 OK).

## 알려진 한계 / 범위 외 (후속 스택)
- **aggressive 같은날 스캘프 학습 미지원**: 같은 날 청산 round-trip은 일봉 1 bar라 채점 불가 →
  aggressive는 *거래*는 단타로 하되 *학습*은 1~3일 스윙에서만. 진짜 intraday 채점은 **C2-full**(후속).
- conservative 콜드스타트: 첫 ~45일 efficacy/EOD 품질요약이 비다시피 함(미성숙) — 정상.
- C4 `idle_days` 레슨 은퇴 레벨화, F74 nightly 자동화, scheduler 틱 간격 레벨화 = 후속.
- **F74 레벨 시나리오**(`aggressive-momentum-breakout`/`conservative-value-pass`)는 LLM-grade(Tier-1,
  구독 토큰) — CI 비포함. 수동 실행: `cd evals && bunx promptfoo eval --filter-pattern "momentum-breakout"`.
