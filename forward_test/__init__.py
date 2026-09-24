"""
Forward Test System for ICC Meta-Labeling Model.

Connects to MT5, loads the trained model, and executes trades
for forward-testing the model's real-world performance.
"""

__version__ = "1.0.0"

from .mt5_bridge import MT5Bridge
from .risk_manager import RiskManager, EmergencyStop
from .trade_journal import TradeJournal
from .engine import ForwardTestEngine
