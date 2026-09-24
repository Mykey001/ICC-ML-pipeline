"""
Trade Journal — Records every signal, decision, and trade outcome to CSV for
forward-test analysis of the model's real-world performance.

Outputs:
  - logs/journal/signals_YYYYMMDD.csv  — Every model decision (TAKE/SKIP/BLOCKED)
  - logs/journal/trades_YYYYMMDD.csv   — Opened and closed trade records
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


# ── Record Types ────────────────────────────────────────────────────────────

@dataclass
class SignalRecord:
    """A single model decision (logged for every ICC signal detected)."""
    timestamp: str
    bar_index: int
    direction: int          # 1=LONG, -1=SHORT
    direction_str: str      # "LONG" or "SHORT"
    entry_price: float
    sl_price: float
    tp_price: float
    probability: float
    threshold: float
    decision: str           # "TAKE", "SKIP", or "BLOCKED"
    block_reason: str = ""
    lot_size: float = 0.0
    executed: bool = False
    ticket: int = 0
    risk_reward: float = 0.0


@dataclass
class TradeRecord:
    """A trade that was opened (and eventually closed)."""
    open_timestamp: str
    ticket: int
    direction: int
    direction_str: str
    entry_price: float
    sl_price: float
    tp_price: float
    lot_size: float
    probability: float
    # Filled on close
    close_timestamp: str = ""
    exit_price: float = 0.0
    pnl_usd: float = 0.0
    exit_reason: str = ""    # "SL", "TP", "MANUAL", "TIMEOUT"
    duration_bars: int = 0
    is_closed: bool = False


# ── Trade Journal ───────────────────────────────────────────────────────────

class TradeJournal:
    """
    Records all signals, decisions, and trade outcomes for forward-test analysis.

    Writes to CSV files daily. Provides summary statistics for model evaluation.
    """

    SIGNAL_HEADERS = [
        "timestamp", "bar_index", "direction", "direction_str",
        "entry_price", "sl_price", "tp_price",
        "probability", "threshold", "decision",
        "block_reason", "lot_size", "executed", "ticket", "risk_reward",
    ]

    TRADE_HEADERS = [
        "open_timestamp", "ticket", "direction", "direction_str",
        "entry_price", "sl_price", "tp_price", "lot_size", "probability",
        "close_timestamp", "exit_price", "pnl_usd",
        "exit_reason", "duration_bars", "is_closed",
    ]

    def __init__(self, journal_dir: str = "forward_test/logs/journal"):
        """
        Initialize trade journal.

        Args:
            journal_dir: Directory for CSV output files.
        """
        self.journal_dir = Path(journal_dir)
        self.journal_dir.mkdir(parents=True, exist_ok=True)

        self._signals: List[SignalRecord] = []
        self._trades: Dict[int, TradeRecord] = {}  # ticket → TradeRecord
        self._current_date: Optional[date] = None

        logger.info(f"TradeJournal initialized: {self.journal_dir}")
        self._ensure_files_exist()

    def _ensure_files_exist(self):
        """Create empty CSV files with headers if they don't exist yet for today."""
        sig_path = self._get_signal_path()
        if not sig_path.exists():
            with open(sig_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self.SIGNAL_HEADERS)
                
        trd_path = self._get_trade_path()
        if not trd_path.exists():
            with open(trd_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self.TRADE_HEADERS)

    # ── Signal Logging ──────────────────────────────────────────────────

    def log_signal(
        self,
        bar_index: int,
        direction: int,
        entry_price: float,
        sl_price: float,
        tp_price: float,
        probability: float,
        threshold: float,
        decision: str,
        block_reason: str = "",
        lot_size: float = 0.0,
        executed: bool = False,
        ticket: int = 0,
    ) -> SignalRecord:
        """
        Log a model decision for any ICC signal detected.

        Called for EVERY signal — TAKE, SKIP, and BLOCKED.
        """
        # Calculate risk-reward
        if direction == 1:  # Long
            risk = entry_price - sl_price
            reward = tp_price - entry_price
        else:
            risk = sl_price - entry_price
            reward = entry_price - tp_price

        rr = reward / risk if risk > 0 else 0.0

        record = SignalRecord(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            bar_index=bar_index,
            direction=direction,
            direction_str="LONG" if direction == 1 else "SHORT",
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            probability=probability,
            threshold=threshold,
            decision=decision,
            block_reason=block_reason,
            lot_size=lot_size,
            executed=executed,
            ticket=ticket,
            risk_reward=round(rr, 2),
        )

        self._signals.append(record)
        self._write_signal_csv(record)

        logger.info(
            f"📝 Signal logged: {record.decision} {record.direction_str} | "
            f"prob={record.probability:.3f} | R:R={record.risk_reward:.1f}"
        )

        return record

    # ── Trade Logging ───────────────────────────────────────────────────

    def log_trade_opened(
        self,
        ticket: int,
        direction: int,
        entry_price: float,
        lot_size: float,
        sl_price: float,
        tp_price: float,
        probability: float,
    ) -> TradeRecord:
        """Log a trade that was opened on MT5."""
        record = TradeRecord(
            open_timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ticket=ticket,
            direction=direction,
            direction_str="LONG" if direction == 1 else "SHORT",
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            lot_size=lot_size,
            probability=probability,
        )

        self._trades[ticket] = record
        self._write_trade_csv(record)

        logger.info(
            f"📈 Trade opened: ticket={ticket} {record.direction_str} "
            f"{lot_size} lots @ {entry_price:.5f}"
        )

        return record

    def log_trade_closed(
        self,
        ticket: int,
        exit_price: float,
        pnl_usd: float,
        exit_reason: str = "",
    ) -> Optional[TradeRecord]:
        """Log that a trade was closed (SL/TP hit or manual)."""
        if ticket not in self._trades:
            logger.warning(f"Trade {ticket} not in journal — recording anyway")
            record = TradeRecord(
                open_timestamp="unknown",
                ticket=ticket,
                direction=0,
                direction_str="UNKNOWN",
                entry_price=0.0,
                sl_price=0.0,
                tp_price=0.0,
                lot_size=0.0,
                probability=0.0,
            )
            self._trades[ticket] = record

        record = self._trades[ticket]
        record.close_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record.exit_price = exit_price
        record.pnl_usd = pnl_usd
        record.exit_reason = exit_reason
        record.is_closed = True

        # Update CSV (append the close record)
        self._write_trade_csv(record)

        win_loss = "WIN ✅" if pnl_usd > 0 else "LOSS ❌"
        logger.info(
            f"📊 Trade closed: ticket={ticket} | {win_loss} | "
            f"PnL=${pnl_usd:.2f} | Reason={exit_reason}"
        )

        return record

    # ── CSV Writing ─────────────────────────────────────────────────────

    def _get_signal_path(self) -> Path:
        """Get today's signal CSV path."""
        return self.journal_dir / f"signals_{datetime.now():%Y%m%d}.csv"

    def _get_trade_path(self) -> Path:
        """Get today's trade CSV path."""
        return self.journal_dir / f"trades_{datetime.now():%Y%m%d}.csv"

    def _write_signal_csv(self, record: SignalRecord):
        """Append a signal record to today's CSV."""
        path = self._get_signal_path()
        write_header = not path.exists()

        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.SIGNAL_HEADERS)
            if write_header:
                writer.writeheader()
            writer.writerow(asdict(record))

    def _write_trade_csv(self, record: TradeRecord):
        """Append a trade record to today's CSV."""
        path = self._get_trade_path()
        write_header = not path.exists()

        with open(path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.TRADE_HEADERS)
            if write_header:
                writer.writeheader()
            writer.writerow(asdict(record))

    # ── Statistics ──────────────────────────────────────────────────────

    def get_summary(self) -> Dict[str, Any]:
        """
        Get forward-test performance summary.

        Returns dict with model accuracy, trade statistics, and PnL breakdown.
        """
        total_signals = len(self._signals)
        take_signals = [s for s in self._signals if s.decision == "TAKE"]
        skip_signals = [s for s in self._signals if s.decision == "SKIP"]
        blocked_signals = [s for s in self._signals if s.decision == "BLOCKED"]
        executed_signals = [s for s in self._signals if s.executed]

        closed_trades = [t for t in self._trades.values() if t.is_closed]
        open_trades = [t for t in self._trades.values() if not t.is_closed]

        wins = [t for t in closed_trades if t.pnl_usd > 0]
        losses = [t for t in closed_trades if t.pnl_usd <= 0]

        total_pnl = sum(t.pnl_usd for t in closed_trades)
        gross_wins = sum(t.pnl_usd for t in wins)
        gross_losses = abs(sum(t.pnl_usd for t in losses))

        return {
            # Signal stats
            "total_signals": total_signals,
            "take_count": len(take_signals),
            "skip_count": len(skip_signals),
            "blocked_count": len(blocked_signals),
            "executed_count": len(executed_signals),
            "take_rate": len(take_signals) / total_signals if total_signals > 0 else 0.0,

            # Trade stats
            "total_trades": len(closed_trades),
            "open_trades": len(open_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(closed_trades) if closed_trades else 0.0,

            # PnL stats
            "total_pnl": total_pnl,
            "gross_wins": gross_wins,
            "gross_losses": gross_losses,
            "profit_factor": gross_wins / gross_losses if gross_losses > 0 else float("inf"),
            "avg_win": gross_wins / len(wins) if wins else 0.0,
            "avg_loss": gross_losses / len(losses) if losses else 0.0,
        }

    def get_open_tickets(self) -> set:
        """Get set of ticket IDs for trades we're tracking as open."""
        return {t.ticket for t in self._trades.values() if not t.is_closed}

    def format_summary(self) -> str:
        """Format summary as a readable string."""
        s = self.get_summary()

        return (
            f"\n{'='*60}\n"
            f"FORWARD TEST SUMMARY\n"
            f"{'='*60}\n"
            f"Signals: {s['total_signals']} total "
            f"({s['take_count']} TAKE, {s['skip_count']} SKIP, {s['blocked_count']} BLOCKED)\n"
            f"Take rate: {s['take_rate']:.1%}\n"
            f"\n"
            f"Trades: {s['total_trades']} closed, {s['open_trades']} open\n"
            f"Win rate: {s['win_rate']:.1%} ({s['wins']}W / {s['losses']}L)\n"
            f"\n"
            f"Total PnL: ${s['total_pnl']:.2f}\n"
            f"Profit factor: {s['profit_factor']:.2f}\n"
            f"Avg win: ${s['avg_win']:.2f}, Avg loss: ${s['avg_loss']:.2f}\n"
            f"{'='*60}\n"
        )
