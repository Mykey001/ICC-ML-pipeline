"""
Forward Test Engine — Main orchestrator for the forward-testing loop.

Pipeline per new bar:
1. Fetch latest OHLCV from MT5
2. Detect new bar close
3. Run ICC signal generation + model inference via src/icc_ml/
4. Apply risk management filters
5. Execute trade on MT5 (or log in dry-run mode)
6. Track open positions and detect SL/TP closes
7. Log everything to the trade journal
"""
from __future__ import annotations

import sys
import signal as sys_signal
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

import yaml

# Ensure src/ is importable
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from icc_ml.config import StrategyConfig, SymbolSpec
from icc_ml.train import load_model
from icc_ml.live_inference import score_latest_signal, format_trading_decision

from .mt5_bridge import MT5Bridge, OrderResult
from .risk_manager import RiskManager, RiskLimits, AccountState, EmergencyStop
from .trade_journal import TradeJournal

logger = logging.getLogger(__name__)


class ForwardTestEngine:
    """
    Orchestrates the forward-testing loop: bar detection → inference → execution → tracking.

    Single-threaded, clean, and reliable. Uses the already logged-in MT5 terminal.
    """

    def __init__(self, config_path: str):
        """
        Initialize the forward test engine from a YAML config file.

        Args:
            config_path: Path to forward_test/config.yaml
        """
        # Load config
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        # ── Core components ─────────────────────────────────────────

        self.mt5 = MT5Bridge()

        # Symbol spec
        sc = self.config["symbol_spec"]
        self.symbol_spec = SymbolSpec(
            name=sc["name"],
            digits=sc["digits"],
            point=sc["point"],
            contract_size=sc["contract_size"],
            typical_spread_points=sc["typical_spread_points"],
            commission_per_lot_roundturn=sc["commission_per_lot_roundturn"],
        )

        # Strategy config
        strat = self.config["strategy"]
        self.strategy_config = StrategyConfig(
            htf_pivot_len=strat["htf_pivot_len"],
            ltf_pivot_len=strat["ltf_pivot_len"],
            tp_pips=strat["tp_pips"],
            use_custom_swing_sl=strat["use_custom_swing_sl"],
            sl_swing_timeframe=strat["sl_swing_timeframe"],
            sl_swing_pivot_len=strat["sl_swing_pivot_len"],
            sl_max_candidates=strat["sl_max_candidates"],
            sl_buffer_pips=strat["sl_buffer_pips"],
            require_custom_swing_sl=strat["require_custom_swing_sl"],
            one_position_at_a_time=strat["one_position_at_a_time"],
            fixed_lots=strat["fixed_lots"],
            max_hold_bars=strat["max_hold_bars"],
        )

        # Risk manager
        rc = self.config["risk"]
        self.risk_manager = RiskManager(RiskLimits(
            max_positions=rc["max_positions"],
            max_lot_size=rc["max_lot_size"],
            min_lot_size=rc["min_lot_size"],
            default_lot_size=rc["default_lot_size"],
            max_daily_loss_usd=rc["max_daily_loss_usd"],
            max_daily_trades=rc["max_daily_trades"],
            max_drawdown_pct=rc["max_drawdown_pct"],
            min_probability=rc.get("min_probability"),
            min_risk_reward_ratio=rc["min_risk_reward_ratio"],
        ))

        # Emergency stop
        ec = self.config["emergency"]
        self.emergency_stop = EmergencyStop(
            max_consecutive_losses=ec["max_consecutive_losses"],
            max_daily_loss_pct=ec["max_daily_loss_pct"],
            max_loss_in_minutes_usd=ec["max_loss_in_minutes_usd"],
            max_loss_in_minutes_time=ec["max_loss_in_minutes_time"],
        )

        # Trade journal
        log_cfg = self.config["logging"]
        self.journal = TradeJournal(
            journal_dir=str(ROOT / log_cfg["journal_dir"]),
        )

        # ── Settings ────────────────────────────────────────────────

        mt5_cfg = self.config["mt5"]
        self.symbol = mt5_cfg["symbol"]
        self.timeframe = mt5_cfg["timeframe"]
        self.buffer_size = mt5_cfg["buffer_size"]
        self.magic_number = mt5_cfg["magic_number"]
        self.slippage = mt5_cfg["slippage_deviation"]

        exec_cfg = self.config["execution"]
        self.dry_run = exec_cfg["dry_run"]
        self.check_interval = exec_cfg["check_interval_seconds"]

        # ── Model ───────────────────────────────────────────────────

        model_cfg = self.config["model"]
        model_dir = ROOT / model_cfg["directory"]
        model_file = model_cfg.get("file")

        if model_file:
            model_path = model_dir / model_file
        else:
            # Auto-discover first .joblib file
            joblib_files = list(model_dir.glob("*.joblib"))
            if not joblib_files:
                raise FileNotFoundError(f"No .joblib models found in {model_dir}")
            model_path = joblib_files[0]

        logger.info(f"Loading model from {model_path}")
        self.model_bundle = load_model(str(model_path))
        logger.info(
            f"Model loaded: {self.model_bundle['model_type']}, "
            f"threshold={self.model_bundle['threshold']:.4f}, "
            f"features={len(self.model_bundle['feature_cols'])}"
        )

        # ── State ───────────────────────────────────────────────────

        self._running = False
        self._last_bar_time: Optional[datetime] = None
        self._last_signal_bar: Optional[int] = None
        self._tracked_tickets: set = set()  # Tickets we've opened

    # ── Public API ──────────────────────────────────────────────────────

    def start(self):
        """Connect to MT5 and enter the main trading loop."""

        # Connect
        account = self.mt5.connect()
        self.mt5.ensure_symbol_visible(self.symbol)
        self.mt5.detect_filling_mode(self.symbol)

        # Sync risk manager with real account
        self.risk_manager.sync_from_mt5(self.mt5)

        # Log startup
        mode_str = "DRY RUN 🟡" if self.dry_run else "LIVE 🔴"
        logger.info("=" * 70)
        logger.info(f"FORWARD TEST ENGINE — {mode_str}")
        logger.info("=" * 70)
        logger.info(f"Account: {account.login} ({account.currency})")
        logger.info(f"Balance: {account.balance:.2f} {account.currency}")
        logger.info(f"Symbol:  {self.symbol} / {self.timeframe}")
        logger.info(f"Model:   {self.model_bundle['model_type']} (threshold={self.model_bundle['threshold']:.4f})")
        logger.info(f"Lot:     {self.risk_manager.limits.default_lot_size}")
        logger.info(f"Check:   every {self.check_interval}s")
        logger.info("=" * 70)

        if not self.dry_run:
            logger.warning("⚠️  LIVE MODE — Real orders will be placed!")
            logger.warning("    Press Ctrl+C within 10 seconds to abort...")
            time.sleep(10)

        # Run
        self._running = True
        self._main_loop()

    def stop(self):
        """Graceful shutdown."""
        self._running = False
        logger.info("\nShutting down...")

        # Print final summary
        logger.info(self.journal.format_summary())

        # Disconnect
        self.mt5.disconnect()
        logger.info("Forward test engine stopped.")

    def get_status(self) -> Dict[str, Any]:
        """Get current engine status (for Streamlit integration)."""
        summary = self.journal.get_summary()
        return {
            "running": self._running,
            "dry_run": self.dry_run,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "last_bar_time": str(self._last_bar_time) if self._last_bar_time else None,
            "account": {
                "login": self.risk_manager.account.login,
                "balance": self.risk_manager.account.balance,
                "equity": self.risk_manager.account.equity,
                "open_positions": self.risk_manager.account.open_positions,
                "daily_pnl": self.risk_manager.account.daily_pnl,
            },
            "journal": summary,
        }

    # ── Main Loop ───────────────────────────────────────────────────────

    def _main_loop(self):
        """Main trading loop."""
        iteration = 0

        try:
            while self._running:
                iteration += 1

                try:
                    # 1. Emergency check
                    should_stop, stop_reason = self.emergency_stop.check(
                        self.risk_manager.account
                    )
                    if should_stop:
                        logger.critical(f"🚨 EMERGENCY STOP: {stop_reason}")
                        break

                    # 2. Sync account state from MT5
                    self.risk_manager.sync_from_mt5(self.mt5)

                    # 3. Check for closed positions
                    self._check_closed_positions()

                    # 4. Write live status for Streamlit UI
                    self._write_status_json()

                    # 5. Check for new bar
                    new_bar, df = self._check_new_bar()

                    if new_bar and df is not None:
                        logger.info(f"\n{'='*60}")
                        logger.info(f"NEW BAR — {self._last_bar_time}")
                        logger.info(f"{'='*60}")

                        self._on_new_bar(df)

                        logger.info(f"{'='*60}\n")

                    elif iteration % 60 == 0:
                        # Heartbeat log every ~30 minutes (60 * 30s)
                        logger.debug(
                            f"Waiting... iteration={iteration}, "
                            f"positions={self.risk_manager.account.open_positions}"
                        )

                except Exception as e:
                    logger.error(f"Error in loop iteration {iteration}: {e}", exc_info=True)

                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            logger.info("\n⚠️  Ctrl+C received")

        finally:
            self.stop()

    # ── Bar Detection ───────────────────────────────────────────────────

    def _check_new_bar(self):
        """
        Fetch bars and detect if a new bar has closed.

        Returns:
            (new_bar_formed, dataframe)
        """
        df = self.mt5.fetch_bars(self.symbol, self.timeframe, self.buffer_size)

        if df is None or len(df) == 0:
            return False, None

        latest_time = df.iloc[-1]["time"]

        if self._last_bar_time is None:
            self._last_bar_time = latest_time
            logger.info(f"Initialized at bar: {latest_time} ({len(df)} bars loaded)")
            return False, None

        if latest_time > self._last_bar_time:
            self._last_bar_time = latest_time
            return True, df

        return False, None

    def _write_status_json(self):
        """Write current engine state to a JSON file for the Streamlit UI."""
        status_file = self.journal.journal_dir / "engine_status.json"
        
        status = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "running": self._running,
            "mode": "DRY RUN" if self.dry_run else "LIVE",
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "lot_size": self.risk_manager.limits.default_lot_size,
            "model_type": self.model_bundle["model_type"],
            "threshold": self.model_bundle["threshold"],
            "account": {
                "login": self.risk_manager.account.login,
                "balance": self.risk_manager.account.balance,
                "equity": self.risk_manager.account.equity,
                "open_positions": self.risk_manager.account.open_positions,
                "daily_pnl": self.risk_manager.account.daily_pnl,
            }
        }
        
        import json
        try:
            with open(status_file, "w") as f:
                json.dump(status, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to write status json: {e}")

    # ── Core Pipeline ───────────────────────────────────────────────────

    def _on_new_bar(self, df):
        """
        Process a new bar through the full ML pipeline.

        1. Score signal via src/icc_ml/live_inference
        2. Apply risk filters
        3. Execute trade (or log dry-run)
        4. Record in journal
        """
        try:
            # Score latest signal
            decision = score_latest_signal(
                df=df,
                model_bundle=self.model_bundle,
                cfg=self.strategy_config,
                spec=self.symbol_spec,
            )

            if decision is None:
                logger.info("No ICC signal on this bar")
                return

            # Avoid duplicate signals
            if decision["signal_bar"] == self._last_signal_bar:
                logger.debug(f"Already processed signal at bar {decision['signal_bar']}")
                return

            self._last_signal_bar = decision["signal_bar"]

            # Log the decision
            logger.info(format_trading_decision(decision))

            entry_price = df.iloc[-1]["close"]
            direction = decision["direction"]
            sl_price = decision["sl_price"]
            tp_price = decision["tp_price"]
            probability = decision["probability"]
            threshold = decision["threshold"]

            # ── SKIP ────────────────────────────────────────────────
            if decision["decision"] == "SKIP":
                logger.info(
                    f"Model → SKIP (prob={probability:.3f}, threshold={threshold:.3f})"
                )
                self.journal.log_signal(
                    bar_index=decision["signal_bar"],
                    direction=direction,
                    entry_price=entry_price,
                    sl_price=sl_price,
                    tp_price=tp_price,
                    probability=probability,
                    threshold=threshold,
                    decision="SKIP",
                )
                return

            # ── TAKE — Check risk management ────────────────────────
            allowed, reason, lot_size = self.risk_manager.check_trade_allowed(
                signal_probability=probability,
                signal_direction=direction,
                sl_price=sl_price,
                tp_price=tp_price,
                entry_price=entry_price,
            )

            if not allowed:
                logger.warning(f"Trade BLOCKED: {reason}")
                self.journal.log_signal(
                    bar_index=decision["signal_bar"],
                    direction=direction,
                    entry_price=entry_price,
                    sl_price=sl_price,
                    tp_price=tp_price,
                    probability=probability,
                    threshold=threshold,
                    decision="BLOCKED",
                    block_reason=reason,
                )
                return

            # ── Execute ─────────────────────────────────────────────
            logger.info(f"Model → TAKE | Risk → APPROVED ({lot_size:.2f} lots)")

            if self.dry_run:
                logger.info("🟡 DRY RUN — Order NOT placed")
                self.journal.log_signal(
                    bar_index=decision["signal_bar"],
                    direction=direction,
                    entry_price=entry_price,
                    sl_price=sl_price,
                    tp_price=tp_price,
                    probability=probability,
                    threshold=threshold,
                    decision="TAKE",
                    lot_size=lot_size,
                    executed=False,
                )
                return

            # Place real order
            result = self.mt5.place_order(
                symbol=self.symbol,
                direction=direction,
                lot_size=lot_size,
                sl=sl_price,
                tp=tp_price,
                magic=self.magic_number,
                comment=f"FT_{probability:.2f}",
                deviation=self.slippage,
            )

            if result.success:
                logger.info(f"✅ Order executed: ticket={result.ticket}")
                self._tracked_tickets.add(result.ticket)
                self.risk_manager.record_trade_opened()

                self.journal.log_signal(
                    bar_index=decision["signal_bar"],
                    direction=direction,
                    entry_price=result.price or entry_price,
                    sl_price=sl_price,
                    tp_price=tp_price,
                    probability=probability,
                    threshold=threshold,
                    decision="TAKE",
                    lot_size=lot_size,
                    executed=True,
                    ticket=result.ticket or 0,
                )

                self.journal.log_trade_opened(
                    ticket=result.ticket or 0,
                    direction=direction,
                    entry_price=result.price or entry_price,
                    lot_size=lot_size,
                    sl_price=sl_price,
                    tp_price=tp_price,
                    probability=probability,
                )
            else:
                logger.error(f"❌ Order failed: {result.error}")
                self.journal.log_signal(
                    bar_index=decision["signal_bar"],
                    direction=direction,
                    entry_price=entry_price,
                    sl_price=sl_price,
                    tp_price=tp_price,
                    probability=probability,
                    threshold=threshold,
                    decision="TAKE",
                    lot_size=lot_size,
                    executed=False,
                    block_reason=f"Execution failed: {result.error}",
                )

        except Exception as e:
            logger.error(f"Error processing bar: {e}", exc_info=True)

    # ── Position Close Detection ────────────────────────────────────────

    def _check_closed_positions(self):
        """
        Poll MT5 for positions that were closed (SL/TP hit).

        Compares our tracked open tickets against MT5's actual open positions.
        Any ticket that disappears was closed by the broker (SL, TP, or manual).
        """
        if not self._tracked_tickets:
            return

        # Get currently open positions from MT5
        open_positions = self.mt5.get_open_positions(
            symbol=self.symbol,
            magic=self.magic_number,
        )
        open_tickets = {p.ticket for p in open_positions}

        # Find tickets that are no longer open
        closed_tickets = self._tracked_tickets - open_tickets

        for ticket in closed_tickets:
            logger.info(f"Position {ticket} no longer open — checking history...")

            # Look up the deal in history
            deals = self.mt5.get_trade_history(
                symbol=self.symbol,
                magic=self.magic_number,
            )

            # Find the closing deal for this position
            close_deal = None
            for deal in deals:
                if deal.entry == 1 and deal.order != 0:  # OUT deal
                    # Match by checking if this deal closed our position
                    # MT5 links deals to positions via the position ticket
                    close_deal = deal
                    break

            if close_deal:
                # Determine exit reason
                pnl = close_deal.profit + close_deal.swap + close_deal.commission
                exit_reason = self._infer_exit_reason(ticket, close_deal.price)

                self.journal.log_trade_closed(
                    ticket=ticket,
                    exit_price=close_deal.price,
                    pnl_usd=pnl,
                    exit_reason=exit_reason,
                )

                self.risk_manager.record_trade_closed(pnl)
                self.emergency_stop.record_trade_result(pnl)
            else:
                # Couldn't find the close deal — log what we can
                logger.warning(f"Could not find close deal for ticket {ticket}")
                self.journal.log_trade_closed(
                    ticket=ticket,
                    exit_price=0.0,
                    pnl_usd=0.0,
                    exit_reason="UNKNOWN",
                )

            self._tracked_tickets.discard(ticket)

    def _infer_exit_reason(self, ticket: int, exit_price: float) -> str:
        """
        Infer whether a trade was closed by SL, TP, or manually.

        Checks the exit price against the trade's SL and TP from our journal.
        """
        journal_tickets = self.journal._trades
        if ticket not in journal_tickets:
            return "UNKNOWN"

        trade = journal_tickets[ticket]
        sl = trade.sl_price
        tp = trade.tp_price

        # Small tolerance for price matching
        tolerance = self.symbol_spec.point * 10

        if abs(exit_price - sl) < tolerance:
            return "SL"
        elif abs(exit_price - tp) < tolerance:
            return "TP"
        else:
            return "MANUAL"
