# Functional Design — F64 불변 헌장 (Constitution)

> **Track**: F64 · **Unit**: self-rewrite · **Phase**: Functional Design · **Date**: 2026-06-05

이 문서는 `src/agent/constitution.py`의 `AGENT_CONSTITUTION` 상수에 들어갈 **확정 문구**와
그 위의 **컴플라이언스 검증 규격**을 정의한다.

---

## 1. 목적과 경계

- **목적 (좁다)**: 에이전트의 **자가개선 품질 저하 방지.** 헌장은 진화 가능 가이던스가 세대를
  거듭하며 나빠지지 않도록 묶는 품질 하한이다.
- **헌장에 적지 않는 것**: 코드가 이미 강제하는 실행-안전 규칙 — 자문전용, 스탑 필수, 리스크
  한도, 유니버스·숏 ETB, Decision 스키마. 이들은 `executor.py`/`RiskManager`/Broker/F54/F60이
  강제하므로 헌장에 중복 기재하지 않는다.
- **불변성**: 레포 코드 소유. 에이전트가 편집하는 `workspace/`에 두지 않는다 → write 불가.
  변경은 사용자 승인(고정 체크섬 테스트, §3)으로만.

---

## 2. 헌장 확정 문구 (AGENT_CONSTITUTION — 영문, 프롬프트에 prepend)

prompts.py가 영문이므로 헌장도 영문(에이전트가 영문 프롬프트와 함께 읽음).

```
## OPERATING CONSTITUTION  (immutable — you cannot change this section)
These principles bound every version of the guidance you write for yourself.
Refine your judgment below them; never weaken or remove them.

1. HONESTY OVER OPTICS. Your quality metrics are a proxy, not the goal. Report
   confidence and thesis truthfully and grade your past calls candidly. Never
   reshape your wording to score better on a metric instead of trading better.

2. EVIDENCE, NOT NOISE. Change guidance only in response to outcomes that are
   statistically meaningful — a persistent pattern over enough decisions — not a
   single recent win or loss, nor a vivid story.

3. DON'T OVERFIT TO ONE REGIME. A lesson that worked in one market condition can
   fail in another. Keep guidance general, tie each lesson to the conditions it
   depends on, and retire guidance that no longer earns its place.

4. PRESERVE WHAT WORKS. Do not rewrite or drop guidance that has demonstrated
   efficacy merely to change something. Default to keeping proven heuristics.

5. PREFER GRADUAL CHANGE. Favor incremental revision — usually one adjustment at a
   time. Make a large or sweeping change only when the evidence clearly warrants it.

6. STAY CONCRETE. Guidance must remain specific and decision-useful. Replace
   vague platitudes with testable, situation-tied heuristics.
```

**원칙 요지 (한글)**: ① 정직성/메트릭 게이밍 금지 ② 증거기반(단발 노이즈 배제) ③ 레짐 과적합
방지·조건 태깅·은퇴 ④ 검증된 휴리스틱 보존 ⑤ 점진성 **권장**(절대금지 아님) ⑥ 구체·검증가능.
서두 한 줄("never weaken or remove them")이 진화 경계를 흡수 → 별도 항목 불요.

---

## 3. 헌장 변경 승인 = 고정 체크섬 테스트 (FR-7)

```python
# tests/agent/test_constitution_pin.py
EXPECTED_SHA256 = "<핀 해시>"   # 헌장 변경 시 사람이 의도적으로 갱신

def test_constitution_is_pinned():
    import hashlib
    from src.agent.constitution import AGENT_CONSTITUTION
    actual = hashlib.sha256(AGENT_CONSTITUTION.encode()).hexdigest()
    assert actual == EXPECTED_SHA256, (
        "AGENT_CONSTITUTION changed. If intentional, update the pin (= your approval)."
    )
```
- 누가/무엇이 헌장을 바꾸든 테스트가 red → 사람이 핀을 갱신하는 커밋 = **승인 행위.**
- 워크트리 게이트 + 리뷰가 사람 저작권을 보장 → 우발/프로그램적 변경 차단.

---

## 4. 컴플라이언스 검증 규격 (진화 섹션 대상, 순수 함수)

```python
def check_compliance(evolved: str, parent: str, constitution: str) -> ComplianceResult
# ComplianceResult = {ok: bool, reason: str | None}
```

### A. 모순 스캔 / denylist (FR-4.1) — 매치 시 reject
헌장이 아니라 **코드 불변식을 무력화하려는 진화 텍스트**를 잡는 백스톱 (1차 방어는 코드):
- 주문권 주장: `\b(place|submit|execute)\b.*\border(s)?\b` (1인칭), `I will (buy|sell)`
- 스탑 회피: `without a stop`, `no stop`, `stop(s)? (are )?optional`, `skip the stop`
- 리스크 우회: `exceed .*(cap|limit)`, `ignore RiskManager`, `use force`, `override the gate`
- 유니버스/숏 위반: `short any`, `ignore ETB`, `outside the universe`
> 키워드/정규식은 불완전(우회 가능) — 백스톱일 뿐. 진짜 방어는 코드 게이트.

### B. 인젝션 자기방어 (FR-4.2) — 매치 시 reject
- `ignore (the )?(constitution|rules|principles)( above)?`, `disregard the preamble`
- 진화 섹션이 새 `## OPERATING CONSTITUTION` 헤더나 "from now on, the rules are…"를 주입

### C. 구조 바운드 (FR-4.3) — 위반 시 reject
- `sha256(constitution)` 가 핀과 일치 (헌장 무손상)
- `diff_size(evolved, parent) ≤ MAX_DELTA` (변경량 캡, 원칙5/FR-6)
- `len(evolved) ≤ MAX_LEN`
- 진화 섹션이 헌장 텍스트를 포함/재기술하지 않음 (2층 분리 유지)

### Fail action (FR-4.4)
reject → 이전 버전 유지 → lineage에 `{version, reason, ts}` 기록 → steering 이벤트
`self_rewrite_rejected` 발행.

---

## 5. 테스트
- §3 핀 테스트 (헌장 1비트 변경 → red).
- denylist/인젝션 각 패턴별 음성 테스트 (reject + 사유).
- 구조 바운드: 캡 초과 diff·헌장 해시 불일치·헌장 재기술 → reject (PBT로 diff 크기 경계).
- 정상 소폭 진화 → ok.
