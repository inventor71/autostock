"""Shared torn-safe JSONL reading + atomic file writes (C-5, BR-11).

> **Moved to `src/core/jsonl.py` (R4).** This module is now a thin re-export so the
> primitives live at the `core` layer (depended on by `surge`, the agent logs, and
> steering alike) instead of under `agent/steering/`. Existing imports
> (`from src.agent.steering.jsonl import read_complete_lines, atomic_write_text,
> ByteCursor`) keep working unchanged.

Cross-process append-only files (commands written by the operator tool, decisions
written by the agent subprocess) can be read mid-write. ``read_complete_lines`` reads
only *complete* (newline-terminated) lines and tracks a **byte-offset** cursor -- never
a parsed-list index, which drifts when malformed lines are skipped. Idempotency on
restart is the byte cursor; higher layers additionally dedup by record ``id``.
"""

from __future__ import annotations

from src.core.jsonl import ByteCursor, atomic_write_text, read_complete_lines

__all__ = ["ByteCursor", "atomic_write_text", "read_complete_lines"]
