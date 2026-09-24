"""
Risk Manager — Position sizing, trade filtering, and emergency stop with live MT5 sync.

Key improvement over old system: sync_from_mt5() queries the real MT5 account state
on every loop iteration, so open_positions actually decrements when SL/TP is hit.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)


# ── Configuration ───────────────────────────────────────────────────────────

@dataclass
class RiskLimits:
    """Risk management limits."""
    max_positions: int = 1
    max_lot_size: float = 1.0
    min_lot_size: float = 0.01
    default_lot_size: float = 0.10

    # Daily limits
    max_daily_loss_usd: float = 500.0
    max_daily_trades: int = 5

    # Overall limits
    max_drawdown_pct: float = 15.0

    # Model confidence (extra filter beyond model threshold)
    min_probability: Optional[float] = None

    # Risk-reward
    min_risk_reward_ratio: float = 1.5


# ── Account State ───────────────────────────────────────────────────────────

@dataclass
class AccountState:
    """
    Live account state, synced from MT5.

    Unlike the old system's static mock, this is refreshed from the real
    MT5 account on every engine iteration.
    """
    login: int = 0
    balance: float = 0.0
    equity: float = 0.0
    open_positions: int = 0
    daily_pnl: float = 0.0
    daily_trades: int = 0
    starting_balance: float = 0.0

    @property
    def drawdown_pct(self) -> float:
        """Current drawdown from starting balance."""
        if self.starting_balance <= 0:
            return 0.0
        return ((self.starting_balance - self.equity) / self.starting_balance) * 100

    @property
    def daily_return_pct(self) -> float:
        """Today's return percentage."""
        if self.starting_balance <= 0:
            return 0.0
        return (self.daily_pnl / self.starting_balance) * 100


# ── Risk Manager ────────────────────────────────────────────────────────────

class RiskManager:
    """
    Risk management system with live MT5 account synchronization.

    Enforces position sizing, daily limits, drawdown caps, and R:R filters.
    Syncs with MT5 to track real position counts and account balance.
    """

    def __init__(self, limits: RiskLimits):
        self.limits = limits
        self.account = AccountState()
        self._daily_reset_date: Optional[date] = None
        self._tracked_tickets: set = set()  # Tickets we know about

        logger.info(f"RiskManager initialized: {limits}")

    def sync_from_mt5(self, mt5_bridge) -> None:
        """
        Pull real account state from MT5.

        This is the key improvement: every iteration we query the actual
        MT5 account balance, equity, and open position count. When a position
        is closed (SL/TP hit), open_positions automatically decrements.
        """
        try:
            info = mt5_bridge.get_account_info()
            positions = mt5_bridge.get_open_positions(
                magic=mt5_bridge._mt5 and None  # Get all positions for now
            )

            self.account.login = info.login
            self.account.balance = info.balance
            self.account.equity = info.equity
            self.account.open_positions = len(positions)

            # Set starting balance on first sync
            if self.account.starting_balance <= 0:
                self.account.starting_balance = info.balance

        except Exception as e:
            logger.warning(f"Failed to sync account from MT5: {e}")

    def check_trade_allowed(
        self,
        signal_probability: float,
        signal_direction: int,
        sl_price: float,
        tp_price: float,
        entry_price: float,
    ) -> Tuple[bool, str, float]:
        """
        Check if a trade is allowed and calculate position size.

        Args:
            signal_probability: Model's predicted win probability
            signal_direction: 1 for long, -1 for short
            sl_price: Stop loss price
            tp_price: Take profit price
            entry_price: Expected entry price

        Returns:
            (allowed, reason, lot_size)
        """
        # Daily counter reset
        self._check_daily_reset()

        # 1. Position limit
        if self.account.open_positions >= self.limits.max_positions:
            return False, f"Max positions reached ({self.limits.max_positions})", 0.0

        # 2. Daily trade limit
        if self.account.daily_trades >= self.limits.max_daily_trades:
            return False, f"Daily trade limit reached ({self.limits.max_daily_trades})", 0.0

        # 3. Daily loss limit
        if self.account.daily_pnl <= -self.limits.max_daily_loss_usd:
            return False, f"Daily loss limit hit (${-self.account.daily_pnl:.2f})", 0.0

        # 4. Drawdown limit
        if self.account.drawdown_pct >= self.limits.max_drawdown_pct:
            return False, f"Drawdown limit exceeded ({self.account.drawdown_pct:.1f}%)", 0.0

        # 5. Minimum probability (if set)
        if self.limits.min_probability is not None:
            if signal_probability < self.limits.min_probability:
                return False, f"Probability too low ({signal_probability:.3f} < {self.limits.min_probability:.3f})", 0.0

        # 6. Risk-reward ratio
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

        # 7. Calculate position size (fixed for now)
        lot_size = self.limits.default_lot_size
        lot_size = max(self.limits.min_lot_size, min(lot_size, self.limits.max_lot_size))

        if lot_size < self.limits.min_lot_size:
            return False, f"Position size too small ({lot_size:.3f} < {self.limits.min_lot_size})", 0.0

        return True, "All risk checks passed", lot_size

    def record_trade_opened(self):
        """Update counters when a trade is opened."""
        self.account.daily_trades += 1
        logger.info(f"Trade opened. Daily trades: {self.account.daily_trades}")

    def record_trade_closed(self, pnl: float):
        """Update PnL counters when a trade is closed."""
        self.account.daily_pnl += pnl
        logger.info(f"Trade closed. PnL: ${pnl:.2f}, Daily PnL: ${self.account.daily_pnl:.2f}")

    def _check_daily_reset(self):
        """Reset daily counters at the start of a new trading day."""
        today = datetime.now().date()
        if self._daily_reset_date != today:
            logger.info(f"Daily reset: {today}")
            self.account.daily_pnl = 0.0
            self.account.daily_trades = 0
            self._daily_reset_date = today


# ── Emergency Stop ──────────────────────────────────────────────────────────

class EmergencyStop:
    """
    Circuit breaker for catastrophic conditions.

    Monitors for consecutive losses, rapid loss spikes, and excessive
    daily drawdown. When triggered, halts all trading.
    """

    def __init__(
        self,
        max_consecutive_losses: int = 5,
        max_daily_loss_pct: float = 10.0,
        max_loss_in_minutes_usd: float = 500.0,
        max_loss_in_minutes_time: int = 60,
    ):
        self.max_consecutive_losses = max_consecutive_losses
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_loss_usd = max_loss_in_minutes_usd
        self.max_loss_minutes = max_loss_in_minutes_time

        self._consecutive_losses = 0
        self._recent_trades: List[Tuple[datetime, float]] = []

        logger.info(
            f"EmergencyStop initialized: {max_consecutive_losses} losses, "
            f"{max_daily_loss_pct}% daily, ${max_loss_in_minutes_usd} in {max_loss_in_minutes_time}min"
        )

    def check(self, account: AccountState) -> Tuple[bool, str]:
        """
        Check if emergency stop should be triggered.

        Returns:
            (should_stop, reason)
        """
        # Consecutive losses
        if self._consecutive_losses >= self.max_consecutive_losses:
            return True, f"Emergency stop: {self._consecutive_losses} consecutive losses"

        # Daily loss percentage
        if account.daily_return_pct <= -self.max_daily_loss_pct:
            return True, f"Emergency stop: daily loss {account.daily_return_pct:.1f}%"

        # Rapid loss
        cutoff_time = datetime.now() - timedelta(minutes=self.max_loss_minutes)
        recent_loss = sum(
            pnl for t, pnl in self._recent_trades
            if t >= cutoff_time and pnl < 0
        )

        if recent_loss <= -self.max_loss_usd:
            return True, f"Emergency stop: ${-recent_loss:.2f} loss in {self.max_loss_minutes} minutes"

        return False, ""

    def record_trade_result(self, pnl: float):
        """Record a trade result for emergency monitoring."""
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

        self._recent_trades.append((datetime.now(), pnl))

        # Keep only last 100 trades
        if len(self._recent_trades) > 100:
            self._recent_trades = self._recent_trades[-100:]
