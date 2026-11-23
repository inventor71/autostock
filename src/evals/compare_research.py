"""Local, paired comparisons of the production research modes on frozen cases.

Run with ``python -m src.evals.compare_research --model opus --repeats 3``.
Results are append-only per experiment under gitignored research-comparisons/.
These are behavior/cost experiments, not return backtests or a profit estimate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import random
import statistics
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from src.agent.session import _default_runner
from src.core.jsonl import atomic_write_text
from src.evals.runner import evaluate_scenario
from src.evals.scenario import load_scenario
from src.evals.profiles import ResearchProfile, prompt_snapshot

ROOT = Path(__file__).resolve().parents[2]
MODES = ("single", "sequential", "parallel")
TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens",
              "cache_creation_input_tokens")


def _write_json(path: Path, value) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def call_totals(calls: list[dict], *, mode: str | None = None) -> dict:
    """Sum per-turn usage, but count resumed session cost only once.

    Claude CLI >=2.1.277 restores total_cost_usd across --resume. The usage
    object is per turn; hidden SDK subagents are disabled by this harness.
    Older artifacts lack session IDs: the mode contract identifies a single
    sequential session, versus independent single/parallel calls.
    """
    def known(value):
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and value >= 0)

    def known_sum(values):
        return sum(values) if values and all(known(v) for v in values) else None

    session_costs = {}
    reset_detected = False
    for i, call in enumerate(calls):
        session = (i if call.get("cost_scope") == "request" else
                   call.get("session_id") or ("sequential" if mode == "sequential" else i))
        cost = call.get("reported_cost_usd")
        prior = session_costs.get(session)
        if known(cost) and known(prior) and cost < prior - 1e-9:
            reset_detected = True  # crash/reset: cannot reconstruct the lost spend
        session_costs[session] = cost
    return {
        "calls": len(calls),
        "failed_calls": sum(bool(c.get("is_error") or c.get("returncode")) for c in calls),
        "permission_denials": sum(len(c.get("permission_denials") or []) for c in calls),
        "reported_cost_usd": None if reset_detected else known_sum(list(session_costs.values())),
        **{key: known_sum([(c.get("usage") or {}).get(key) for c in calls])
           for key in TOKEN_KEYS},
    }


def _write_index(root: Path) -> None:
    lines = [
        "# Local research comparisons", "",
        "Model calls use frozen evidence and simulated execution. This directory is gitignored.",
        "Open an experiment's summary for paired mode results; compare like scenarios and source versions.", "",
        "| Experiment | Requested model | Finished runs / planned | Errors |",
        "| --- | --- | ---: | ---: |",
    ]
    for manifest_path in sorted(root.glob("*/manifest.json"), reverse=True):
        directory = manifest_path.parent
        try:
            manifest = json.loads(manifest_path.read_text())
            with (directory / "summary.csv").open(newline="") as f:
                rows = list(csv.DictReader(f))
            runs = sum(int(r["runs"]) for r in rows)
            errors = sum(int(r["error_runs"]) for r in rows)
            planned = (len(manifest["scenario_ids"]) * manifest["repeats"] * len(manifest["modes"])
                       * len(manifest.get("profiles", [None])))
        except (OSError, ValueError, KeyError):
            continue
        model = str(manifest["model"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| [{directory.name}]({directory.name}/summary.md) | {model} | "
                     f"{runs} / {planned} | {errors} |")
    lines += ["", "Run again from the repository root:", "", "```bash",
              "python -m src.evals.compare_research --model opus --repeats 3",
              "python -m src.evals.compare_research --report research-comparisons/<experiment>",
              "```", "", "Raw responses and source snapshots stay inside each experiment.",
              "Passing behavior checks does not establish better trading returns.", ""]
    if (root / "review.md").exists():
        lines += ["[Pilot interpretation and diagnostic-run notes](review.md)", ""]
    atomic_write_text(root / "README.md", "\n".join(lines))


class MeasuredRunner:
    """Measure every CLI invocation, including analyst/review calls and errors."""

    def __init__(self, runner=None):
        self.runner = runner or _default_runner
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def observe_api(self, event: dict) -> None:
        with self._lock:
            self.calls.append(event)

    def __call__(self, cmd, *, input, cwd, timeout, env=None):
        # Make the information budget identical across modes. Safe mode excludes
        # personal hooks/plugins/memory; explicitly supply the pinned manual.
        # Only fixture-backed market commands and sandbox file tools are allowed
        # by the production permission list. No web, MCP, or hidden agent tools.
        cmd = [*cmd, "--safe-mode", "--strict-mcp-config",
               "--tools", "Bash,Read,Write,Edit,Glob,Grep",
               "--disable-slash-commands"]
        manual = Path(cwd) / "CLAUDE.md"
        if manual.exists():
            cmd += ["--append-system-prompt", manual.read_text(encoding="utf-8")]
        input = (
            "Frozen research evaluation: use only the supplied scenario and tool "
            "fixtures. External web research is unavailable. Missing fixtures "
            "mean missing evidence. Only decision turns may write actions to the "
            "sandbox journal.\n\n"
            + input
        )
        session_flag = "--resume" if "--resume" in cmd else "--session-id"
        call = {
            "prompt": input, "model": cmd[cmd.index("--model") + 1],
            "effort": cmd[cmd.index("--effort") + 1] if "--effort" in cmd else None,
            "provider": "claude_code",
            "session_id": cmd[cmd.index(session_flag) + 1] if session_flag in cmd else None,
            "cost_scope": "session_cumulative",
        }
        start = time.perf_counter()
        try:
            proc = self.runner(cmd, input=input, cwd=cwd, timeout=timeout, env=env)
            call["returncode"] = proc.returncode
            try:
                payload = json.loads(proc.stdout)
                if isinstance(payload, dict):
                    call.update({
                        "usage": payload.get("usage"),
                        "reported_cost_usd": payload.get("total_cost_usd"),
                        "resolved_models": sorted((payload.get("modelUsage") or {}).keys()),
                        "model_usage": payload.get("modelUsage"),
                        "response": payload.get("result"),
                        "is_error": payload.get("is_error", False),
                        "permission_denials": payload.get("permission_denials", []),
                    })
                else:
                    call["is_error"] = True
            except (ValueError, TypeError):
                call["is_error"] = True
            return proc
        except (Exception, KeyboardInterrupt) as exc:
            call["is_error"] = True
            call["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            call["wall_seconds"] = time.perf_counter() - start
            with self._lock:
                self.calls.append(call)

    def totals(self) -> dict:
        return call_totals(self.calls)


def summarize(experiment: Path) -> str:
    """Rebuild a readable comparison and CSV, including incomplete/error runs."""
    rows = []
    for path in sorted((experiment / "runs").glob("*.json")):
        row = json.loads(path.read_text())
        if "calls" in row:
            # Metrics are derived; rebuild them from retained raw telemetry so
            # accounting fixes do not require spending more model calls.
            row["metrics"] = call_totals(row["calls"], mode=row["mode"])
            row["cost_accounting"] = "latest_total_per_session"
            _write_json(path, row)
        rows.append(row)
    summaries = []
    groups = sorted({(r.get("profile", "default"), r["mode"]) for r in rows})
    for profile, mode in groups:
        selected = [r for r in rows if r["mode"] == mode and r.get("profile", "default") == profile]
        if not selected:
            continue
        complete = [r for r in selected if r.get("report")]
        passed = sum(
            r["report"]["tier1"]["hard"]["extraction_ok"]
            and r["report"]["tier1"]["behavior"]["matched"]
            for r in complete
        )
        def mean_known(key):
            values = [r["metrics"].get(key) for r in selected]
            return statistics.mean(values) if all(v is not None for v in values) else None
        summaries.append({
            "profile": profile,
            "mode": mode, "runs": len(selected), "completed": len(complete),
            "behavior_and_schema_passes": passed,
            "error_runs": sum(bool(r.get("error")) or not r.get("report") for r in selected),
            "failed_calls": sum(r["metrics"]["failed_calls"] for r in selected),
            "permission_denials": sum(r["metrics"].get("permission_denials", 0) for r in selected),
            "gate_issues": sum(
                outcome["status"] not in ("executed", "skipped_hold")
                for r in complete for outcome in r["report"]["tier1"]["executor_replay"]
            ),
            "median_seconds": round(statistics.median(r["wall_seconds"] for r in selected), 2),
            "mean_calls": mean_known("calls"),
            **{f"mean_{key}": mean_known(key) for key in (*TOKEN_KEYS, "reported_cost_usd")},
        })
    if summaries:
        with (experiment / "summary.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(summaries[0]))
            writer.writeheader()
            writer.writerows(summaries)
    lines = [
        "# Research comparison", "",
        "Frozen-case behavior and resource use; these results do not establish trading returns.",
        "Errors remain in the denominator. Blank telemetry means unavailable, not free.", "",
        "Cost uses each session's final CLI total; resumed turns are not double-counted.", "",
        "| Profile | Mode | Passed / runs | Errors | Failed calls | Permission denials | Gate issues | Median seconds | Mean calls |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for s in summaries:
        lines.append(
            f"| {s['profile']} | {s['mode']} | {s['behavior_and_schema_passes']} / {s['runs']} | "
            f"{s['error_runs']} | {s['failed_calls']} | {s['permission_denials']} | {s['gate_issues']} | "
            f"{s['median_seconds']} | {s['mean_calls']} |"
        )
    lines += ["", "Inspect runs/*.json for decisions, execution-gate verdicts, thesis changes,",
              "every call's prompt/response, and usage. summary.csv includes token/cache/cost means.",
              "Compare the same scenario/repeat across modes; repeat runs before changing defaults.",
              "A passing action alone does not establish good reasoning or a profitable trade.", ""]
    text = "\n".join(lines)
    (experiment / "summary.md").write_text(text, encoding="utf-8")
    _write_index(experiment.parent)
    return text


def run_comparison(
    scenarios: list[Path], *, model: str = "claude-opus-5-5", repeats: int = 1,
    modes: tuple[str, ...] = MODES, n_agents: int = 3, timeout: float = 600,
    output_root: Path = ROOT / "research-comparisons", seed: int = 0, runner=None,
    effort: str = "high", profiles: list[ResearchProfile] | None = None,
    api_client=None,
) -> Path:
    if repeats < 1 or not modes or any(mode not in MODES for mode in modes):
        raise ValueError("Choose positive repeats and valid research modes")
    if not scenarios or not 2 <= n_agents <= 5 or timeout <= 0:
        raise ValueError("Scenarios, 2–5 agents, and a positive timeout are required")
    cases = [load_scenario(p) for p in scenarios]
    from config.config import get_settings
    for case in cases:
        if case.risk is None:
            case.risk = get_settings().risk.model_copy(deep=True)
    if any(s.turn_type != "research" for s in cases):
        raise ValueError("Research comparisons require research scenarios")
    if len({s.id for s in cases}) != len(cases):
        raise ValueError("Scenario IDs must be unique")
    if profiles is None:
        profiles = [ResearchProfile(name="default", model=model, effort=effort)]
    if not profiles:
        raise ValueError("At least one profile is required")
    if len({p.name for p in profiles}) != len(profiles):
        raise ValueError("Profile names must be unique")
    snapshots = {p.name: prompt_snapshot(p.prompt_ref) for p in profiles}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    experiment = output_root / f"{stamp}-{uuid.uuid4().hex[:8]}"
    (experiment / "runs").mkdir(parents=True)
    (experiment / "scenarios").mkdir()
    source_hashes = {}
    source_paths = [ROOT / "main.py", ROOT / "pyproject.toml"]
    for directory in (ROOT / "src", ROOT / "config", ROOT / "evals"):
        source_paths.extend(p for p in directory.rglob("*")
                            if p.is_file() and p.suffix in (".py", ".txt", ".md", ".yaml", ".json")
                            and "node_modules" not in p.parts)
    with zipfile.ZipFile(experiment / "source.zip", "w", zipfile.ZIP_DEFLATED) as snapshot:
        for p in sorted(source_paths):
            relative = str(p.relative_to(ROOT))
            content = p.read_bytes()
            source_hashes[relative] = hashlib.sha256(content).hexdigest()
            snapshot.writestr(relative, content)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    patch = subprocess.run(["git", "diff", "--", "src", "config", "evals", "main.py", "pyproject.toml"],
                           cwd=ROOT, capture_output=True, text=True)
    (experiment / "source.diff").write_text(patch.stdout, encoding="utf-8")
    for index, s in enumerate(cases):
        _write_json(experiment / "scenarios" / f"{index:03d}.json", s.model_dump(mode="json"))
    manifest = {
        "started_at": stamp, "model": profiles[0].model if len(profiles) == 1 else "profile matrix", "modes": modes,
        "profiles": [p.model_dump() for p in profiles],
        "prompt_snapshots": {name: value[2] for name, value in snapshots.items()},
        "repeats": repeats, "n_agents": n_agents, "timeout_seconds": timeout,
        "seed": seed, "revision": revision.stdout.strip(), "source_sha256": source_hashes,
        "scenario_ids": [s.id for s in cases], "frozen_data": True,
        "runner": ("injected_test_runner" if runner or api_client is not None else
                   "claude_cli" if all(p.provider == "claude_code" for p in profiles) else
                   "openai_api" if all(p.provider == "openai" for p in profiles) else "mixed"),
        "cost_accounting": "latest_total_per_session; requires Claude CLI >=2.1.277",
    }
    manifest["runtime"] = {"python": sys.version.split()[0]}
    for package in ("openai", "anthropic", "pydantic"):
        try:
            manifest["runtime"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            manifest["runtime"][package] = None
    if runner is None and any(p.provider == "claude_code" for p in profiles):
        try:
            version = subprocess.run(["claude", "--version"], capture_output=True,
                                     text=True, timeout=10)
            manifest["cli_version"] = version.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            manifest["cli_version"] = None
    _write_json(experiment / "manifest.json", manifest)
    rng = random.Random(seed)
    schedule = []
    for repeat in range(repeats):
        for index in range(len(cases)):
            pairs = [(profile, mode) for profile in profiles for mode in modes]
            rng.shuffle(pairs)  # paired cases; randomize profile/mode ordering
            schedule.extend((index, repeat, profile, mode) for profile, mode in pairs)
    for run_index, (index, repeat, profile, mode) in enumerate(schedule):
        measured = MeasuredRunner(runner)
        row = {"scenario_id": cases[index].id, "repeat": repeat, "mode": mode,
               "profile": profile.name, "requested": profile.model_dump(),
               "started_at": datetime.now(timezone.utc).isoformat()}
        prompt_module, manual, _ = snapshots[profile.name]
        start = time.perf_counter()
        try:
            row["report"] = evaluate_scenario(
                cases[index], model=profile.model, timeout=timeout, runner=measured,
                research_mode=mode, n_agents=n_agents,
                effort=profile.effort, provider=profile.provider, prompt_module=prompt_module,
                manual=manual, observer=measured.observe_api, api_client=api_client,
            )
        except (Exception, KeyboardInterrupt) as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            if isinstance(exc, KeyboardInterrupt):
                raise
        finally:
            row["wall_seconds"] = time.perf_counter() - start
            row["finished_at"] = datetime.now(timezone.utc).isoformat()
            if row.get("report"):
                decisions = json.dumps(row["report"]["new_decisions"], sort_keys=True).encode()
                row["decisions_sha256"] = hashlib.sha256(decisions).hexdigest()
            row["metrics"] = measured.totals()
            row["calls"] = measured.calls
            _write_json(experiment / "runs" / f"{run_index:03d}-{profile.name}-{mode}.json", row)
            summarize(experiment)
        print(f"{run_index + 1}/{len(schedule)} {cases[index].id} {profile.name}/{mode}: "
              f"{'error' if row.get('error') else 'complete'} ({row['wall_seconds']:.1f}s)", flush=True)
    return experiment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=ROOT / "evals/scenarios/research")
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max"), default="high")
    parser.add_argument("--profiles", type=Path, help="JSON array of named model/effort/prompt profiles")
    parser.add_argument("--select", nargs="+", help="Subset of names from --profiles")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--n-agents", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--output", type=Path, default=ROOT / "research-comparisons")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--report", type=Path, help="Summarize an existing run; no model calls")
    args = parser.parse_args()
    if args.report:
        print(summarize(args.report))
        return
    paths = sorted(args.scenarios.glob("*.json")) if args.scenarios.is_dir() else [args.scenarios]
    profiles = None
    if args.profiles:
        profiles = [ResearchProfile.model_validate(p) for p in json.loads(args.profiles.read_text())]
        if args.select:
            unknown = set(args.select) - {p.name for p in profiles}
            if unknown:
                parser.error(f"Unknown profiles: {sorted(unknown)}")
            profiles = [p for p in profiles if p.name in args.select]
    elif args.select:
        parser.error("--select requires --profiles")
    result = run_comparison(paths, model=args.model, repeats=args.repeats,
                            modes=tuple(args.modes), n_agents=args.n_agents,
                            timeout=args.timeout, output_root=args.output, seed=args.seed,
                            effort=args.effort, profiles=profiles)
    print(f"Results: {result}\n{summarize(result)}")


if __name__ == "__main__":
    main()
