"""Trigger subsystem configuration from settings.yaml ``triggers:`` block (F88).

Shipped OFF (``enabled: false``) — set ``enabled: true`` to let the daemon run the
TriggerEvaluator. All knobs have safe defaults so an empty block is valid.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TriggersConfig(BaseModel):
    enabled: bool = False
    # how often the evaluator wakes to check due-ness (cheap; only DUE triggers run
    # the sandbox). Independent of per-trigger cadence (hourly/daily).
    tick_seconds: int = Field(default=300, ge=30)
    # lifecycle / runaway guards (FR-9)
    max_consecutive_errors: int = Field(default=5, ge=1)
    min_fire_gap_s: float = Field(default=6 * 3600, ge=0.0)
    wake_timeout: float = Field(default=120.0, gt=0.0)
    # sandbox (U2)
    sandbox_image: str = (
        "python@sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9"
    )
    sandbox_timeout_s: float = Field(default=8.0, gt=0.0)
    sandbox_memory: str = "256m"
    sandbox_cpus: str = "0.5"
    # webfetch (U3) — domains the daemon may GET on a trigger's behalf (SSRF guard).
    webfetch_allowlist: list[str] = Field(default_factory=list)

    @classmethod
    def from_settings(cls, triggers_block: dict | None) -> "TriggersConfig":
        return cls(**(triggers_block or {}))
