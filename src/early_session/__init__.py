"""Early-session signal detection — monitor extreme moves during the first hour.

See ``aidlc-docs/tracks/F51/`` for design docs.
"""

from src.early_session.settings import EarlySessionConfig
from src.early_session.monitor import EarlySessionMonitor

__all__ = ["EarlySessionConfig", "EarlySessionMonitor"]
