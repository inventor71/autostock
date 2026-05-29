"""Reusable PTY injection harness for verifying an interactive console.

Spawns a command in a real pseudo-terminal (so a TUI's raw-mode input works),
injects a scripted sequence of keystrokes with waits, and captures all output.
Pure stdlib (`pty`) — no native build needed. The SAME harness drives the stub
console (here) and, on a machine with the toolchain, the real opencode TUI
(`bun dev`) — just change `cmd`.
"""

from __future__ import annotations

import os
import pty
import select
import subprocess
import time


def drive(cmd: list[str], steps: list[tuple[str, float]], *,
          idle: float = 0.5, env: dict | None = None) -> str:
    """Run `cmd` in a PTY; for each (text, wait) step, write text then pump output
    for `wait` seconds. Returns all captured output (decoded)."""
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        cmd, stdin=slave, stdout=slave, stderr=slave,
        close_fds=True, start_new_session=True, env=env or os.environ.copy(),
    )
    os.close(slave)
    out = bytearray()

    def pump(duration: float) -> None:
        end = time.time() + duration
        while time.time() < end:
            r, _, _ = select.select([master], [], [], 0.05)
            if r:
                try:
                    data = os.read(master, 4096)
                except OSError:
                    return
                if not data:
                    return
                out.extend(data)

    pump(idle)  # startup/banner
    for text, wait in steps:
        os.write(master, text.encode())
        pump(wait)
    pump(idle)
    for fn in (lambda: proc.terminate(), lambda: os.close(master)):
        try:
            fn()
        except Exception:
            pass
    try:
        proc.wait(timeout=3)
    except Exception:
        pass
    return out.decode(errors="replace")
