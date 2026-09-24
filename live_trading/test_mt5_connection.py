"""
Test MT5 connection and data pipeline.

Run this before starting live trading to verify everything works.
"""
import sys
from pathlib import Path
import yaml
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from icc_ml.config import StrategyConfig, SymbolSpec
from icc_ml.indicators import compute_all_indicators
from icc_ml.features import build_all_features
from icc_ml.strategy_icc import generate_icc_signals
from icc_ml.train import load_model
from icc_ml.live_inference import score_latest_signal

from data_manager import DataManager

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def load_config(path: str = "config.yaml") -> dict:
    """Load config file."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def test_mt5_connection(config: dict) -> bool:
    """Test MT5 connection (basic connectivity only)."""
    logger.info("=" * 80)
    logger.info("TEST 1: MT5 CONNECTION")
    logger.info("=" * 80)
    
    data_config = config["data"]
    
    if data_config["source"] != "mt5":
        logger.warning(f"⚠️  Data source is '{data_config['source']}', not 'mt5'")
        logger.warning("    Change config.yaml: data.source = mt5")
        return False
    
    try:
        import MetaTrader5 as mt5
        
        # Just test connection, not full initialization
        logger.info("Testing MT5 connection...")
        
        if not mt5.initialize():
            logger.error(f"✗ MT5 initialization failed: {mt5.last_error()}")
            return False
        
        # Check if login needed
        mt5_login = data_config.get("mt5_login")
        mt5_password = data_config.get("mt5_password")
        mt5_server = data_config.get("mt5_server")
        
        if mt5_login and mt5_password and mt5_server:
            logger.info(f"Testing login to account {mt5_login}...")
            authorized = mt5.login(mt5_login, mt5_password, mt5_server)
            if not authorized:
                logger.error(f"✗ Login failed: {mt5.last_error()}")
                mt5.shutdown()
                return False
            logger.info("✓ Login successful")
        
        # Get account info
        account_info = mt5.account_info()
        if account_info is None:
            logger.error("✗ Failed to get account info")
            mt5.shutdown()
            return False
        
        logger.info(f"✓ Connected to MT5 account: {account_info.login}")
        logger.info(f"  Balance: {account_info.balance} {account_info.currency}")
        
        # Check symbol
        symbol = data_config["symbol"]
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.error(f"✗ Symbol {symbol} not found")
            mt5.shutdown()
            return False
        
        if not symbol_info.visible:
            logger.info(f"Adding {symbol} to Market Watch...")
            if not mt5.symbol_select(symbol, True):
                logger.error(f"✗ Failed to add {symbol}")
                mt5.shutdown()
                return False
        
        logger.info(f"✓ Symbol {symbol} available (spread: {symbol_info.spread} points)")
        
        # Try to fetch a few bars
        timeframe = data_config["timeframe"]
        tf_mt5 = {
            "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }.get(timeframe, mt5.TIMEFRAME_H1)
        
        rates = mt5.copy_rates_from_pos(symbol, tf_mt5, 0, 10)
        if rates is None or len(rates) == 0:
            logger.error(f"✗ Failed to fetch bars: {mt5.last_error()}")
            mt5.shutdown()
            return False
        
        logger.info(f"✓ Successfully fetched {len(rates)} test bars")
        
        mt5.shutdown()
        logger.info("✓ MT5 connection test passed")
        return True
            
    except ImportError:
        logger.error("✗ MetaTrader5 package not installed")
        logger.error("   Install: pip install MetaTrader5")
        return False
    except Exception as e:
        logger.error(f"✗ Connection test failed: {e}")
        return False


def test_data_pipeline(config: dict) -> bool:
    """Test full data pipeline (indicators → features → signals)."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: DATA PIPELINE")
    logger.info("=" * 80)
    
    data_config = config["data"]
    
    try:
        # Fetch data
        dm = DataManager(
            symbol=data_config["symbol"],
            timeframe=data_config["timeframe"],
            buffer_size=data_config["buffer_size"],
            data_source=data_config["source"],
            csv_path=data_config.get("csv_path"),
            mt5_login=data_config.get("mt5_login"),
            mt5_password=data_config.get("mt5_password"),
            mt5_server=data_config.get("mt5_server"),
        )
        
        logger.info("Initializing data manager...")
        if not dm.initialize():
            logger.error("✗ Data initialization failed")
            return False
        
        df = dm.get_buffer()
        logger.info(f"✓ Loaded {len(df)} bars")
        
        # Test indicators
        logger.info("Computing indicators...")
        df_ind = compute_all_indicators(df)
        n_indicators = len(df_ind.columns) - len(df.columns)
        logger.info(f"✓ Added {n_indicators} indicators")
        
        # Test features
        logger.info("Building features...")
        df_feat = build_all_features(df_ind)
        n_features = len(df_feat.columns) - len(df_ind.columns)
        logger.info(f"✓ Added {n_features} features")
        
        # Test ICC signals
        logger.info("Generating ICC signals...")
        spec_config = config["symbol_spec"]
        symbol_spec = SymbolSpec(
            name=spec_config["name"],
            digits=spec_config["digits"],
            point=spec_config["point"],
            contract_size=spec_config["contract_size"],
            typical_spread_points=spec_config["typical_spread_points"],
            commission_per_lot_roundturn=spec_config["commission_per_lot_roundturn"],
        )
        
        strat_config = config["strategy"]
        strategy_config = StrategyConfig(
            htf_pivot_len=strat_config["htf_pivot_len"],
            ltf_pivot_len=strat_config["ltf_pivot_len"],
            tp_pips=strat_config["tp_pips"],
            use_custom_swing_sl=strat_config["use_custom_swing_sl"],
            sl_swing_timeframe=strat_config["sl_swing_timeframe"],
            sl_swing_pivot_len=strat_config["sl_swing_pivot_len"],
        )
        
        signals = generate_icc_signals(df, strategy_config, symbol_spec)
        n_signals = (signals["signal"] != 0).sum()
        logger.info(f"✓ Found {n_signals} ICC signals in history")
        
        dm.shutdown()
        return True
        
    except Exception as e:
        logger.error(f"✗ Pipeline test failed: {e}", exc_info=True)
        return False


def test_model_scoring(config: dict) -> bool:
    """Test model loading and scoring."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: MODEL SCORING")
    logger.info("=" * 80)
    
    model_path = Path(__file__).parent / config["model"]["path"]
    
    if not model_path.exists():
        logger.error(f"✗ Model not found: {model_path}")
        logger.error("   Train a model first or update config.yaml")
        return False
    
    try:
        # Load model
        logger.info(f"Loading model from {model_path}")
        model_bundle = load_model(str(model_path))
        logger.info(f"✓ Model loaded: {model_bundle['model_type']}")
        logger.info(f"  - Threshold: {model_bundle['threshold']:.4f}")
        logger.info(f"  - Features: {len(model_bundle['feature_cols'])}")
        
        # Get data
        data_config = config["data"]
        dm = DataManager(
            symbol=data_config["symbol"],
            timeframe=data_config["timeframe"],
            buffer_size=data_config["buffer_size"],
            data_source=data_config["source"],
            csv_path=data_config.get("csv_path"),
            mt5_login=data_config.get("mt5_login"),
            mt5_password=data_config.get("mt5_password"),
            mt5_server=data_config.get("mt5_server"),
        )
        
        if not dm.initialize():
            logger.error("✗ Data initialization failed")
            return False
        
        df = dm.get_buffer()
        
        # Build configs
        spec_config = config["symbol_spec"]
        symbol_spec = SymbolSpec(
            name=spec_config["name"],
            digits=spec_config["digits"],
            point=spec_config["point"],
            contract_size=spec_config["contract_size"],
            typical_spread_points=spec_config["typical_spread_points"],
            commission_per_lot_roundturn=spec_config["commission_per_lot_roundturn"],
        )
        
        strat_config = config["strategy"]
        strategy_config = StrategyConfig(
            htf_pivot_len=strat_config["htf_pivot_len"],
            ltf_pivot_len=strat_config["ltf_pivot_len"],
            tp_pips=strat_config["tp_pips"],
            use_custom_swing_sl=strat_config["use_custom_swing_sl"],
            sl_swing_timeframe=strat_config["sl_swing_timeframe"],
            sl_swing_pivot_len=strat_config["sl_swing_pivot_len"],
        )
        
        # Score latest signal
        logger.info("Scoring latest bar...")
        decision = score_latest_signal(
            df=df,
            model_bundle=model_bundle,
            cfg=strategy_config,
            spec=symbol_spec,
        )
        
        if decision is None:
            logger.info("✓ No ICC signal on latest bar (this is normal)")
        else:
            logger.info("✓ ICC signal found on latest bar:")
            logger.info(f"  - Direction: {'BUY' if decision['direction'] == 1 else 'SELL'}")
            logger.info(f"  - SL: {decision['sl_price']:.3f}")
            logger.info(f"  - TP: {decision['tp_price']:.3f}")
            logger.info(f"  - Probability: {decision['probability']:.4f}")
            logger.info(f"  - Threshold: {decision['threshold']:.4f}")
            logger.info(f"  - Decision: {decision['decision']}")
        
        dm.shutdown()
        return True
        
    except Exception as e:
        logger.error(f"✗ Model scoring failed: {e}", exc_info=True)
        return False


def test_config_consistency(config: dict) -> bool:
    """Check if config matches training assumptions."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: CONFIG CONSISTENCY")
    logger.info("=" * 80)
    
    issues = []
    
    # Check data source
    if config["data"]["source"] == "csv":
        issues.append("⚠️  Using CSV data source (not live MT5)")
    
    # Check execution mode
    if config["execution"]["dry_run"]:
        logger.info("✓ Dry run mode enabled (safe)")
    else:
        logger.warning("⚠️  LIVE TRADING MODE - real orders will be placed!")
    
    # Check risk limits
    risk = config["risk"]
    if risk["default_lot_size"] > 0.1:
        issues.append(f"⚠️  Large default lot size: {risk['default_lot_size']}")
    
    if risk["max_daily_loss_usd"] > 1000:
        issues.append(f"⚠️  High daily loss limit: ${risk['max_daily_loss_usd']}")
    
    # Check symbol
    if config["data"]["symbol"] != config["symbol_spec"]["name"]:
        issues.append("✗ Symbol mismatch in config!")
        logger.error(f"  data.symbol = {config['data']['symbol']}")
        logger.error(f"  symbol_spec.name = {config['symbol_spec']['name']}")
    
    # Display results
    if issues:
        logger.info("\nConfiguration issues found:")
        for issue in issues:
            logger.info(f"  {issue}")
    else:
        logger.info("✓ No configuration issues detected")
    
    return len(issues) == 0


def main():
    """Run all tests."""
    logger.info("\n" + "="*80)
    logger.info("MT5 LIVE TRADING - CONNECTION & PIPELINE TEST")
    logger.info("="*80 + "\n")
    
    # Load config
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        return
    
    logger.info(f"Loading config from {config_path}")
    config = load_config(str(config_path))
    logger.info("✓ Config loaded\n")
    
    # Run tests
    results = {}
    
    results["mt5_connection"] = test_mt5_connection(config)
    results["data_pipeline"] = test_data_pipeline(config)
    results["model_scoring"] = test_model_scoring(config)
    results["config_check"] = test_config_consistency(config)
    
    # Summary
    logger.info("\n" + "="*80)
    logger.info("TEST SUMMARY")
    logger.info("="*80)
    
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{test_name:20s}: {status}")
    
    all_passed = all(results.values())
    
    logger.info("="*80)
    
    if all_passed:
        logger.info("\n✓ ALL TESTS PASSED")
        logger.info("\nYou're ready to run live trading:")
        logger.info("  python main.py --config config.yaml --dry-run")
    else:
        logger.error("\n✗ SOME TESTS FAILED")
        logger.error("\nFix the issues above before running live trading.")
        logger.error("See MT5_SETUP_GUIDE.md for help.")
    
    logger.info("")


if __name__ == "__main__":
    main()
