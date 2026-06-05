# Functional Design — F64 unit-self-rewrite

> **Track**: F64 · **Unit**: self-rewrite · **Phase**: Functional Design · **Date**: 2026-06-05
> **선행**: F62 (효능/롤백 메트릭), F65 (회상; prompts.py 조립 정합)
> 헌장 문구·컴플라이언스 규격은 동봉 `constitution.md` 참조.

---

## 1. Data Model (prompt_manager 재사용)

기존 `src/strategy/llm/prompt_manager.py`의 `PromptVersion`/`PromptHistory`(version,
parent_version, created_at, content, get_latest/get_best)를 재사용한다. 에이전트 가이던스용
저장소를 추가:

```python
class GuidanceVersion(BaseModel):     # PromptVersion 패턴
    version: str                      # 예: "g3"
    parent_version: str | None
    created_at: datetime
    evolved_section: str              # 진화 가능 섹션 본문 (헌장 제외)
    adopted_metric_snapshot: dict     # 채택 시점 F62 효능 스냅샷
    status: str = "active"            # active | rolled_back | rejected

class GuidanceHistory(BaseModel):
    versions: dict[str, GuidanceVersion]
    current_version: str = "seed"     # F62 Decision.prompt_version 기본과 정합
```
- 영속: `workspace/guidance/history.json` (감사·lineage). **헌장은 여기 없음** — 코드 상수.

---

## 2. 2층 프롬프트 조립 (FR-1) — critic HIGH#3 반영

**정정**: durable 가이던스는 prompts.py 안의 단일 블록이 아니라 **workspace `CLAUDE.md`**에 산다
(`prompts.py:4-7`; `journal.py:104`가 `templates/CLAUDE.md`를 시드). 그런데 **CLAUDE.md는
에이전트가 아무 턴에나 직접 쓸 수 있는 파일** → 진화 가이던스를 거기 두면 컴플라이언스 게이트를
우회해 직접 수정 가능 → F64 안전모델 붕괴.

**결정 (사용자: "Python prepend로 이전")**: 진화 가이던스를 **CLAUDE.md에서 들어내** Python이
관리하는 저장소로 옮기고, 프롬프트 조립 시 Python이 prepend한다. 에이전트는 그 텍스트를 **직접
쓰지 않고**, EOD에 "제안"만 한다(전용 출력/도구) → Python이 검증·영속.

```python
def build_guidance(history: GuidanceHistory) -> str:
    evolved = history.versions[history.current_version].evolved_section
    return AGENT_CONSTITUTION + "\n\n## EVOLVABLE GUIDANCE\n" + evolved
```

### 2.1 CLAUDE.md 재조정 (필수)
- `templates/CLAUDE.md`에서 **진화 대상 판단 휴리스틱을 제거**하고, 정적 역할·decision 스키마
  (`lessons_cited` 포함, F62)만 남긴다. 진화 휴리스틱의 단일 출처 = Python 저장소.
  (두 가이던스 출처가 공존하면 모순 → 단일화.)

### 2.2 주입 지점 — 전 프롬프트 빌더 (one-liner 아님)
`prompts.py`엔 ~10개 빌더가 있다: `morning_research_prompt`/`intraday_prompt`/`wake_prompt`/
`multi_research_initial_prompt`/`debate`/`synthesis`/`sub_agent`/`parallel_synthesis`/
`eod_review_prompt`. **가이던스가 필요한 턴**(morning/intraday/wake/multi_research)에 `build_guidance()`
를 주입한다. 평가 전용 턴(debate/synthesis/sub_agent)·EOD는 제외(특히 **EOD 자기재작성 턴에
진화 가이던스를 주입하면 재귀** → 제외). F65의 `build_lesson_context` 위임과 같은 조립부를 건드리므로
**F65 위에서 분기**(아래 §재귀/머지 주의).

### 2.3 prompt_version 스탬프
- 결정의 `prompt_version`은 LLM이 모르므로 **Python이 스탬프**(F62 §3.2 restamp와 동일 경로):
  오케스트레이터가 `read_decisions()[before:]`에 `history.current_version`을 찍는다.

### 2.4 남는 리스크 (정직)
에이전트는 워크스페이스 셸 접근이 있어 이론상 저장 파일을 덮어쓸 수 있다. 완화: 권위 사본을
**에이전트 cwd 밖**(또는 프롬프트가 참조하지 않는 경로)에 두고, 조립은 그 Python측 사본만 읽는다.
완전 차단은 아니며(셸 접근 존재), 정상 경로 우회를 비자명하게 만드는 수준.

---

## 3. EOD 자가재작성 루프 (FR-3,4,5,6)

```text
EOD turn:
  1. eff = efficacy.prompt_version_efficacy(decisions, outcomes)        # F62
  2. if not gate_ok(eff, current):                                      # FR-6.3 / F62 가드
        return  # min_sample/지속성 미충족 또는 쿨다운 → 보류
  3. evolved' = LLM_rewrite(current.evolved_section, eff, lessons)      # 비결정 1스텝
  4. result = check_compliance(evolved', current.evolved_section, AGENT_CONSTITUTION)  # 순수
     if not result.ok:                                                  # FR-4.4 fail-closed
        record_rejected(evolved', result.reason); emit("self_rewrite_rejected"); return
  5. if diff_size(evolved', current) > MAX_DELTA: reject; return        # FR-6.1 (검증과 합칠 수 있음)
  6. new = GuidanceVersion(parent=current, evolved_section=evolved',
                           adopted_metric_snapshot=eff)
     history.add(new); history.current_version = new.version            # FR-3.3 즉시 교체
```

### 자동 롤백 (FR-5, 별도 일배치 또는 EOD 후반)
```text
  if live_days(current_version) < N:                                    # cold-start (critic MED)
        return  # 신규 버전은 N일치 라이브 데이터 누적 전까지 롤백 판정 보류 (그동안 current 유지)
  m_new   = excess_over_window(current_version, N)                      # F62 (excess 부착본)
  m_parent= excess_over_window(parent_version, N)
  if m_new + MARGIN < m_parent:                                         # 악화
        history.current_version = parent_version
        mark(current, "rolled_back"); emit("guidance_rolled_back")
```
- **critic 정직성 정정**: 롤백은 (1) **parent 한 세대만** 되돌린다 — g1→g2→g3 점진 악화는
  자동 교정 못 하고 §드리프트 점검(FR-5.3)으로 **가시화만**. (2) excess는 F62가 부착한
  `outcome.excess`에 의존(벤치마크 경로) — F62 확장 전엔 롤백 신호 없음. (3) cold-start N일간은
  나쁜 세대가 라이브로 돌 수 있음(즉시교체의 감수 리스크).

### 드리프트 점검 (FR-5.3, 주기적)
- 현재 진화 섹션 vs **원본 시드** 가이던스의 누적 diff·메트릭 추세 리포트. 한 방향 표류 경고
  (자동 복귀는 parent까지만이므로 다세대 표류는 사람 가시화).

---

## 4. 안전장치 요약 (즉시교체 보완)
| 장치 | 위치 | 역할 |
|------|------|------|
| 불변 헌장 | constitution.py 상수 + prepend | 진화 품질 하한 (에이전트 write 불가) |
| 헌장 핀 테스트 | tests | 헌장 변경 = 사용자 승인 강제 (FR-7) |
| 컴플라이언스 검증 | check_compliance (순수) | 모순/인젝션/구조 위반 거부 (fail-closed) |
| 변경량 캡 / 쿨다운 | gate_ok + MAX_DELTA | 급변·과빈도 억제 (원칙5) |
| F62 통계 가드 | gate_ok | 소표본/노이즈 진화 보류 |
| 자동 롤백 | excess N일 비교 | **parent 1세대만** 복귀 (다세대 드리프트는 §드리프트 점검으로 가시화; cold-start N일 보류) |
| 드리프트 점검 | 주기 리포트 | 다세대 누적 표류 가시화 |
| 불변 경계(코드) | executor/RiskManager/스키마 | 실행-안전 — 자가재작성 영향권 밖 |

---

## 5. 파일 터치포인트
| 파일 | 변경 |
|------|------|
| `src/agent/constitution.py` (신규) | AGENT_CONSTITUTION 상수 + check_compliance(순수) |
| `src/agent/self_rewrite.py` (신규) | GuidanceVersion/History, build_guidance, EOD 루프, 롤백 |
| `src/agent/prompts.py` | 가이던스 필요 빌더(morning/intraday/wake/multi_research)에 build_guidance() 주입; 평가턴·EOD 제외(재귀 방지). **F65의 build_lesson_context 위임 위에서 분기** |
| `src/agent/templates/CLAUDE.md` | 진화 휴리스틱 제거(→Python 저장소 단일화); 정적 역할+decision 스키마만 유지 (§2.1) |
| `src/agent/orchestrator.py` | prompt_version 스탬프(restamp, F62 §3.2와 동일 경로) + 롤백 cold-start 가드 |
| `src/strategy/llm/prompt_manager.py` | PromptVersion/lineage 패턴 재사용 (필요시 일반화) |
| `src/agent/review.py` / `orchestrator.py` | EOD 재작성 스텝 + 롤백 배선 |
| `src/agent/steering/records.py` | EventKind에 self_rewrite_rejected / guidance_rolled_back (추가-only) |
| `tests/agent/test_constitution_pin.py` (신규) | 헌장 고정 체크섬 |

## 6. 테스트 (PBT Partial)
- 헌장 핀(1비트 변경 → red); 컴플라이언스 denylist/인젝션/구조 음성 테스트.
- gate_ok: min_sample 미달·쿨다운 → 보류 (음성).
- 즉시 교체: 정상 진화 → current_version 갱신 + Decision.prompt_version 반영.
- 자동 롤백: 합성 excess 악화 → parent 복귀 (음성/경계).
- build_guidance: 헌장 항상 prepend·해시 불변 (PBT).
