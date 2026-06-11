"""F64: constitution-bounded prompt self-rewrite.

The agent evolves the "evolvable guidance" section of its own prompt from its
measured outcomes (F62 efficacy). The immutable constitution
(``constitution.AGENT_CONSTITUTION``) is prepended to every generation and is NOT
part of this store, so the agent cannot edit it. The evolvable section lives in a
Python-managed store (NOT a free markdown file the agent edits each turn) — the
agent only *proposes* a new version at EOD via an injected ``rewrite_fn``; this
module validates (constitution compliance), gates (cooldown / min-sample / change
cap), adopts immediately on pass, and auto-rolls-back a version that degrades.

All decision logic here is pure/deterministic; the only nondeterminism is the
injected ``rewrite_fn`` (the LLM turn), which defaults to None (inert) — so the
machinery ships safe and is activated by providing a rewrite_fn.

Residual risk (documented): the agent has shell access to the workspace, so a
determined agent could overwrite the store file. Mitigation: callers should keep
the authoritative copy outside the agent cwd; this is not a hard lockout.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, Field

from src.agent.learning.constitution import AGENT_CONSTITUTION, check_compliance
from src.agent.learning.efficacy import MIN_EFFICACY_SAMPLE

SEED_VERSION = "seed"
_SEED_GUIDANCE = (
    "Refine these heuristics over time from your measured outcomes:\n"
    "- Weigh downside before upside; size to the stop distance, not conviction.\n"
    "- Prefer setups your past calls actually scored well on (see the lessons shown).\n"
)


class GuidanceVersion(BaseModel):
    version: str
    parent_version: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    evolved_section: str = ""
    adopted_metric: dict = Field(default_factory=dict)  # F62 efficacy snapshot
    status: str = "active"  # active | rolled_back | rejected


class GuidanceHistory(BaseModel):
    versions: dict[str, GuidanceVersion] = Field(default_factory=dict)
    current_version: str = SEED_VERSION

    def current(self) -> GuidanceVersion:
        return self.versions[self.current_version]

    def add(self, v: GuidanceVersion) -> None:
        self.versions[v.version] = v

    def next_version_id(self) -> str:
        g_keys = [k for k in self.versions if k.startswith("g")]
        if not g_keys:
            return "g1"
        max_n = max(int(k[1:]) for k in g_keys if k[1:].isdigit())
        return f"g{max_n + 1}"


def seed_history() -> GuidanceHistory:
    seed = GuidanceVersion(version=SEED_VERSION, parent_version=None, evolved_section=_SEED_GUIDANCE)
    return GuidanceHistory(versions={SEED_VERSION: seed}, current_version=SEED_VERSION)


# --------------------------------------------------------------------------- #
# 2-layer prompt assembly
# --------------------------------------------------------------------------- #
def build_guidance(history: GuidanceHistory) -> str:
    """Immutable constitution (code) prepended to the current evolvable section."""
    evolved = history.current().evolved_section
    return AGENT_CONSTITUTION + "\n\n## EVOLVABLE GUIDANCE\n" + evolved


# --------------------------------------------------------------------------- #
# persistence (workspace/guidance/history.json)
# --------------------------------------------------------------------------- #
def _store_path(root: str | Path) -> Path:
    return Path(root) / "guidance" / "history.json"


def load_history(root: str | Path) -> GuidanceHistory:
    p = _store_path(root)
    if not p.exists():
        return seed_history()
    try:
        return GuidanceHistory.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"guidance history unreadable, reseeding: {exc}")
        return seed_history()


def save_history(root: str | Path, history: GuidanceHistory) -> None:
    from src.agent.steering.jsonl import atomic_write_text

    p = _store_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(p, history.model_dump_json(indent=2))


# --------------------------------------------------------------------------- #
# rewrite loop (gates -> propose -> compliance -> adopt)
# --------------------------------------------------------------------------- #
class RewriteResult(BaseModel):
    action: str  # "disabled" | "held" | "rejected" | "adopted"
    version: str | None = None
    reason: str | None = None


def should_rewrite(
    history: GuidanceHistory,
    version_sample: int,
    *,
    today: date | None = None,
    cooldown_days: int = 7,
    min_sample: int = MIN_EFFICACY_SAMPLE,
) -> bool:
    """Gate (constitution rule 5 'gradual' + F62 small-sample guard): hold unless
    the current version is past its cooldown AND has enough measured decisions."""
    if version_sample < min_sample:
        return False
    today = today or date.today()
    age = (today - history.current().created_at.date()).days
    return age >= cooldown_days


def propose_rewrite(
    history: GuidanceHistory,
    efficacy_snapshot: dict,
    *,
    rewrite_fn=None,
    today: date | None = None,
) -> RewriteResult:
    """Run one EOD self-rewrite. ``rewrite_fn(current_evolved, efficacy) -> str``
    is the LLM proposal; None = inert (default, ships safe). Mutates ``history``
    in place on adoption; the caller persists. fail-closed on compliance.
    """
    if rewrite_fn is None:
        return RewriteResult(action="disabled")
    current = history.current()
    try:
        proposed = rewrite_fn(current.evolved_section, efficacy_snapshot)
    except Exception as exc:
        logger.warning(f"self-rewrite proposal failed: {exc}")
        return RewriteResult(action="held", reason=f"proposal error: {exc}")

    result = check_compliance(proposed, current.evolved_section,
                              is_seed_parent=(current.version == SEED_VERSION))
    if not result.ok:
        # record the rejected attempt in lineage for audit, do NOT adopt
        rej = history.next_version_id()
        history.add(GuidanceVersion(
            version=rej, parent_version=current.version,
            evolved_section=proposed, status="rejected",
        ))
        logger.warning(f"self-rewrite rejected ({rej}): {result.reason}")
        return RewriteResult(action="rejected", version=rej, reason=result.reason)

    new_id = history.next_version_id()
    history.add(GuidanceVersion(
        version=new_id, parent_version=current.version,
        evolved_section=proposed, adopted_metric=dict(efficacy_snapshot or {}),
        status="active",
    ))
    history.current_version = new_id  # immediate swap (user decision)
    return RewriteResult(action="adopted", version=new_id)


def maybe_rollback(
    history: GuidanceHistory,
    version_excess: dict[str, float | None],
    *,
    today: date | None = None,
    n_days: int = 5,
    margin: float = 0.0,
) -> bool:
    """Auto-rollback ONE generation: if the current version, after ``n_days`` of
    live data, has worse benchmark-excess than its parent (by more than margin),
    revert to the parent. Cold-start: no decision until n_days of live data.
    Returns True iff a rollback happened. (Multi-generation drift is only
    SURFACED by a separate seed-regression report, not auto-corrected.)
    """
    today = today or date.today()
    cur = history.current()
    if cur.parent_version is None or cur.parent_version not in history.versions:
        return False
    if (today - cur.created_at.date()).days < n_days:
        return False  # cold-start
    m_new = version_excess.get(cur.version)
    m_par = version_excess.get(cur.parent_version)
    if m_new is None or m_par is None:
        return False
    if m_new + margin < m_par:
        cur_obj = history.versions[cur.version]
        history.versions[cur.version] = cur_obj.model_copy(update={"status": "rolled_back"})
        history.current_version = cur.parent_version
        logger.warning(f"guidance {cur.version} rolled back to {cur.parent_version} "
                       f"(excess {m_new:.4f} < parent {m_par:.4f})")
        return True
    return False
