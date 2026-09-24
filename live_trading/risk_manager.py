"""
Risk management and position sizing for live trading.

Controls:
- Position sizing
- Maximum positions
- Daily loss limits
- Drawdown limits
- Probability thresholds
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Optional
import logging


logger = logging.getLogger(__name__)


@dataclass
class RiskLimits:
    """Risk management limits."""
    
    # Position limits
    max_positions: int = 1
    max_lot_size: float = 1.0
    min_lot_size: float = 0.01
    default_lot_size: float = 0.10
    
    # Daily limits
    max_daily_loss_usd: float = 1000.0
    max_daily_trades: int = 5
    
    # Overall limits
    max_drawdown_pct: float = 20.0  # % of starting balance
    
    # Model confidence
    min_probability: Optional[float] = None  # Extra safety filter (beyond model threshold)
    
    # Risk-reward
    min_risk_reward_ratio: float = 1.5


@dataclass
class AccountState:
    """Current account state."""
    balance: float
    equity: float
    open_positions: int
    daily_pnl: float
    daily_trades: int
    trades_since_reset: int = 0
    starting_balance: float = 0.0
    
    def __post_init__(self):
        if self.starting_balance == 0.0:
            self.starting_balance = self.balance
    
    @property
    def drawdown_pct(self) -> float:
        """Current drawdown from starting balance."""
        return ((self.starting_balance - self.equity) / self.starting_balance) * 100
    
    @property
    def daily_return_pct(self) -> float:
        """Today's return percentage."""
        return (self.daily_pnl / self.starting_balance) * 100


class RiskManager:
    """
    Risk management system for live trading.
    
    Enforces position sizing, daily limits, and risk controls.
    """
    
    def __init__(self, limits: RiskLimits):
        """
        Initialize risk manager.
        
        Args:
            limits: Risk management limits
        """
        self.limits = limits
        self._daily_reset_date: Optional[date] = None
        
        logger.info(f"RiskManager initialized with limits: {limits}")
    
    def check_trade_allowed(
        self,
        account: AccountState,
        signal_probability: float,
        signal_direction: int,
        sl_price: float,
        tp_price: float,
        entry_price: float,
    ) -> tuple[bool, str, float]:
        """
        Check if trade is allowed and calculate position size.
        
        Args:
            account: Current account state
            signal_probability: Model's predicted win probability
            signal_direction: 1 for long, -1 for short
            sl_price: Stop loss price
            tp_price: Take profit price
            entry_price: Expected entry price
        
        Returns:
            (allowed, reason, lot_size)
            - allowed: True if trade should be taken
            - reason: Explanation (for logging)
            - lot_size: Calculated position size (0 if not allowed)
        """
        # Reset daily counters if needed
        self._check_daily_reset(account)
        
        # Check position limit
        if account.open_positions >= self.limits.max_positions:
            return False, f"Max positions reached ({self.limits.max_positions})", 0.0
        
        # Check daily trade limit
        if account.daily_trades >= self.limits.max_daily_trades:
            return False, f"Daily trade limit reached ({self.limits.max_daily_trades})", 0.0
        
        # Check daily loss limit
        if account.daily_pnl <= -self.limits.max_daily_loss_usd:
            return False, f"Daily loss limit hit (${-account.daily_pnl:.2f})", 0.0
        
        # Check drawdown limit
        if account.drawdown_pct >= self.limits.max_drawdown_pct:
            return False, f"Drawdown limit exceeded ({account.drawdown_pct:.1f}%)", 0.0
        
        # Check minimum probability (if set)
        if self.limits.min_probability is not None:
            if signal_probability < self.limits.min_probability:
                return False, f"Probability too low ({signal_probability:.3f} < {self.limits.min_probability:.3f})", 0.0
        
        # Check risk-reward ratio
        if signal_direction == 1:  # Long
            risk = entry_price - sl_price
            reward = tp_price - entry_price
        else:  # Short
            risk = sl_price - entry_price
            reward = entry_price - tp_price
        
        if risk <= 0:
            return False, "Invalid stop loss (no risk)", 0.0
        
        rr_ratio = reward / risk if risk > 0 else 0
        
        if rr_ratio < self.limits.min_risk_reward_ratio:
            return False, f"Risk-reward too low ({rr_ratio:.2f} < {self.limits.min_risk_reward_ratio:.2f})", 0.0
        
        # Calculate position size
        lot_size = self._calculate_position_size(
            account=account,
            risk_price=abs(entry_price - sl_price),
            probability=signal_probability,
        )
        
        if lot_size < self.limits.min_lot_size:
            return False, f"Position size too small ({lot_size:.3f} < {self.limits.min_lot_size})", 0.0
        
        # All checks passed
        return True, "All risk checks passed", lot_size
    
    def _calculate_position_size(
        self,
        account: AccountState,
        risk_price: float,
        probability: float,
    ) -> float:
        """
        Calculate position size based on risk parameters.
        
        Simple fixed lot sizing by default. Override for more sophisticated
        position sizing (e.g., Kelly criterion, volatility-based).
        
        Args:
            account: Account state
            risk_price: Price distance to stop loss
            probability: Model probability
        
        Returns:
            Lot size
        """
        # For now, use fixed lot size
        # TODO: Implement dynamic sizing based on probability or volatility
        lot_size = self.limits.default_lot_size
        
        # Clamp to limits
        lot_size = max(self.limits.min_lot_size, min(lot_size, self.limits.max_lot_size))
        
        return lot_size
    
    def _check_daily_reset(self, account: AccountState):
        """Reset daily counters at start of new day."""
        today = datetime.now().date()
        
        if self._daily_reset_date != today:
            logger.info(f"Daily reset: {today}")
            account.daily_pnl = 0.0
            account.daily_trades = 0
            self._daily_reset_date = today
    
    def record_trade_opened(self, account: AccountState):
        """Update counters when trade is opened."""
        account.open_positions += 1
        account.daily_trades += 1
        account.trades_since_reset += 1
    
    def record_trade_closed(self, account: AccountState, pnl: float):
        """Update counters and PnL when trade is closed."""
        account.open_positions -= 1
        account.daily_pnl += pnl
        account.equity = account.balance + pnl  # Simplified


class EmergencyStop:
    """
    Emergency stop mechanism.
    
    Monitors for catastrophic conditions and triggers emergency shutdown.
    """
    
    def __init__(
        self,
        max_consecutive_losses: int = 5,
        max_daily_loss_pct: float = 10.0,
        max_loss_in_minutes: tuple[float, int] = (500.0, 60),  # ($500 in 60 min)
    ):
        """
        Initialize emergency stop.
        
        Args:
            max_consecutive_losses: Stop after N consecutive losses
            max_daily_loss_pct: Stop if daily loss exceeds X%
            max_loss_in_minutes: Stop if loss of $X in Y minutes
        """
        self.max_consecutive_losses = max_consecutive_losses
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_loss_in_minutes = max_loss_in_minutes
        
        self._consecutive_losses = 0
        self._recent_trades: list[tuple[datetime, float]] = []  # (time, pnl)
        
        logger.info(f"EmergencyStop initialized: {max_consecutive_losses} losses, {max_daily_loss_pct}% daily")
    
    def check(self, account: AccountState) -> tuple[bool, str]:
        """
        Check if emergency stop should be triggered.
        
        Returns:
            (should_stop, reason)
        """
        # Check consecutive losses
        if self._consecutive_losses >= self.max_consecutive_losses:
            return True, f"Emergency stop: {self._consecutive_losses} consecutive losses"
        
        # Check daily loss percentage
        if account.daily_return_pct <= -self.max_daily_loss_pct:
            return True, f"Emergency stop: daily loss {account.daily_return_pct:.1f}%"
        
        # Check rapid loss
        max_loss, minutes = self.max_loss_in_minutes
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        recent_loss = sum(
            pnl for time, pnl in self._recent_trades
            if time >= cutoff_time and pnl < 0
        )
        
        if recent_loss <= -max_loss:
            return True, f"Emergency stop: ${-recent_loss:.2f} loss in {minutes} minutes"
        
        return False, ""
    
    def record_trade_result(self, pnl: float):
        """Record trade result for emergency monitoring."""
        # Update consecutive losses
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
        
        # Record recent trade
        self._recent_trades.append((datetime.now(), pnl))
        
        # Keep only last 100 trades
        if len(self._recent_trades) > 100:
            self._recent_trades = self._recent_trades[-100:]
