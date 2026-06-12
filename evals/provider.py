"""promptfoo Python provider: one test case = one scenario turn.

promptfoo passes per-test ``vars`` through ``context``; the provider runs the
full src/evals pipeline (sandbox -> production orchestrator turn -> artifact
extraction -> Tier-1 grading) and returns the report object as the output, so
asserts and the web viewer read structured fields instead of prose.

Recognized vars:
- ``scenario``: path to the scenario JSON (relative to this directory).
- ``guidance_file`` (optional): path to a guidance history.json payload to pin
  a specific F64 guidance version (the matrix axis). Omitted -> seed.
- ``guidance_label`` (optional): label echoed into the report.

The subject agent runs via the local ``claude`` CLI (subscription); only the
Tier-2 rubric grading (separate config) spends API tokens.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_EVALS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVALS_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def call_api(prompt: str, options: dict, context: dict) -> dict:
    from src.evals.runner import evaluate_scenario

    cfg = (options or {}).get("config", {}) or {}
    var = (context or {}).get("vars", {}) or {}

    scenario_path = _EVALS_DIR / str(var.get("scenario", prompt))
    if not scenario_path.exists():
        return {"error": f"scenario not found: {scenario_path}"}

    guidance_history = None
    label = str(var.get("guidance_label", "seed"))
    gfile = var.get("guidance_file")
    if gfile:
        gpath = _EVALS_DIR / str(gfile)
        guidance_history = json.loads(gpath.read_text(encoding="utf-8"))

    try:
        report = evaluate_scenario(
            scenario_path,
            guidance_history=guidance_history,
            guidance_label=label,
            model=str(cfg.get("model", "sonnet")),
            timeout=float(cfg["timeout"]) if cfg.get("timeout") else None,
        )
    except Exception as exc:  # surface as a failed case, not a crashed run
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {"output": report}
