"""F64: the immutable operating constitution + the deterministic compliance gate
that bounds the agent's self-rewritten guidance.

Two layers wrap the agent's guidance prompt (see ``self_rewrite.build_guidance``):
  1. AGENT_CONSTITUTION — this constant, prepended to every generation. It lives
     in repo CODE (never the agent-writable workspace), so the agent cannot edit
     it. Its purpose is narrow: keep the SELF-IMPROVEMENT quality from decaying.
     It deliberately omits execution-safety rules already enforced by code
     (advisory-only / mandatory stop / risk caps / universe+short-ETB / schema).
  2. the evolvable guidance the agent rewrites — checked by ``check_compliance``.

Changing the constitution requires a human: ``tests/test_constitution_pin.py``
pins its checksum, so any edit fails CI until a person updates the pin (= their
approval). ``check_compliance`` is a pure deterministic BACKSTOP on the evolvable
text — the real execution-safety enforcement is the RiskManager/executor code.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

AGENT_CONSTITUTION = """\
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
"""


def constitution_sha256() -> str:
    return hashlib.sha256(AGENT_CONSTITUTION.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ComplianceResult:
    ok: bool
    reason: str | None = None


# Max fraction of the evolvable text that may change in one revision (a safety
# ceiling for constitution rule 5's "prefer gradual"; not the soft preference).
MAX_DELTA_FRACTION = 0.6
MAX_LEN = 6000

# A) contradiction backstop — evolvable text trying to undo a CODE invariant.
#    Regex/keywords are necessarily imperfect (the LLM can phrase around them);
#    the real guard is the RiskManager/executor. This only catches the obvious.
_DENYLIST = [
    (r"\b(place|submit|execute)\b[^.\n]{0,40}\border", "claims order authority"),
    (r"\bi\s+will\s+(buy|sell|short|cover)\b", "claims order authority"),
    (r"\b(without|no|skip(ping)?)\b[^.\n]{0,20}\bstop", "rationalizes a stop-less entry"),
    (r"\bstop(s)?\b[^.\n]{0,15}\boptional", "treats the mandatory stop as optional"),
    (r"\bexceed\b[^.\n]{0,25}\b(cap|limit|max)", "directs exceeding risk caps"),
    (r"\b(ignore|bypass|override)\b[^.\n]{0,25}\b(riskmanager|risk manager|the gate|gate)", "bypasses the risk gate"),
    (r"\buse\s+force\b", "directs using the force bypass"),
    (r"\bshort\s+any\b", "ignores the short universe / ETB gate"),
    (r"\b(ignore|outside)\b[^.\n]{0,15}\b(etb|easy.to.borrow|the universe)", "ignores universe/ETB"),
]

# B) prompt-injection self-defense — evolvable text trying to disable the preamble.
_INJECTION = [
    (r"\bignore\b[^.\n]{0,30}\b(the\s+)?(constitution|rules|principles|preamble|above)", "tries to ignore the constitution"),
    (r"\bdisregard\b[^.\n]{0,30}\b(the\s+)?(constitution|rules|preamble|above)", "tries to disregard the constitution"),
    (r"\bfrom now on[^.\n]{0,30}\b(the\s+)?rules?\s+(are|is)", "tries to redefine the rules"),
    (r"##\s*OPERATING CONSTITUTION", "injects a constitution header"),
]


def check_compliance(evolved: str, parent: str, constitution: str = AGENT_CONSTITUTION) -> ComplianceResult:
    """Pure deterministic gate on a proposed evolvable-guidance revision.

    fail-closed: any match / bound violation rejects the revision (the caller
    keeps the prior version). Returns the FIRST reason found.
    """
    text = evolved or ""
    low = text.lower()

    # Content safety first (report the meaningful reason, not just size):
    # B) injection self-defense
    for pat, reason in _INJECTION:
        if re.search(pat, text, re.IGNORECASE):
            return ComplianceResult(False, f"injection: {reason}")

    # A) contradiction backstop
    for pat, reason in _DENYLIST:
        if re.search(pat, low, re.IGNORECASE):
            return ComplianceResult(False, f"contradicts a code invariant: {reason}")

    # C) structural bounds (size ceiling for rule-5 'prefer gradual')
    if len(text) > MAX_LEN:
        return ComplianceResult(False, f"too long ({len(text)} > {MAX_LEN})")
    changed = 1.0 - SequenceMatcher(None, parent or "", text).ratio()
    if (parent or "") and changed > MAX_DELTA_FRACTION:
        return ComplianceResult(False, f"change too large ({changed:.0%} > {MAX_DELTA_FRACTION:.0%})")

    return ComplianceResult(True, None)
