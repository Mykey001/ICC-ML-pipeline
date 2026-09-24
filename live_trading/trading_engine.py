"""
Core trading engine for live execution.

Integrates:
- Model inference
- Signal scoring
- Order execution
- Position management
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime
import logging
import pandas as pd

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from icc_ml.train import load_model
from icc_ml.live_inference import score_latest_signal, format_trading_decision
from icc_ml.config import StrategyConfig, SymbolSpec

from .risk_manager import RiskManager, AccountState
from .data_manager import DataManager


logger = logging.getLogger(__name__)


class TradingEngine:
    """
    Main trading engine for live execution.
    
    Orchestrates:
    - Data updates
    - Signal scoring
    - Risk checks
    - Order execution
    """
    
    def __init__(
        self,
        model_path: str,
        data_manager: DataManager,
        risk_manager: RiskManager,
        strategy_config: StrategyConfig,
        symbol_spec: SymbolSpec,
        order_executor: Optional[Callable] = None,
        dry_run: bool = True,
    ):
        """
        Initialize trading engine.
        
        Args:
            model_path: Path to trained model bundle
            data_manager: Data manager instance
            risk_manager: Risk manager instance
            strategy_config: ICC strategy configuration
            symbol_spec: Symbol specification
            order_executor: Function to execute orders (if None, logs only)
            dry_run: If True, no real orders executed
        """
        self.model_path = model_path
        self.data_manager = data_manager
        self.risk_manager = risk_manager
        self.cfg = strategy_config
        self.spec = symbol_spec
        self.order_executor = order_executor
        self.dry_run = dry_run
        
        # Load model
        logger.info(f"Loading model from {model_path}")
        self.model_bundle = load_model(model_path)
        logger.info(
            f"Model loaded: {self.model_bundle['model_type']}, "
            f"threshold={self.model_bundle['threshold']:.4f}, "
            f"features={len(self.model_bundle['feature_cols'])}"
        )
        
        # State
        self.running = False
        self._last_signal_bar: Optional[int] = None
        
        logger.info(f"TradingEngine initialized (dry_run={dry_run})")
    
    def process_bar(self, account: AccountState) -> Optional[dict]:
        """
        Process new bar close.
        
        Called when DataManager detects a new bar.
        
        Args:
            account: Current account state
        
        Returns:
            Trading decision dict if signal exists, None otherwise
        """
        # Get latest data
        df = self.data_manager.get_buffer()
        
        logger.info(f"Processing bar {len(df)-1}, time={df.iloc[-1]['time']}")
        
        # Score latest signal
        try:
            decision = score_latest_signal(
                df=df,
                model_bundle=self.model_bundle,
                cfg=self.cfg,
                spec=self.spec,
            )
        except Exception as e:
            logger.error(f"Error scoring signal: {e}", exc_info=True)
            return None
        
        # No signal on this bar
        if decision is None:
            logger.debug("No ICC signal on this bar")
            return None
        
        # Check if we already processed this signal
        signal_bar = decision["signal_bar"]
        if signal_bar == self._last_signal_bar:
            logger.debug(f"Already processed signal at bar {signal_bar}")
            return None
        
        self._last_signal_bar = signal_bar
        
        # Log decision
        logger.info(format_trading_decision(decision))
        
        # If model says SKIP, we're done
        if decision["decision"] == "SKIP":
            logger.info(f"Model says SKIP (probability={decision['probability']:.3f})")
            return decision
        
        # Model says TAKE - check risk management
        allowed, reason, lot_size = self.risk_manager.check_trade_allowed(
            account=account,
            signal_probability=decision["probability"],
            signal_direction=decision["direction"],
            sl_price=decision["sl_price"],
            tp_price=decision["tp_price"],
            entry_price=df.iloc[-1]["close"],  # Assume entry at last close
        )
        
        if not allowed:
            logger.warning(f"Trade blocked by risk manager: {reason}")
            decision["blocked"] = True
            decision["block_reason"] = reason
            return decision
        
        # Risk manager approved - execute trade
        decision["lot_size"] = lot_size
        decision["risk_approved"] = True
        
        logger.info(f"Risk manager approved: {lot_size:.2f} lots")
        
        # Execute order
        if self.dry_run:
            logger.info(f"DRY RUN: Would execute {decision['direction']} trade")
            decision["executed"] = False
            decision["execution_mode"] = "dry_run"
        else:
            success = self._execute_order(decision, account)
            decision["executed"] = success
            decision["execution_mode"] = "live"
        
        return decision
    
    def _execute_order(self, decision: dict, account: AccountState) -> bool:
        """
        Execute trading order.
        
        Args:
            decision: Trading decision dict
            account: Account state
        
        Returns:
            True if successful, False otherwise
        """
        if self.order_executor is None:
            logger.warning("No order executor configured. Order not placed.")
            return False
        
        try:
            # Build order parameters
            order_params = {
                "symbol": self.spec.name,
                "direction": decision["direction"],  # 1=BUY, -1=SELL
                "lot_size": decision["lot_size"],
                "sl_price": decision["sl_price"],
                "tp_price": decision["tp_price"],
                "comment": f"ICC_ML_{decision['probability']:.3f}",
            }
            
            # Execute via provided executor function
            result = self.order_executor(**order_params)
            
            if result.get("success"):
                logger.info(f"Order executed successfully: ticket={result.get('ticket')}")
                self.risk_manager.record_trade_opened(account)
                return True
            else:
                logger.error(f"Order execution failed: {result.get('error')}")
                return False
                
        except Exception as e:
            logger.error(f"Exception during order execution: {e}", exc_info=True)
            return False
    
    def start(self):
        """Mark engine as running."""
        self.running = True
        logger.info("Trading engine started")
    
    def stop(self):
        """Mark engine as stopped."""
        self.running = False
        logger.info("Trading engine stopped")


def demo_order_executor(**kwargs) -> dict:
    """
    Demo order executor (logs only, doesn't place real orders).
    
    Replace this with your broker's API order execution.
    """
    logger.info(f"DEMO ORDER: {kwargs}")
    
    # Simulate success
    return {
        "success": True,
        "ticket": f"DEMO_{datetime.now().timestamp():.0f}",
        "message": "Demo order (not executed)",
    }


def mt5_order_executor(**kwargs) -> dict:
    """
    MetaTrader 5 order executor.
    
    Args (via kwargs):
        symbol: Trading symbol
        direction: 1=BUY, -1=SELL
        lot_size: Position size in lots
        sl_price: Stop loss price
        tp_price: Take profit price
        comment: Order comment
    
    Returns:
        Dict with success status and details
    """
    try:
        import MetaTrader5 as mt5
        
        if not mt5.initialize():
            return {"success": False, "error": f"MT5 not initialized: {mt5.last_error()}"}
        
        symbol = kwargs["symbol"]
        direction = kwargs["direction"]
        lot_size = kwargs["lot_size"]
        sl_price = kwargs["sl_price"]
        tp_price = kwargs["tp_price"]
        comment = kwargs.get("comment", "ICC_ML")
        
        # Get current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"success": False, "error": f"Failed to get tick for {symbol}"}
        
        # Determine order type and price
        if direction == 1:  # BUY
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:  # SELL
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        
        # Build request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": 20,  # Slippage tolerance in points
            "magic": 123456,  # Magic number for ICC ML
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        # Send order
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {
                "success": False,
                "error": f"Order failed: {result.retcode}, {result.comment}",
            }
        
        return {
            "success": True,
            "ticket": result.order,
            "price": result.price,
            "volume": result.volume,
            "comment": result.comment,
        }
        
    except ImportError:
        return {"success": False, "error": "MetaTrader5 package not installed"}
    except Exception as e:
        return {"success": False, "error": str(e)}
