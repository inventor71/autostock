"""U2 — SandboxRunner isolation + fail-closed (the security boundary).

These tests run REAL containers, so they are skipped when docker is unreachable
(CI without docker, etc.). They are the executable proof of the F88 security
requirements: src un-mounted, network off, secrets stripped, resource-bounded,
fail-closed. A green run here is the acceptance evidence for U2.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from src.agent.triggers.sandbox import SandboxConfig, SandboxRunner


def _docker_ok() -> bool:
    try:
        p = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                           capture_output=True, timeout=10)
        return p.returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _docker_ok(), reason="docker unavailable")

# Short timeout keeps the loop/timeout test fast.
RUNNER = SandboxRunner(SandboxConfig(timeout_s=6.0))


def test_preflight_ok():
    ok, msg = RUNNER.preflight()
    assert ok, msg


def test_normal_fire_roundtrip():
    src = "def should_fire(ctx):\n    return {'fire': True, 'why': 'always'}\n"
    res = RUNNER.run(src, {})
    assert res.ok, res.detail
    assert res.verdict.fire is True
    assert res.verdict.why == "always"


def test_ctx_injection_drives_decision():
    src = (
        "def should_fire(ctx):\n"
        "    vix = ctx['macro']['vix']\n"
        "    return {'fire': vix > 25, 'why': f'vix={vix}'}\n"
    )
    fire = RUNNER.run(src, {"macro": {"vix": 30}})
    nofire = RUNNER.run(src, {"macro": {"vix": 10}})
    assert fire.ok and fire.verdict.fire is True
    assert nofire.ok and nofire.verdict.fire is False


def test_secrets_not_visible_in_container():
    # A secret in the DAEMON env must not reach the container (no -e passthrough).
    os.environ["FAKE_BROKER_SECRET"] = "sk-supersecret-DO-NOT-LEAK"
    try:
        src = (
            "import os\n"
            "def should_fire(ctx):\n"
            "    return {'fire': False, 'why': os.environ.get('FAKE_BROKER_SECRET', 'ABSENT')}\n"
        )
        res = RUNNER.run(src, {})
    finally:
        del os.environ["FAKE_BROKER_SECRET"]
    assert res.ok, res.detail
    assert res.verdict.why == "ABSENT"
    assert "supersecret" not in res.verdict.why


def test_network_is_blocked():
    src = (
        "import socket\n"
        "def should_fire(ctx):\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=3)\n"
        "    return {'fire': True, 'why': 'reached network'}\n"
    )
    res = RUNNER.run(src, {})
    # net=none → connect raises inside the predicate → fail-closed, never a fire.
    assert res.verdict.fire is False
    assert res.error == "predicate-raised"


def test_host_source_not_mounted():
    # The predicate cannot read autostock source — it isn't in the container fs.
    src = (
        "def should_fire(ctx):\n"
        "    with open('/app/src/agent/session.py') as f:\n"
        "        f.read()\n"
        "    return {'fire': True, 'why': 'read source'}\n"
    )
    res = RUNNER.run(src, {})
    assert res.verdict.fire is False
    assert res.error == "predicate-raised"


def test_infinite_loop_times_out():
    src = "def should_fire(ctx):\n    while True:\n        pass\n"
    res = RUNNER.run(src, {}, timeout_s=4.0)
    assert res.verdict.fire is False
    assert res.error == "timeout"


def test_predicate_exception_fail_closed():
    src = "def should_fire(ctx):\n    return {'fire': 1 / 0}\n"
    res = RUNNER.run(src, {})
    assert res.verdict.fire is False
    assert res.error == "predicate-raised"


def test_bad_return_shape_rejected():
    src = "def should_fire(ctx):\n    return {'fire': 'yes'}\n"
    res = RUNNER.run(src, {})
    assert res.verdict.fire is False
    assert res.error == "bad-return"


def test_non_dict_return_rejected():
    src = "def should_fire(ctx):\n    return True\n"
    res = RUNNER.run(src, {})
    assert res.verdict.fire is False
    assert res.error == "bad-return"
