"""
Real-time trading engine with automatic bar monitoring and full pipeline transparency.

Automatically:
- Monitors for new bars
- Processes through complete ML pipeline
- Logs every step with detailed progress
- Executes trades based on model decisions
- Manages risk and positions
"""
from __future__ import annotations
import sys
from pathlib import Path
import time
import threading
from datetime import datetime
from typing import Optional, Callable, Dict, Any
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from icc_ml.config import StrategyConfig, SymbolSpec, ExecutionConfig
from icc_ml.strategy_icc import generate_icc_signals
from icc_ml.train import load_model

from .data_manager import DataManager
from .risk_manager import RiskManager, AccountState, EmergencyStop
from .monitor import PerformanceMonitor
from .pipeline_logger import get_pipeline_logger, OperationTimer, ActivityLevel
from .instrumented_indicators import compute_all_indicators_instrumented
from .instrumented_features import build_all_features_instrumented

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
plogger = get_pipeline_logger()


class RealtimeTradingEngine:
    """
    Real-time trading engine with automatic bar monitoring.
    
    Features:
    - Automatic new bar detection (no manual clicking)
    - Complete pipeline execution with logging
    - Model-based trading decisions
    - Risk management integration
    - Performance monitoring
    - Thread-safe operation
    """
    
    def __init__(
        self,
        model_path: str,
        data_manager: DataManager,
        risk_manager: RiskManager,
        emergency_stop: EmergencyStop,
        performance_monitor: PerformanceMonitor,
        strategy_config: StrategyConfig,
        symbol_spec: SymbolSpec,
        execution_config: ExecutionConfig,
        order_executor: Optional[Callable] = None,
        check_interval: int = 10,
        dry_run: bool = True,
    ):
        """
        Initialize real-time trading engine.
        
        Args:
            model_path: Path to trained model
            data_manager: Data manager instance
            risk_manager: Risk manager instance
            emergency_stop: Emergency stop instance
            performance_monitor: Performance monitor instance
            strategy_config: ICC strategy configuration
            symbol_spec: Symbol specification
            execution_config: Execution configuration
            order_executor: Function to execute orders
            check_interval: Seconds between new bar checks
            dry_run: If True, no real orders executed
        """
        self.model_path = model_path
        self.data_manager = data_manager
        self.risk_manager = risk_manager
        self.emergency_stop = emergency_stop
        self.performance_monitor = performance_monitor
        self.cfg = strategy_config
        self.spec = symbol_spec
        self.exec_cfg = execution_config
        self.order_executor = order_executor
        self.check_interval = check_interval
        self.dry_run = dry_run
        
        # Load model
        plogger.info("MODEL", "Load", f"Loading model from {model_path}")
        with OperationTimer(plogger, "MODEL", "Load", "Loading trained model") as timer:
            self.model_bundle = load_model(model_path)
            timer.add_detail("model_type", self.model_bundle["model_type"])
            timer.add_detail("threshold", f"{self.model_bundle['threshold']:.4f}")
            timer.add_detail("features", len(self.model_bundle["feature_cols"]))
            timer.add_detail("training_trades", self.model_bundle.get("n_training_trades", "N/A"))
        
        logger.info(
            f"Model loaded: {self.model_bundle['model_type']}, "
            f"threshold={self.model_bundle['threshold']:.4f}, "
            f"features={len(self.model_bundle['feature_cols'])}"
        )
        
        # State
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_signal_bar: Optional[int] = None
        self.account: Optional[AccountState] = None
        
        plogger.success("ENGINE", "Initialize", "Real-time trading engine initialized", details={
            "check_interval": f"{check_interval}s",
            "dry_run": dry_run,
            "symbol": symbol_spec.name,
        })
    
    def start(self, account: AccountState):
        """
        Start the real-time trading engine.
        
        Args:
            account: Initial account state
        """
        if self.running:
            plogger.warning("ENGINE", "Start", "Engine already running")
            logger.warning("Engine already running")
            return
        
        plogger.info("ENGINE", "Start", "Starting real-time trading engine")
        
        self.account = account
        self.running = True
        self._stop_event.clear()
        
        # Start monitoring thread
        self.thread = threading.Thread(target=self._trading_loop, daemon=True)
        self.thread.start()
        
        plogger.success("ENGINE", "Start", "Real-time engine started successfully")
        logger.info("Real-time trading engine started")
    
    def stop(self):
        """Stop the real-time trading engine."""
        if not self.running:
            return
        
        plogger.info("ENGINE", "Stop", "Stopping real-time trading engine")
        
        self.running = False
        self._stop_event.set()
        
        if self.thread:
            self.thread.join(timeout=10)
        
        plogger.success("ENGINE", "Stop", "Real-time engine stopped")
        logger.info("Real-time trading engine stopped")
    
    def _trading_loop(self):
        """Main trading loop (runs in background thread)."""
        plogger.info("ENGINE", "Loop", "Entering main trading loop")
        logger.info(f"Trading loop started - checking every {self.check_interval}s")
        
        iteration = 0
        
        try:
            while self.running and not self._stop_event.is_set():
                iteration += 1
                
                try:
                    # Check for emergency stop
                    with OperationTimer(plogger, "RISK", "EmergencyCheck", "Checking emergency stop") as timer:
                        should_stop, stop_reason = self.emergency_stop.check(self.account)
                        
                        if should_stop:
                            plogger.critical("RISK", "EmergencyStop", f"EMERGENCY STOP TRIGGERED: {stop_reason}")
                            logger.critical(f"EMERGENCY STOP: {stop_reason}")
                            self.running = False
                            break
                        
                        timer.add_detail("status", "OK")
                    
                    # Check for new bar
                    plogger.debug("ENGINE", "Check", f"Checking for new bar (iteration {iteration})")
                    
                    new_bar, df = self.data_manager.update()
                    
                    if new_bar:
                        plogger.info("ENGINE", "NewBar", f"New bar detected - processing pipeline (iteration {iteration})")
                        logger.info(f"\n{'='*80}\nNEW BAR DETECTED - Processing...\n{'='*80}")
                        
                        # Process the new bar through complete pipeline
                        decision = self._process_bar(df)
                        
                        if decision:
                            # Record in monitor
                            self.performance_monitor.record_signal(decision)
                        
                        plogger.success("ENGINE", "NewBar", "Bar processing completed")
                        logger.info(f"{'='*80}\n")
                    else:
                        # No new bar - just wait
                        if iteration % 60 == 0:  # Log every 60 iterations
                            plogger.debug("ENGINE", "Wait", f"No new bar yet (iteration {iteration})")
                    
                    # Sleep until next check
                    self._stop_event.wait(timeout=self.check_interval)
                
                except Exception as e:
                    plogger.error("ENGINE", "Loop", f"Error in trading loop iteration {iteration}: {e}")
                    logger.error(f"Error in trading loop: {e}", exc_info=True)
                    # Continue running despite error
                    time.sleep(self.check_interval)
        
        except Exception as e:
            plogger.critical("ENGINE", "Loop", f"Fatal error in trading loop: {e}")
            logger.critical(f"Fatal error in trading loop: {e}", exc_info=True)
        
        finally:
            plogger.info("ENGINE", "Loop", "Exiting trading loop")
            logger.info("Trading loop exited")
    
    def _process_bar(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Process new bar through complete ML pipeline.
        
        Args:
            df: Complete OHLCV buffer
        
        Returns:
            Trading decision dict if signal exists, None otherwise
        """
        with OperationTimer(plogger, "PIPELINE", "ProcessBar", "Processing bar through ML pipeline") as timer:
            
            # Step 1: Compute indicators
            plogger.info("PIPELINE", "Step1", "Computing indicators...")
            df_with_indicators = compute_all_indicators_instrumented(df)
            
            # Step 2: Build features
            plogger.info("PIPELINE", "Step2", "Building features...")
            df_with_features = build_all_features_instrumented(df_with_indicators)
            
            # Step 3: Generate ICC signals
            plogger.info("PIPELINE", "Step3", "Generating ICC signals...")
            with OperationTimer(plogger, "SIGNALS", "Generate", "Running ICC state machine") as sig_timer:
                signals = generate_icc_signals(df, self.cfg, self.spec)
                
                # Count signals
                n_signals = (signals["signal"] != 0).sum()
                sig_timer.add_detail("total_signals", int(n_signals))
            
            # Step 4: Check for signal on last bar
            last_idx = len(df) - 1
            
            if signals.loc[last_idx, "signal"] == 0:
                plogger.info("SIGNALS", "Check", "No ICC signal on last bar")
                logger.info("No ICC signal on this bar")
                timer.add_detail("signal", "NONE")
                return None
            
            # Extract signal details
            signal_row = signals.loc[last_idx]
            direction = int(signal_row["signal"])
            sl_price = signal_row["sl_price"]
            tp_price = signal_row["tp_price"]
            entry_price = df.iloc[-1]["close"]
            
            direction_str = "LONG" if direction == 1 else "SHORT"
            plogger.success("SIGNALS", "Detected", f"ICC signal: {direction_str}")
            logger.info(f"ICC Signal: {direction_str} @ {entry_price:.5f}, SL: {sl_price:.5f}, TP: {tp_price:.5f}")
            
            # Check if we already processed this signal
            if last_idx == self._last_signal_bar:
                plogger.warning("SIGNALS", "Duplicate", f"Already processed signal at bar {last_idx}")
                logger.info(f"Already processed this signal")
                return None
            
            self._last_signal_bar = last_idx
            
            # Step 5: Extract features and score with model
            plogger.info("MODEL", "Score", "Extracting features for model scoring...")
            
            with OperationTimer(plogger, "MODEL", "Predict", "Scoring signal with trained model") as model_timer:
                try:
                    feature_cols = self.model_bundle["feature_cols"]
                    features = df_with_features.loc[last_idx, feature_cols].values.reshape(1, -1)
                    
                    # Check for NaNs
                    nan_count = np.isnan(features).sum()
                    if nan_count > 0:
                        plogger.warning("MODEL", "Features", f"{nan_count} NaN values in features")
                        logger.warning(f"Features contain {nan_count} NaN values")
                    
                    # Predict
                    model = self.model_bundle["model"]
                    probability = model.predict_proba(features)[0, 1]
                    threshold = self.model_bundle["threshold"]
                    
                    decision_str = "TAKE" if probability >= threshold else "SKIP"
                    
                    model_timer.add_detail("probability", f"{probability:.4f}")
                    model_timer.add_detail("threshold", f"{threshold:.4f}")
                    model_timer.add_detail("decision", decision_str)
                    model_timer.add_detail("features_used", len(feature_cols))
                    
                    plogger.success("MODEL", "Predict", f"Model decision: {decision_str} (prob={probability:.4f}, threshold={threshold:.4f})")
                    logger.info(f"Model probability: {probability:.4f} (threshold: {threshold:.4f}) → {decision_str}")
                
                except Exception as e:
                    plogger.error("MODEL", "Predict", f"Model scoring failed: {e}")
                    logger.error(f"Model scoring failed: {e}", exc_info=True)
                    return None
            
            # Build decision dict
            decision = {
                "timestamp": datetime.now(),
                "signal_bar": last_idx,
                "direction": direction,
                "direction_str": direction_str,
                "entry_price": entry_price,
                "sl_price": sl_price,
                "tp_price": tp_price,
                "probability": float(probability),
                "threshold": threshold,
                "decision": decision_str,
                "executed": False,
                "blocked": False,
            }
            
            # Step 6: If model says SKIP, we're done
            if decision_str == "SKIP":
                plogger.info("DECISION", "Skip", f"Model says SKIP - not taking trade")
                logger.info("Decision: SKIP (model probability below threshold)")
                timer.add_detail("final_decision", "SKIP")
                return decision
            
            # Step 7: Model says TAKE - check risk management
            plogger.info("DECISION", "Take", "Model says TAKE - checking risk management...")
            
            with OperationTimer(plogger, "RISK", "Check", "Evaluating trade against risk limits") as risk_timer:
                allowed, reason, lot_size = self.risk_manager.check_trade_allowed(
                    account=self.account,
                    signal_probability=probability,
                    signal_direction=direction,
                    sl_price=sl_price,
                    tp_price=tp_price,
                    entry_price=entry_price,
                )
                
                risk_timer.add_detail("allowed", allowed)
                risk_timer.add_detail("lot_size", f"{lot_size:.2f}" if allowed else "N/A")
                
                if not allowed:
                    plogger.warning("RISK", "Blocked", f"Trade blocked: {reason}")
                    logger.warning(f"Trade blocked by risk manager: {reason}")
                    decision["blocked"] = True
                    decision["block_reason"] = reason
                    timer.add_detail("final_decision", "BLOCKED")
                    return decision
                
                plogger.success("RISK", "Approved", f"Trade approved: {lot_size:.2f} lots")
                logger.info(f"Risk check passed: {lot_size:.2f} lots approved")
                
                decision["lot_size"] = lot_size
                decision["risk_approved"] = True
            
            # Step 8: Execute order
            plogger.info("EXECUTION", "Execute", f"Executing {direction_str} order...")
            
            with OperationTimer(plogger, "EXECUTION", "Order", f"Placing {direction_str} order") as exec_timer:
                if self.dry_run:
                    plogger.warning("EXECUTION", "DryRun", "DRY RUN MODE - Order not executed")
                    logger.info("DRY RUN MODE - Order would be executed here")
                    decision["executed"] = False
                    decision["execution_mode"] = "dry_run"
                    exec_timer.add_detail("mode", "DRY_RUN")
                else:
                    success = self._execute_order(decision)
                    decision["executed"] = success
                    decision["execution_mode"] = "live"
                    exec_timer.add_detail("success", success)
                    
                    if success:
                        plogger.success("EXECUTION", "Order", "Order executed successfully")
                        logger.info("✓ Order executed successfully")
                        
                        # Update account state
                        self.risk_manager.record_trade_opened(self.account)
                    else:
                        plogger.error("EXECUTION", "Order", "Order execution failed")
                        logger.error("✗ Order execution failed")
            
            # Final summary
            timer.add_detail("final_decision", "EXECUTED" if decision.get("executed") else "DRY_RUN" if self.dry_run else "FAILED")
            
            return decision
    
    def _execute_order(self, decision: Dict[str, Any]) -> bool:
        """
        Execute trading order.
        
        Args:
            decision: Trading decision dict
        
        Returns:
            True if successful, False otherwise
        """
        if self.order_executor is None:
            plogger.warning("EXECUTION", "NoExecutor", "No order executor configured")
            logger.warning("No order executor configured. Order not placed.")
            return False
        
        try:
            # Build order parameters
            order_params = {
                "symbol": self.spec.name,
                "direction": decision["direction"],
                "lot_size": decision["lot_size"],
                "sl_price": decision["sl_price"],
                "tp_price": decision["tp_price"],
                "comment": f"ICC_ML_{decision['probability']:.3f}",
            }
            
            plogger.info("EXECUTION", "SendOrder", f"Sending order: {order_params}")
            
            # Execute via provided executor function
            result = self.order_executor(**order_params)
            
            if result.get("success"):
                plogger.success("EXECUTION", "OrderResult", f"Order successful: ticket={result.get('ticket')}")
                logger.info(f"Order executed: ticket={result.get('ticket')}")
                return True
            else:
                plogger.error("EXECUTION", "OrderResult", f"Order failed: {result.get('error')}")
                logger.error(f"Order execution failed: {result.get('error')}")
                return False
                
        except Exception as e:
            plogger.error("EXECUTION", "Exception", f"Exception during order execution: {e}")
            logger.error(f"Exception during order execution: {e}", exc_info=True)
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current engine status."""
        return {
            "running": self.running,
            "check_interval": self.check_interval,
            "dry_run": self.dry_run,
            "symbol": self.spec.name,
            "model_loaded": self.model_bundle is not None,
            "account_balance": self.account.balance if self.account else None,
            "account_equity": self.account.equity if self.account else None,
            "open_positions": self.account.open_positions if self.account else None,
        }
