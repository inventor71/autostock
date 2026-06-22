"""U3 — BrokeredFetcher: ctx assembly, allow-list, fail-honest (with fakes)."""

from __future__ import annotations

import pytest

from src.agent.triggers.fetch import BrokeredFetcher
from src.agent.triggers.models import SourceRef


def test_signal_source_mapped_to_ctx():
    def resolver(name, params):
        return {"vix": 30} if name == "macro" else None

    f = BrokeredFetcher(signal_resolver=resolver)
    ctx = f.build_ctx([SourceRef(kind="signal", name="macro")])
    assert ctx["macro"] == {"vix": 30}
    assert ctx["_meta"]["sources"] == ["macro"]


def test_signal_params_passed_through():
    seen = {}

    def resolver(name, params):
        seen.update(params)
        return "ok"

    f = BrokeredFetcher(signal_resolver=resolver)
    f.build_ctx([SourceRef(kind="signal", name="movers", params={"top": 5})])
    assert seen == {"top": 5}


def test_signal_resolver_error_is_fail_honest():
    def resolver(name, params):
        raise RuntimeError("provider down")

    f = BrokeredFetcher(signal_resolver=resolver)
    ctx = f.build_ctx([SourceRef(kind="signal", name="macro")])
    assert ctx["macro"]["_error"] == "provider down"  # surfaced, not crashed


def test_missing_signal_resolver_surfaced():
    f = BrokeredFetcher()
    ctx = f.build_ctx([SourceRef(kind="signal", name="macro")])
    assert "_error" in ctx["macro"]


def test_webfetch_allowlisted_host():
    def http_get(url):
        return 200, "PAYLOAD"

    f = BrokeredFetcher(http_get=http_get, webfetch_allowlist=frozenset({"stlouisfed.org"}))
    ctx = f.build_ctx([SourceRef(kind="webfetch", url="https://fred.stlouisfed.org/x")])
    key = next(k for k in ctx if k.startswith("fetch_"))
    assert ctx[key]["status"] == 200
    assert ctx[key]["body"] == "PAYLOAD"
    assert ctx[key]["host"] == "fred.stlouisfed.org"


def test_webfetch_domain_not_allowlisted_blocked():
    def http_get(url):
        raise AssertionError("must not be called for non-allowlisted host")

    f = BrokeredFetcher(http_get=http_get, webfetch_allowlist=frozenset({"stlouisfed.org"}))
    ctx = f.build_ctx([SourceRef(kind="webfetch", url="https://evil.example.com/x")])
    key = next(k for k in ctx if k.startswith("fetch_"))
    assert "not allow-listed" in ctx[key]["_error"]


def test_webfetch_body_capped():
    def http_get(url):
        return 200, "z" * 100_000

    f = BrokeredFetcher(http_get=http_get, webfetch_allowlist=frozenset({"x.com"}))
    ctx = f.build_ctx([SourceRef(kind="webfetch", url="https://x.com/big")])
    key = next(k for k in ctx if k.startswith("fetch_"))
    assert len(ctx[key]["body"]) <= 32 * 1024


def test_webfetch_http_error_fail_honest():
    def http_get(url):
        raise ConnectionError("timeout")

    f = BrokeredFetcher(http_get=http_get, webfetch_allowlist=frozenset({"x.com"}))
    ctx = f.build_ctx([SourceRef(kind="webfetch", url="https://x.com/y")])
    key = next(k for k in ctx if k.startswith("fetch_"))
    assert ctx[key]["_error"] == "timeout"


def test_one_source_failure_does_not_sink_others():
    def resolver(name, params):
        if name == "macro":
            raise RuntimeError("down")
        return {"ok": True}

    f = BrokeredFetcher(signal_resolver=resolver)
    ctx = f.build_ctx([
        SourceRef(kind="signal", name="macro"),
        SourceRef(kind="signal", name="movers"),
    ])
    assert "_error" in ctx["macro"]
    assert ctx["movers"] == {"ok": True}


def test_subdomain_allowlist_match():
    def http_get(url):
        return 200, "ok"

    f = BrokeredFetcher(http_get=http_get, webfetch_allowlist=frozenset({"example.com"}))
    ctx = f.build_ctx([SourceRef(kind="webfetch", url="https://api.data.example.com/z")])
    key = next(k for k in ctx if k.startswith("fetch_"))
    assert ctx[key].get("status") == 200
