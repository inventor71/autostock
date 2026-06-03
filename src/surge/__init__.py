"""Surge stock detection and history recording.

EOD scan of the trading universe for stocks that surged/dived beyond
a configurable threshold, with agent-driven root-cause analysis.
"""

from src.surge.records import SurgeAnalysis, SurgeCause, SurgeRecord
from src.surge.settings import SurgeDetectionConfig

__all__ = ["SurgeRecord", "SurgeAnalysis", "SurgeCause", "SurgeDetectionConfig"]
