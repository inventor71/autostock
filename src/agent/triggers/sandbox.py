"""SandboxRunner — run an agent-authored predicate in a one-shot Docker container (U2).

This is the **security boundary** for F88 (the AST screen is only defense-in-depth).
Every property the design promises is enforced here by `docker run` flags, not by
trusting the predicate:

* **autostock `src/` is never mounted** → the predicate cannot read or modify source.
* **`--network=none`** → no exfiltration, no live fetch (data arrives only via the
  brokered `ctx.json`).
* **no secrets in env** → the container gets a tiny fixed env; the daemon's env (and
  its API keys) are never passed with `-e`, so `os.environ` is empty of secrets.
* **`--read-only` rootfs + tmpfs `/scratch`, `--cap-drop=ALL`, non-root (65534),
  `--no-new-privileges`, `--pids-limit`, `--memory`, `--cpus`** → resource/escape bounds.
* **wall-clock timeout** (kills the container) → an infinite loop can't wedge the daemon.

Fail-closed (SECURITY-15): ANY failure — docker missing, timeout, non-zero exit,
unparseable/oversize output, predicate exception — yields `Verdict(fire=False)` with a
classified `error`, never a fire. The evaluator uses `error` to drive the
consecutive-error auto-disable counter.

The container runs a small, trusted `entry.py` (written per-run, NOT screened — it is
our code) that imports the predicate, calls `should_fire(ctx)`, and prints a strict
JSON verdict (or a structured error) to stdout.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from src.agent.triggers.models import Verdict

# Pinned base image (SECURITY-10: digest, never `latest`/floating tag). python:3.12-slim
# at pin time; override via SandboxConfig for upgrades. Manifest digest works cross-arch.
DEFAULT_IMAGE = (
    "python@sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9"
)

# Trusted in-container driver. Stdlib only (the container has no extra deps). It is OUR
# code, so it may use importlib/open — the predicate it loads is the untrusted part.
_ENTRY = r'''
import json, sys, traceback

def _emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()

try:
    with open("/run/ctx.json", "r") as f:
        ctx = json.load(f)
except Exception as e:  # ctx we wrote ourselves; treat as infra error
    _emit({"error": "ctx-load", "detail": str(e)})
    sys.exit(0)

try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("predicate", "/run/predicate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
except Exception:
    _emit({"error": "predicate-import", "detail": traceback.format_exc(limit=3)})
    sys.exit(0)

if not hasattr(mod, "should_fire"):
    _emit({"error": "no-entrypoint", "detail": "predicate defines no should_fire"})
    sys.exit(0)

try:
    out = mod.should_fire(ctx)
except Exception:
    _emit({"error": "predicate-raised", "detail": traceback.format_exc(limit=4)})
    sys.exit(0)

try:
    fire = out["fire"] if isinstance(out, dict) else None
    why = out.get("why", "") if isinstance(out, dict) else ""
    if not isinstance(fire, bool):
        _emit({"error": "bad-return", "detail": "should_fire must return {'fire': bool, 'why': str}"})
        sys.exit(0)
    _emit({"fire": fire, "why": str(why)})
except Exception:
    _emit({"error": "bad-return", "detail": traceback.format_exc(limit=2)})
'''


@dataclass(frozen=True)
class SandboxConfig:
    image: str = DEFAULT_IMAGE
    timeout_s: float = 8.0
    memory: str = "256m"
    cpus: str = "0.5"
    pids_limit: int = 64
    scratch_size: str = "16m"
    output_cap_bytes: int = 64 * 1024
    uid_gid: str = "65534:65534"  # nobody:nogroup


@dataclass(frozen=True)
class SandboxResult:
    """Outcome of one evaluation. ``verdict`` is always present (fire=False on error)."""

    verdict: Verdict
    error: str | None          # None = clean; else classified category
    detail: str = ""           # short diagnostic (predicate trace / docker stderr tail)
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None


class SandboxRunner:
    def __init__(self, config: SandboxConfig | None = None, *, docker_bin: str = "docker"):
        self.cfg = config or SandboxConfig()
        self._docker = docker_bin

    # ---- startup probe (critic#5: fail loud, never silently fail-closed) ---- #
    def preflight(self) -> tuple[bool, str]:
        """Check docker reachability at daemon startup. Returns (ok, message).

        The daemon MUST surface a not-ok result loudly — if docker is unreachable
        every evaluation would otherwise fail-closed and triggers would look 'on'
        but be dead (consecutive_errors climbing to auto-disable)."""
        try:
            p = subprocess.run(
                [self._docker, "version", "--format", "{{.Server.Version}}"],
                capture_output=True, text=True, timeout=10,
            )
        except FileNotFoundError:
            return False, f"docker binary {self._docker!r} not found on PATH"
        except subprocess.TimeoutExpired:
            return False, "docker version timed out (daemon unreachable?)"
        if p.returncode != 0:
            return False, f"docker not reachable: {p.stderr.strip() or p.stdout.strip()}"
        return True, f"docker server {p.stdout.strip()}"

    # ---- run ---------------------------------------------------------------- #
    def run(self, predicate_src: str, ctx: dict[str, Any], *, timeout_s: float | None = None) -> SandboxResult:
        timeout = timeout_s if timeout_s is not None else self.cfg.timeout_s
        start = time.monotonic()
        workdir = Path(tempfile.mkdtemp(prefix="trigger-sbx-"))
        name = "trigger-sbx-" + uuid.uuid4().hex[:12]
        try:
            self._materialize(workdir, predicate_src, ctx)
            cmd = self._docker_cmd(workdir, name)
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                self._kill(name)
                return self._fail("timeout", f"exceeded {timeout}s", start)
            except FileNotFoundError:
                return self._fail("docker-unavailable", f"{self._docker!r} not found", start)

            if p.returncode != 0:
                # Non-zero from `docker run` = container/runtime failure (OOM kill,
                # net-blocked syscall surfacing as a crash, etc.). Fail-closed.
                tail = (p.stderr or p.stdout or "").strip()[-400:]
                return self._fail("nonzero-exit", f"exit={p.returncode}: {tail}", start)

            return self._parse(p.stdout, start)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    # ---- internals ---------------------------------------------------------- #
    def _materialize(self, workdir: Path, predicate_src: str, ctx: dict[str, Any]) -> None:
        (workdir / "predicate.py").write_text(predicate_src)
        (workdir / "ctx.json").write_text(json.dumps(ctx))
        (workdir / "entry.py").write_text(_ENTRY)
        # mkdtemp is 0700; the container's non-root user must read the bind-mounted
        # files, so widen to world-readable (dir o+rx, files o+r).
        os.chmod(workdir, 0o755)
        for f in ("predicate.py", "ctx.json", "entry.py"):
            os.chmod(workdir / f, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH | stat.S_IWUSR)

    def _docker_cmd(self, workdir: Path, name: str) -> list[str]:
        return [
            self._docker, "run", "--rm", "--name", name,
            "--network=none", "--read-only",
            "--user", self.cfg.uid_gid,
            "--security-opt", "no-new-privileges",
            "--cap-drop=ALL",
            "--pids-limit", str(self.cfg.pids_limit),
            "--memory", self.cfg.memory, "--memory-swap", self.cfg.memory,
            "--cpus", self.cfg.cpus,
            "--tmpfs", f"/scratch:size={self.cfg.scratch_size},mode=1777",
            "-v", f"{workdir / 'predicate.py'}:/run/predicate.py:ro",
            "-v", f"{workdir / 'ctx.json'}:/run/ctx.json:ro",
            "-v", f"{workdir / 'entry.py'}:/run/entry.py:ro",
            "--workdir", "/run",
            "-e", "HOME=/scratch", "-e", "TMPDIR=/scratch", "-e", "PYTHONDONTWRITEBYTECODE=1",
            self.cfg.image,
            # -I isolated mode: ignore PYTHON* env + user site; -B no .pyc writes.
            "python", "-I", "-B", "/run/entry.py",
        ]

    def _kill(self, name: str) -> None:
        try:
            subprocess.run([self._docker, "kill", name], capture_output=True, timeout=10)
        except Exception as e:  # best-effort cleanup
            logger.warning("sandbox kill {} failed: {}", name, e)

    def _parse(self, stdout: str, start: float) -> SandboxResult:
        raw = stdout or ""
        if len(raw.encode("utf-8")) > self.cfg.output_cap_bytes:
            return self._fail("oversize-output", f"stdout > {self.cfg.output_cap_bytes}B", start)
        raw = raw.strip()
        if not raw:
            return self._fail("no-output", "predicate produced no verdict", start)
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return self._fail("bad-output", f"non-JSON stdout: {raw[:200]}", start)
        if isinstance(obj, dict) and "error" in obj:
            # structured error from entry.py (predicate import/raise/bad-return)
            return self._fail(str(obj.get("error")), str(obj.get("detail", ""))[:400], start)
        try:
            verdict = Verdict.model_validate(obj)
        except Exception as e:
            return self._fail("bad-output", f"verdict schema: {e}", start)
        return SandboxResult(verdict=verdict, error=None, duration_s=time.monotonic() - start)

    @staticmethod
    def _fail(category: str, detail: str, start: float) -> SandboxResult:
        # Fail-closed: never a fire on error.
        return SandboxResult(
            verdict=Verdict(fire=False, why=""),
            error=category, detail=detail, duration_s=time.monotonic() - start,
        )
