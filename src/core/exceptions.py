class AutostockError(Exception):
    """Base exception for all autostock errors."""
    pass


class DataProviderError(AutostockError):
    """Error fetching or processing market data."""
    pass


class BrokerError(AutostockError):
    """Error communicating with or executing on broker."""
    pass


class StrategyError(AutostockError):
    """Error in strategy signal generation."""
    pass


class RiskLimitError(AutostockError):
    """Order rejected due to risk limit violation."""
    pass


class ConfigurationError(AutostockError):
    """Invalid configuration."""
    pass


class InsufficientDataError(AutostockError):
    """Not enough data to compute indicators or generate signals."""
    pass
