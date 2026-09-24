"""
Performance monitoring and alerting system.

Tracks:
- Win rate vs expectation
- Model probability distribution
- Feature drift
- Trade frequency
- P&L metrics
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
import numpy as np
import json
from pathlib import Path
import logging


logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """Single trade record for monitoring."""
    timestamp: datetime
    signal_bar: int
    direction: int  # 1=long, -1=short
    probability: float
    decision: str  # TAKE or SKIP
    executed: bool
    lot_size: float
    entry_price: Optional[float] = None
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    pnl: Optional[float] = None
    blocked: bool = False
    block_reason: Optional[str] = None


@dataclass
class MonitoringStats:
    """Aggregated monitoring statistics."""
    
    # Time window
    start_time: datetime
    end_time: datetime
    
    # Signal counts
    total_signals: int = 0
    signals_taken: int = 0
    signals_skipped: int = 0
    signals_blocked: int = 0
    
    # Execution
    trades_opened: int = 0
    trades_closed: int = 0
    
    # Performance (closed trades only)
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_win_pnl: float = 0.0
    avg_loss_pnl: float = 0.0
    total_pnl: float = 0.0
    
    # Model statistics
    avg_probability_taken: float = 0.0
    avg_probability_skipped: float = 0.0
    probability_distribution: dict = field(default_factory=dict)
    
    # Drift indicators
    signals_per_day: float = 0.0
    
    def compute_metrics(self, trades: list[TradeRecord]):
        """Compute statistics from trade records."""
        if not trades:
            return
        
        self.total_signals = len(trades)
        self.signals_taken = sum(1 for t in trades if t.decision == "TAKE")
        self.signals_skipped = sum(1 for t in trades if t.decision == "SKIP")
        self.signals_blocked = sum(1 for t in trades if t.blocked)
        self.trades_opened = sum(1 for t in trades if t.executed)
        
        # Closed trades only
        closed_trades = [t for t in trades if t.pnl is not None]
        self.trades_closed = len(closed_trades)
        
        if closed_trades:
            self.wins = sum(1 for t in closed_trades if t.pnl > 0)
            self.losses = sum(1 for t in closed_trades if t.pnl <= 0)
            self.win_rate = self.wins / len(closed_trades)
            
            winning_trades = [t.pnl for t in closed_trades if t.pnl > 0]
            losing_trades = [t.pnl for t in closed_trades if t.pnl <= 0]
            
            self.avg_win_pnl = np.mean(winning_trades) if winning_trades else 0.0
            self.avg_loss_pnl = np.mean(losing_trades) if losing_trades else 0.0
            self.total_pnl = sum(t.pnl for t in closed_trades)
        
        # Model probabilities
        taken = [t.probability for t in trades if t.decision == "TAKE"]
        skipped = [t.probability for t in trades if t.decision == "SKIP"]
        
        self.avg_probability_taken = np.mean(taken) if taken else 0.0
        self.avg_probability_skipped = np.mean(skipped) if skipped else 0.0
        
        # Probability distribution (binned)
        all_probs = [t.probability for t in trades]
        hist, bins = np.histogram(all_probs, bins=[0, 0.4, 0.5, 0.6, 0.7, 1.0])
        self.probability_distribution = {
            f"{bins[i]:.1f}-{bins[i+1]:.1f}": int(hist[i])
            for i in range(len(hist))
        }
        
        # Signal frequency
        time_span = (self.end_time - self.start_time).total_seconds() / 86400  # days
        self.signals_per_day = self.total_signals / time_span if time_span > 0 else 0


class PerformanceMonitor:
    """
    Real-time performance monitoring and alerting.
    
    Tracks model performance and detects drift/issues.
    """
    
    def __init__(
        self,
        log_dir: str = "live_trading/logs",
        alert_callback: Optional[callable] = None,
    ):
        """
        Initialize performance monitor.
        
        Args:
            log_dir: Directory to store monitoring logs
            alert_callback: Function to call for alerts (e.g., send email/SMS)
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.alert_callback = alert_callback
        
        # Trade history
        self.trades: list[TradeRecord] = []
        
        # Session start
        self.session_start = datetime.now()
        
        logger.info(f"PerformanceMonitor initialized, logs in: {self.log_dir}")
    
    def record_signal(self, decision: dict):
        """
        Record a signal decision.
        
        Args:
            decision: Decision dict from TradingEngine
        """
        record = TradeRecord(
            timestamp=datetime.now(),
            signal_bar=decision["signal_bar"],
            direction=decision["direction"],
            probability=decision["probability"],
            decision=decision["decision"],
            executed=decision.get("executed", False),
            lot_size=decision.get("lot_size", 0.0),
            sl_price=decision.get("sl_price"),
            tp_price=decision.get("tp_price"),
            blocked=decision.get("blocked", False),
            block_reason=decision.get("block_reason"),
        )
        
        self.trades.append(record)
        
        # Save to CSV
        self._save_trade_log(record)
    
    def record_trade_close(
        self,
        signal_bar: int,
        exit_price: float,
        pnl: float,
    ):
        """
        Update trade record when position closes.
        
        Args:
            signal_bar: Signal bar that opened the trade
            exit_price: Exit price
            pnl: Profit/loss in account currency
        """
        # Find matching trade
        for trade in reversed(self.trades):
            if trade.signal_bar == signal_bar and trade.pnl is None:
                trade.exit_price = exit_price
                trade.exit_time = datetime.now()
                trade.pnl = pnl
                
                logger.info(
                    f"Trade closed: bar={signal_bar}, "
                    f"pnl=${pnl:.2f}, "
                    f"win={pnl > 0}"
                )
                
                # Update log
                self._save_trade_log(trade)
                
                # Check for alerts
                self._check_performance_alerts()
                break
    
    def get_stats(
        self,
        window_hours: Optional[int] = None
    ) -> MonitoringStats:
        """
        Get monitoring statistics.
        
        Args:
            window_hours: Only include trades from last N hours (None = all)
        
        Returns:
            MonitoringStats object
        """
        if window_hours is not None:
            cutoff = datetime.now() - timedelta(hours=window_hours)
            trades = [t for t in self.trades if t.timestamp >= cutoff]
            start_time = cutoff
        else:
            trades = self.trades
            start_time = self.session_start
        
        stats = MonitoringStats(
            start_time=start_time,
            end_time=datetime.now(),
        )
        
        stats.compute_metrics(trades)
        
        return stats
    
    def print_stats(self, window_hours: Optional[int] = None):
        """Print monitoring statistics to console."""
        stats = self.get_stats(window_hours)
        
        print("\n" + "=" * 80)
        print("PERFORMANCE MONITORING REPORT")
        print("=" * 80)
        
        time_window = f"Last {window_hours}h" if window_hours else "All time"
        print(f"Period: {time_window} ({stats.start_time} to {stats.end_time})")
        
        print(f"\n--- SIGNALS ---")
        print(f"Total signals: {stats.total_signals}")
        print(f"  Taken:   {stats.signals_taken} ({stats.signals_taken/max(stats.total_signals,1)*100:.1f}%)")
        print(f"  Skipped: {stats.signals_skipped} ({stats.signals_skipped/max(stats.total_signals,1)*100:.1f}%)")
        print(f"  Blocked: {stats.signals_blocked} ({stats.signals_blocked/max(stats.total_signals,1)*100:.1f}%)")
        print(f"Signal frequency: {stats.signals_per_day:.2f} per day")
        
        print(f"\n--- EXECUTION ---")
        print(f"Trades opened: {stats.trades_opened}")
        print(f"Trades closed: {stats.trades_closed}")
        
        if stats.trades_closed > 0:
            print(f"\n--- PERFORMANCE ---")
            print(f"Win rate: {stats.win_rate*100:.1f}% ({stats.wins}W / {stats.losses}L)")
            print(f"Total P&L: ${stats.total_pnl:.2f}")
            print(f"Avg win:  ${stats.avg_win_pnl:.2f}")
            print(f"Avg loss: ${stats.avg_loss_pnl:.2f}")
            
            if stats.avg_loss_pnl != 0:
                profit_factor = -stats.avg_win_pnl / stats.avg_loss_pnl
                print(f"Profit factor: {profit_factor:.2f}")
        
        print(f"\n--- MODEL PROBABILITIES ---")
        print(f"Avg probability (taken):  {stats.avg_probability_taken:.3f}")
        print(f"Avg probability (skipped): {stats.avg_probability_skipped:.3f}")
        print(f"Distribution: {stats.probability_distribution}")
        
        print("=" * 80 + "\n")
    
    def _save_trade_log(self, record: TradeRecord):
        """Save trade record to CSV log."""
        log_file = self.log_dir / f"trades_{datetime.now().strftime('%Y%m%d')}.csv"
        
        # Convert to dict
        record_dict = {
            "timestamp": record.timestamp.isoformat(),
            "signal_bar": record.signal_bar,
            "direction": record.direction,
            "probability": record.probability,
            "decision": record.decision,
            "executed": record.executed,
            "lot_size": record.lot_size,
            "entry_price": record.entry_price,
            "sl_price": record.sl_price,
            "tp_price": record.tp_price,
            "exit_price": record.exit_price,
            "exit_time": record.exit_time.isoformat() if record.exit_time else None,
            "pnl": record.pnl,
            "blocked": record.blocked,
            "block_reason": record.block_reason,
        }
        
        df = pd.DataFrame([record_dict])
        
        # Append to CSV
        if log_file.exists():
            df.to_csv(log_file, mode="a", header=False, index=False)
        else:
            df.to_csv(log_file, index=False)
    
    def _check_performance_alerts(self):
        """Check for performance issues and send alerts."""
        # Get recent stats (last 24 hours)
        stats = self.get_stats(window_hours=24)
        
        alerts = []
        
        # Check win rate (if enough trades)
        if stats.trades_closed >= 10:
            if stats.win_rate < 0.30:  # Below 30%
                alerts.append(f"LOW WIN RATE: {stats.win_rate*100:.1f}% (last 24h, {stats.trades_closed} trades)")
        
        # Check daily P&L
        if stats.total_pnl < -500:  # Lost more than $500
            alerts.append(f"LARGE DAILY LOSS: ${stats.total_pnl:.2f} (last 24h)")
        
        # Check probability distribution shift
        if stats.total_signals >= 20:
            if stats.avg_probability_taken < 0.55:
                alerts.append(
                    f"LOW MODEL CONFIDENCE: avg probability {stats.avg_probability_taken:.3f} "
                    f"(threshold: {0.52})"
                )
        
        # Send alerts
        for alert in alerts:
            logger.warning(f"ALERT: {alert}")
            if self.alert_callback:
                try:
                    self.alert_callback(alert)
                except Exception as e:
                    logger.error(f"Alert callback failed: {e}")
    
    def export_report(self, filename: Optional[str] = None):
        """Export detailed monitoring report to JSON."""
        if filename is None:
            filename = f"monitor_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        report_path = self.log_dir / filename
        
        stats = self.get_stats()
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "session_start": self.session_start.isoformat(),
            "statistics": {
                "total_signals": stats.total_signals,
                "signals_taken": stats.signals_taken,
                "signals_skipped": stats.signals_skipped,
                "signals_blocked": stats.signals_blocked,
                "trades_opened": stats.trades_opened,
                "trades_closed": stats.trades_closed,
                "win_rate": stats.win_rate,
                "total_pnl": stats.total_pnl,
                "avg_probability_taken": stats.avg_probability_taken,
                "avg_probability_skipped": stats.avg_probability_skipped,
                "probability_distribution": stats.probability_distribution,
            },
            "trades": [
                {
                    "timestamp": t.timestamp.isoformat(),
                    "signal_bar": t.signal_bar,
                    "direction": t.direction,
                    "probability": t.probability,
                    "decision": t.decision,
                    "pnl": t.pnl,
                }
                for t in self.trades
            ],
        }
        
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Monitoring report exported to: {report_path}")
        return report_path
