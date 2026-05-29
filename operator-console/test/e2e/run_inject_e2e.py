#!/usr/bin/env python3
"""TUI injection e2e: drive the interactive console via a PTY, inject keystrokes,
and assert the resulting file-drop. Proves the *interactive* parse→confirm→token+
append path (BR-B1), not just the unit-tested pure functions.

Run:  python3 test/e2e/run_inject_e2e.py
Needs: bun (~/.bun/bin/bun) + python stdlib. The SAME harness will drive the real
`bun dev` opencode console on a machine with the full toolchain (change CMD).
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
CONSOLE = HERE.parents[1]  # operator-console/
sys.path.insert(0, str(HERE))
from pty_harness import drive  # noqa: E402

BUN = os.path.expanduser("~/.bun/bin/bun")
TOKEN = "e2e-token-xyz"


def main() -> int:
    steer = tempfile.mkdtemp(prefix="e2e_steer_")
    env = os.environ.copy()
    env["STEERING_OPERATOR_TOKEN"] = TOKEN
    # seed a snapshot so a read command has something to show
    pathlib.Path(steer, "snapshot.json").write_text(json.dumps({"run_state": {"paused": False}, "positions": {}}))

    steps = [
        ("/status\n", 0.5),          # read-only (no write, no confirm)
        ("/pause\n", 0.5),           # lifecycle -> confirm
        ("y\n", 0.6),                #   confirm -> write
        ("/sell AAPL 50%\n", 0.5),   # trade -> confirm
        ("y\n", 0.6),                #   confirm -> write
        ("/flatten all\n", 0.5),     # destructive -> needs CONFIRM keyword
        ("n\n", 0.5),                #   plain 'n' must NOT execute (cancelled)
        ("/buy AAPL 1000\n", 0.5),   # malformed (no unit) -> error, no write
        ("quit\n", 0.3),
    ]
    cmd = [BUN, "run", str(CONSOLE / "src" / "console-stub.ts"), steer]
    out = drive(cmd, steps, env=env)

    print("==== injected TUI session output ====")
    print(out)
    print("=====================================")

    cmds_file = pathlib.Path(steer, "commands.jsonl")
    parsed = []
    if cmds_file.exists():
        parsed = [json.loads(ln) for ln in cmds_file.read_text().splitlines() if ln.strip()]
    verbs = [c["verb"] for c in parsed]

    checks = {
        "console started (banner)": "autostock-console" in out,
        "token connected": "token:ok" in out,
        "confirm prompt shown": "confirm?" in out,
        "pause written": "pause" in verbs,
        "sell written": "sell" in verbs,
        "flatten_all NOT written (plain 'n' cancelled)": "flatten_all" not in verbs,
        "malformed /buy NOT written": all(not (c["verb"] == "buy") for c in parsed),
        "all writes confirmed+token+human": all(
            c["confirmed"] and c["token"] == TOKEN and c["source"] == "human" for c in parsed
        ),
    }
    ok = all(checks.values())
    print("commands.jsonl verbs:", verbs)
    for name, passed in checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    print("RESULT:", "PASS ✅" if ok else "FAIL ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
