from types import SimpleNamespace

from src.benchmark.settings import DEFAULT_BASELINES, BenchmarkConfig


def _settings(benchmark: dict):
    return SimpleNamespace(benchmark=benchmark)


def test_defaults_disabled():
    cfg = BenchmarkConfig.from_settings(_settings({}))
    assert cfg.enabled is False
    assert cfg.baselines == DEFAULT_BASELINES
    assert cfg.accounts == {}
    assert cfg.interval_minutes is None  # "eod"


def test_eod_interval():
    cfg = BenchmarkConfig.from_settings(_settings({"interval": "eod"}))
    assert cfg.interval_minutes is None


def test_minute_interval():
    cfg = BenchmarkConfig.from_settings(_settings({"interval": 30}))
    assert cfg.interval_minutes == 30


def test_bad_interval_falls_back_to_eod():
    cfg = BenchmarkConfig.from_settings(_settings({"interval": "nonsense"}))
    assert cfg.interval_minutes is None
    cfg2 = BenchmarkConfig.from_settings(_settings({"interval": -5}))
    assert cfg2.interval_minutes is None


def test_missing_account_warns_but_parses(caplog):
    cfg = BenchmarkConfig.from_settings(
        _settings({"enabled": True, "baselines": ["rsi", "macd"], "accounts": {"rsi": "a1"}})
    )
    assert cfg.enabled is True
    assert cfg.accounts == {"rsi": "a1"}  # macd missing — still parses (skipped at build)


def test_no_benchmark_attr():
    cfg = BenchmarkConfig.from_settings(SimpleNamespace())
    assert cfg.enabled is False
