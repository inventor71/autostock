"""Broker composition root — the single place that maps ``broker.provider`` config
to a concrete broker. Every code path that needs the account-truth broker (the daemon
executor, health checks, the agent's read-only CLI tools, equity logging, the operator
dashboard) builds it here, so they all agree on which account they read and trade.

Hard-coding a specific broker outside this factory is the F92 bug class: it silently
trades/reads the wrong account when the config names a different provider.
"""

from __future__ import annotations


def create_broker(settings):
    """Create broker based on config (alpaca | kis | account_farm | toss)."""
    if (settings.broker.name or "").lower() == "toss" and settings.broker.provider != "toss":
        raise ValueError("broker.name=toss requires broker.provider=toss; refusing an Alpaca fallback")
    if getattr(settings.broker, "provider", "") == "toss":
        if (settings.broker.name or "").lower() not in {"", "alpaca", "toss"}:
            raise ValueError("Conflicting broker.name and broker.provider for Toss")
        if settings.broker.paper:
            raise ValueError("Toss has no documented paper endpoint; broker.paper must be false")
        from src.execution.brokers.toss.broker import TossBroker
        return TossBroker(create_toss_client(settings))
    if (settings.broker.name or "").lower() == "kis":
        if not settings.broker.paper:
            raise NotImplementedError("KIS live broker not yet implemented (paper only)")
        from src.execution.brokers.kis.broker import KisPaperBroker
        return KisPaperBroker(
            settings.kis_paper_api_key, settings.kis_paper_api_secret,
            settings.kis_paper_account, paper=True,
        )
    provider = settings.broker.provider
    if provider == "account_farm":
        from src.execution.brokers.account_farm_broker import AccountFarmBroker
        return AccountFarmBroker(
            api_key=settings.broker_api_key,
            secret_key=settings.broker_api_secret,
            account_id=settings.broker_account_id,
            sandbox=True,
        )
    if provider != "alpaca":
        # Fail loud on an unknown provider — a silent fallback would trade on the
        # wrong (Alpaca) account when the config names a provider we don't know.
        raise ValueError(
            f"Unknown broker.provider {provider!r}; expected 'alpaca', 'account_farm' or 'toss'"
        )
    from src.execution.brokers.alpaca_broker import AlpacaBroker
    return AlpacaBroker(
        api_key=settings.alpaca_api_key,
        secret_key=settings.alpaca_api_secret,
        paper=settings.broker.paper,
    )


def create_toss_client(settings, *, data_only=False):
    from src.execution.brokers.toss.client import TossClient
    from src.execution.brokers.toss.credentials import load_credentials

    if not data_only and not settings.toss.read_only and settings.app.mode != "live":
        raise ValueError("Toss writes require app.mode=live and toss.read_only=false")
    return TossClient(
        load_credentials(settings.toss.credentials_file, require_account=not data_only),
        read_only=True if data_only else settings.toss.read_only,
        state_dir=settings.toss.state_dir or None,
    )
