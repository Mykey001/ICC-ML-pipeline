"""
Configuration classes for symbol specifications, strategy parameters, and execution settings.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class SymbolSpec:
    """
    Broker-specific symbol specification.
    
    Critical: Get these exact values from YOUR broker for YOUR symbol.
    Defaults are placeholders and will produce incorrect results.
    """
    name: str
    digits: int  # Symbol specification -> Digits
    point: float  # Symbol specification -> Point
    contract_size: float  # Symbol specification -> Contract size
    typical_spread_points: float  # Observed from Market Watch
    commission_per_lot_roundturn: float  # From broker terms (NOT in screenshots!)
    
    @property
    def pip(self) -> float:
        """
        Pip size using MT5 convention:
        - 3/5-digit quotes: pip = 10 × point
        - 2/4-digit quotes: pip = 1 × point
        """
        if self.digits in (3, 5):
            return 10.0 * self.point
        else:
            return 1.0 * self.point
    
    def pips_to_price(self, pips: float) -> float:
        """Convert pip distance to price distance."""
        return pips * self.pip
    
    def price_to_pips(self, price_distance: float) -> float:
        """Convert price distance to pips."""
        return price_distance / self.pip
    
    def pips_to_money(self, pips: float, lots: float) -> float:
        """
        Convert pip P&L to money P&L.
        
        For most symbols: money = pips × pip × contract_size × lots
        Special handling for index CFDs may be needed.
        """
        return pips * self.pip * self.contract_size * lots


# Preset symbol specifications
SYMBOL_PRESETS = {
    "XAUUSDm": SymbolSpec(
        name="XAUUSDm",
        digits=3,
        point=0.001,
        contract_size=100.0,
        typical_spread_points=30.0,
        commission_per_lot_roundturn=0.0,  # ⚠️ MUST SET from broker
    ),
    "XAUUSD": SymbolSpec(
        name="XAUUSD",
        digits=2,
        point=0.01,
        contract_size=100.0,
        typical_spread_points=30.0,
        commission_per_lot_roundturn=0.0,
    ),
    "EURUSD": SymbolSpec(
        name="EURUSD",
        digits=5,
        point=0.00001,
        contract_size=100000.0,
        typical_spread_points=15.0,
        commission_per_lot_roundturn=0.0,
    ),
    "GBPUSD": SymbolSpec(
        name="GBPUSD",
        digits=5,
        point=0.00001,
        contract_size=100000.0,
        typical_spread_points=20.0,
        commission_per_lot_roundturn=0.0,
    ),
    "US30": SymbolSpec(
        name="US30",
        digits=2,
        point=0.01,
        contract_size=1.0,
        typical_spread_points=40.0,
        commission_per_lot_roundturn=0.0,
    ),
}


@dataclass
class StrategyConfig:
    """
    ICC strategy parameters.
    
    Defaults match ICC_Swing_EA_Simplified.mq5 inputs.
    """
    # Pivot detection
    htf_pivot_len: int = 2  # HTF_PivotLen
    ltf_pivot_len: int = 1  # LTF_PivotLen
    
    # Trade management
    tp_pips: float = 2500.0  # TP_Pips
    use_custom_swing_sl: bool = True  # UseCustomSwingSL
    sl_swing_timeframe: str = "4h"  # SL_SwingTimeframe
    sl_swing_pivot_len: int = 2  # SL_SwingPivotLen
    sl_max_candidates: int = 20  # SL_MaxCandidates
    sl_buffer_pips: float = 0.0  # SL_BufferPips
    require_custom_swing_sl: bool = False  # RequireCustomSwingSL
    one_position_at_a_time: bool = True  # OnePositionAtATime
    fixed_lots: float = 0.10  # FixedLots
    
    # Timeout for stuck trades
    max_hold_bars: int = 2000  # Prevents infinite hangs in labeling


@dataclass
class ExecutionConfig:
    """
    Execution realism parameters for trade simulation.
    
    These assumptions exist to prevent the backtest from flattering itself.
    """
    slippage_points: float = 5.0  # Adverse slippage on entry & exit
    both_hit_same_bar_policy: Literal["sl_first", "tp_first"] = "sl_first"  # Pessimistic default
    apply_commission: bool = True
    
    def __post_init__(self):
        if self.both_hit_same_bar_policy == "tp_first":
            import warnings
            warnings.warn(
                "both_hit_same_bar_policy='tp_first' inflates results. "
                "Use 'sl_first' for honest simulation.",
                UserWarning
            )
