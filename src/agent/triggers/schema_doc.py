"""The authoritative `ctx`/predicate contract, surfaced to the agent (critic#7).

The agent cannot read autostock source (F39), so the predicate contract must reach
it through a channel it CAN read: this doc is seeded into ``workspace/triggers/
ctx-schema.md`` by the daemon at startup, and the ``trigger register`` tool help
points at it. Keep this in sync with ``models.py`` / ``fetch.py`` / ``sandbox.py``.
"""

from __future__ import annotations

from pathlib import Path

CTX_SCHEMA_MD = '''# Long-horizon trigger — predicate & ctx contract (F88)

You can register a **long-horizon trigger**: a small Python predicate the daemon
evaluates on a slow cadence (hourly or daily). When it returns `fire=True`, you are
woken (an out-of-band turn) to reason about it — the trigger itself NEVER trades.

## The predicate

Write a file defining exactly one function:

```python
def should_fire(ctx):
    # ctx is a plain dict the daemon assembled from your declared sources.
    vix = ctx.get("macro", {}).get("vix")
    return {"fire": vix is not None and vix > 25, "why": f"vix={vix}"}
```

- Return `{"fire": <bool>, "why": "<short reason>"}`. `fire` MUST be a real bool.
- It is a **pure function over `ctx`** — no network, no filesystem, no secrets. It
  runs in a locked-down sandbox (no autostock source, `--network=none`). Any attempt
  to reach the network/source/env raises and is treated as fire=False.
- Allowed imports only: `math, statistics, json, re, datetime, decimal, fractions,
  itertools, functools, collections, typing, operator`. No `os/sys/subprocess/...`.
- Keep it small (<16KB). On any error the trigger fails closed (does not fire) and,
  after repeated errors, auto-disables.

## The `ctx` dict

`ctx["_meta"]` = `{"built_at": <iso>, "sources": [<keys>]}`. Each declared source
appears under its key:

- **signal** (`{"kind":"signal","name":"<name>"}`) → under `ctx["<name>"]`. Names:
  `macro` (yields/dollar/gold/oil/VIX), `movers`, `earnings`, `holdings`. (`sentiment`
  is a follow-up.)
- **webfetch** (`{"kind":"webfetch","url":"https://<allowlisted-host>/..."}`) → under
  `ctx["fetch_<host>"]` = `{"status": <int>, "body": "<text, capped>", "host": "..."}`.
  Only allow-listed domains are fetched.
- A source that failed to fetch appears as `{"_error": "<reason>"}` under its key —
  check for it; treat a missing datum as "unknown", not 0.

## Registering (via the agent tool)

```
python -m src.agent.tools trigger register \\
  --id semi-capex-rollover --thesis "semis capex cycle rolling over" \\
  --cadence daily --ttl-days 60 \\
  --sources-json '[{"kind":"signal","name":"macro"}]' \\
  --predicate-file <path-you-wrote-with-should_fire>
```

- `--no-entry-inducing` marks a trigger that may fire even when entries are halted
  (use only for protective/exit theses). By default a trigger is entry-inducing and
  is suppressed while entries are halted.
- Other commands: `trigger list`, `trigger inspect <id>`, `trigger cancel <id>`.

## Lifecycle

- **TTL**: every trigger expires (`--ttl-days`); expired triggers stop evaluating.
- **Cadence**: `hourly` or `daily` — the minimum gap between evaluations.
- **Rate-limit**: a persistently-true trigger won't wake you every tick.
- **Auto-disable**: repeated predicate errors disable the trigger (inspect to see why).
'''


def write_ctx_schema(triggers_root: str | Path) -> Path:
    """Seed the contract doc into the triggers workspace dir (idempotent)."""
    root = Path(triggers_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "ctx-schema.md"
    path.write_text(CTX_SCHEMA_MD)
    return path
