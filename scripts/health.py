#!/usr/bin/env python
"""Autostock system health check — read-only, multi-dimensional monitoring.

    python scripts/health.py            # JSON report to stdout
    python scripts/health.py --quiet    # minimal output (just overall status line)
    python scripts/health.py --exit-code-only  # no output, exit 0/1/2/3

Exit codes: 0=OK  1=WARNING  2=ERROR  3=CRITICAL

Designed for AI-driven periodic execution (Claude runs this hourly, interprets
the JSON output, and surfaces actionable findings).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Follow the same pattern as scripts/status.py: add project root to sys.path
# so we can import from src.* and config.* regardless of cwd.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.config import get_settings  # noqa: E402
from src.monitoring.health import run_all_checks  # noqa: E402
from src.monitoring.health.report import CheckStatus  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="autostock health check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Minimal output (one summary line)",
    )
    parser.add_argument(
        "--exit-code-only", action="store_true",
        help="No output — just exit with the appropriate code",
    )
    parser.add_argument(
        "--dimension", "-d", type=str, nargs="*",
        help="Run only the named dimension(s), e.g. --dimension broker process",
    )
    args = parser.parse_args()

    # Load settings (validates config/env at parse time)
    try:
        settings = get_settings()
    except Exception as exc:
        _emit_fatal(f"Config load failed: {exc}")
        return 3

    # Run all (or selected) health checks
    t0 = time.monotonic()
    try:
        report = run_all_checks(settings)
    except Exception as exc:
        _emit_fatal(f"Health check crashed: {exc}")
        return 3

    elapsed = time.monotonic() - t0

    # Filter dimensions if requested
    if args.dimension:
        requested = set(args.dimension)
        report.dimensions = {
            k: v for k, v in report.dimensions.items() if k in requested
        }
        report.overall = CheckStatus.OK
        for dim in report.dimensions.values():
            severity_order = [
                CheckStatus.OK, CheckStatus.SKIPPED,
                CheckStatus.WARNING, CheckStatus.ERROR, CheckStatus.CRITICAL,
            ]
            if severity_order.index(dim.status) > severity_order.index(report.overall):
                report.overall = dim.status
        report.summary = f"Filtered to: {', '.join(sorted(requested))}"

    # Output
    if args.exit_code_only:
        pass
    elif args.quiet:
        status_icon = _status_icon(report.overall)
        print(
            f"{status_icon} [{report.overall.value}] {report.summary} "
            f"({report.duration_ms:.0f}ms)"
        )
    else:
        print(report.model_dump_json(indent=2))

    return report.exit_code


def _emit_fatal(msg: str) -> None:
    """Print a minimal CRITICAL report and exit."""
    print(json.dumps({
        "overall": "CRITICAL",
        "summary": msg,
        "dimensions": {},
    }))


def _status_icon(status: CheckStatus) -> str:
    icons = {
        CheckStatus.OK: "✓",
        CheckStatus.WARNING: "⚠",
        CheckStatus.ERROR: "✗",
        CheckStatus.CRITICAL: "⊘",
        CheckStatus.SKIPPED: "○",
    }
    return icons.get(status, "?")


if __name__ == "__main__":
    sys.exit(main())
