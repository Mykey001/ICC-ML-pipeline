"""
End-to-end test for the real-time trading system.

Tests:
1. Data manager initialization and fetching
2. Instrumented indicators computation
3. Instrumented features computation
4. ICC signal generation
5. Model loading and prediction
6. Risk management checks
7. Pipeline logger and activity feed
8. Real-time engine integration
9. Complete pipeline execution

Run this to verify everything works before using with MT5.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime

# Add paths
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "live_trading"))

print("="*80)
print("ICC ML REAL-TIME TRADING SYSTEM - END-TO-END TEST")
print("="*80)
print()

# Import all components
print("Importing components...")
try:
    from icc_ml.config import StrategyConfig, SymbolSpec, ExecutionConfig
    from icc_ml.train import load_model
    
    from data_manager import DataManager
    from realtime_engine import RealtimeTradingEngine
    from risk_manager import RiskManager, RiskLimits, AccountState, EmergencyStop
    from monitor import PerformanceMonitor
    from trading_engine import demo_order_executor
    from pipeline_logger import get_pipeline_logger
    from activity_feed_ui import ActivityFeedUI
    from instrumented_indicators import compute_all_indicators_instrumented
    from instrumented_features import build_all_features_instrumented
    from logging_config import quick_setup
    
    print("✓ All imports successful")
except Exception as e:
    print(f"✗ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()

# Setup logging
print("Setting up logging...")
try:
    logger = quick_setup(verbose=True, log_dir=str(ROOT / "live_trading" / "logs"))
    print("✓ Logging configured")
except Exception as e:
    print(f"✗ Logging setup failed: {e}")
    sys.exit(1)

print()

# Test 1: Pipeline Logger
print("TEST 1: Pipeline Logger")
print("-" * 80)
try:
    plogger = get_pipeline_logger()
    
    # Test logging
    plogger.info("TEST", "Test1", "Testing INFO level")
    plogger.success("TEST", "Test1", "Testing SUCCESS level")
    plogger.warning("TEST", "Test1", "Testing WARNING level")
    
    # Check feed
    if plogger.feed:
        entries = plogger.feed.get_recent(3)
        print(f"✓ Pipeline logger working ({len(entries)} entries logged)")
    else:
        print("✗ Activity feed not initialized")
        sys.exit(1)
except Exception as e:
    print(f"✗ Pipeline logger test failed: {e}")
    sys.exit(1)

print()

# Test 2: Activity Feed UI
print("TEST 2: Activity Feed UI")
print("-" * 80)
try:
    activity_ui = ActivityFeedUI()
    
    # Get stats
    stats = activity_ui.get_pipeline_stats()
    print(f"✓ Activity feed UI working")
    print(f"  - Total operations: {stats['total_operations']}")
    print(f"  - Last activity: {stats.get('last_activity', 'N/A')}")
except Exception as e:
    print(f"✗ Activity feed UI test failed: {e}")
    sys.exit(1)

print()

# Test 3: Configuration
print("TEST 3: Configuration Objects")
print("-" * 80)
try:
    cfg = StrategyConfig(
        htf_pivot_len=2,
        ltf_pivot_len=1,
        tp_pips=2500.0,
        sl_swing_timeframe="4h",
        sl_swing_pivot_len=2,
    )
    print("✓ StrategyConfig created")
    
    spec = SymbolSpec(
        name="XAUUSDm",
        digits=3,
        point=0.001,
        contract_size=100.0,
        typical_spread_points=30.0,
        commission_per_lot_roundturn=0.0,
    )
    print("✓ SymbolSpec created")
    
    exec_cfg = ExecutionConfig(slippage_points=5.0)
    print("✓ ExecutionConfig created")
except Exception as e:
    print(f"✗ Configuration test failed: {e}")
    sys.exit(1)

print()

# Test 4: Data Manager (CSV mode)
print("TEST 4: Data Manager (CSV)")
print("-" * 80)
try:
    csv_path = ROOT / "data" / "raw" / "XAUUSDm_H1.csv"
    
    if not csv_path.exists():
        print(f"⚠ CSV file not found: {csv_path}")
        print("  Skipping data manager test")
        data_manager = None
    else:
        data_manager = DataManager(
            symbol="XAUUSDm",
            timeframe="H1",
            buffer_size=2000,
            data_source="csv",
            csv_path=str(csv_path),
        )
        
        if data_manager.initialize():
            print("✓ Data manager initialized")
            
            df = data_manager.get_buffer()
            print(f"  - Loaded {len(df)} bars")
            print(f"  - From: {df.iloc[0]['time']}")
            print(f"  - To: {df.iloc[-1]['time']}")
            print(f"  - Columns: {list(df.columns)}")
        else:
            print("✗ Data manager initialization failed")
            data_manager = None
except Exception as e:
    print(f"✗ Data manager test failed: {e}")
    import traceback
    traceback.print_exc()
    data_manager = None

print()

# Test 5: Instrumented Indicators
print("TEST 5: Instrumented Indicators")
print("-" * 80)
if data_manager:
    try:
        df = data_manager.get_buffer()
        
        print(f"Computing indicators on {len(df)} bars...")
        df_with_indicators = compute_all_indicators_instrumented(df)
        
        indicator_cols = len(df_with_indicators.columns) - len(df.columns)
        print(f"✓ Computed {indicator_cols} indicators")
        print(f"  - Total columns: {len(df_with_indicators.columns)}")
        
        # Check for NaNs
        nan_pct = df_with_indicators.isna().sum().sum() / (len(df_with_indicators) * len(df_with_indicators.columns))
        print(f"  - NaN percentage: {nan_pct*100:.2f}%")
        
    except Exception as e:
        print(f"✗ Indicators test failed: {e}")
        import traceback
        traceback.print_exc()
        df_with_indicators = None
else:
    print("⚠ Skipping (no data manager)")
    df_with_indicators = None

print()

# Test 6: Instrumented Features
print("TEST 6: Instrumented Features")
print("-" * 80)
if df_with_indicators is not None:
    try:
        print(f"Building features from {len(df_with_indicators.columns)} columns...")
        df_with_features = build_all_features_instrumented(df_with_indicators)
        
        feature_cols = len(df_with_features.columns) - len(df_with_indicators.columns)
        print(f"✓ Built {feature_cols} features")
        print(f"  - Total columns: {len(df_with_features.columns)}")
        
        # Check for NaNs
        nan_pct = df_with_features.isna().sum().sum() / (len(df_with_features) * len(df_with_features.columns))
        print(f"  - NaN percentage: {nan_pct*100:.2f}%")
        
    except Exception as e:
        print(f"✗ Features test failed: {e}")
        import traceback
        traceback.print_exc()
        df_with_features = None
else:
    print("⚠ Skipping (no indicators)")
    df_with_features = None

print()

# Test 7: Model Loading
print("TEST 7: Model Loading")
print("-" * 80)
try:
    # Find a model
    model_path = None
    for loc in [ROOT / "models", Path("C:/Users/MYCkey98/Downloads/models")]:
        if loc.exists():
            models = list(loc.glob("*.joblib")) + list(loc.glob("*.pkl"))
            if models:
                model_path = models[0]
                break
    
    if model_path is None:
        print("⚠ No model found")
        print("  Train a model first using Tabs 1-8")
        model_bundle = None
    else:
        print(f"Loading model: {model_path.name}")
        model_bundle = load_model(str(model_path))
        
        print("✓ Model loaded successfully")
        print(f"  - Type: {model_bundle['model_type']}")
        print(f"  - Threshold: {model_bundle['threshold']:.4f}")
        print(f"  - Features: {len(model_bundle['feature_cols'])}")
        print(f"  - Training trades: {model_bundle.get('n_training_trades', 'N/A')}")
except Exception as e:
    print(f"✗ Model loading test failed: {e}")
    model_bundle = None

print()

# Test 8: Risk Management
print("TEST 8: Risk Management")
print("-" * 80)
try:
    risk_limits = RiskLimits(
        max_positions=1,
        default_lot_size=0.10,
        max_daily_loss_usd=500.0,
        max_daily_trades=5,
        max_drawdown_pct=15.0,
    )
    print("✓ RiskLimits created")
    
    risk_manager = RiskManager(risk_limits)
    print("✓ RiskManager created")
    
    account = AccountState(
        balance=10000.0,
        equity=10000.0,
        open_positions=0,
        daily_pnl=0.0,
        daily_trades=0,
    )
    print("✓ AccountState created")
    
    # Test risk check
    allowed, reason, lot_size = risk_manager.check_trade_allowed(
        account=account,
        signal_probability=0.75,
        signal_direction=1,
        sl_price=2000.0,
        tp_price=2100.0,
        entry_price=2050.0,
    )
    
    if allowed:
        print(f"✓ Risk check passed: {lot_size:.2f} lots approved")
    else:
        print(f"✗ Risk check failed: {reason}")
        
    emergency_stop = EmergencyStop()
    print("✓ EmergencyStop created")
    
except Exception as e:
    print(f"✗ Risk management test failed: {e}")
    import traceback
    traceback.print_exc()

print()

# Test 9: Performance Monitor
print("TEST 9: Performance Monitor")
print("-" * 80)
try:
    monitor = PerformanceMonitor(log_dir=str(ROOT / "live_trading" / "logs"))
    print("✓ PerformanceMonitor created")
    
    # Test recording a signal
    test_decision = {
        "timestamp": datetime.now(),
        "signal_bar": 100,
        "direction": 1,
        "probability": 0.75,
        "decision": "TAKE",
        "executed": False,
    }
    monitor.record_signal(test_decision)
    print("✓ Signal recorded")
    
    stats = monitor.get_stats()
    print(f"  - Total signals: {stats.total_signals}")
    
except Exception as e:
    print(f"✗ Performance monitor test failed: {e}")

print()

# Test 10: Complete Pipeline (if we have data and model)
print("TEST 10: Complete Pipeline Integration")
print("-" * 80)
if data_manager and model_bundle:
    try:
        print("Creating real-time engine...")
        
        engine = RealtimeTradingEngine(
            model_path=str(model_path),
            data_manager=data_manager,
            risk_manager=risk_manager,
            emergency_stop=emergency_stop,
            performance_monitor=monitor,
            strategy_config=cfg,
            symbol_spec=spec,
            execution_config=exec_cfg,
            order_executor=demo_order_executor,
            check_interval=10,
            dry_run=True,
        )
        
        print("✓ Real-time engine created")
        print(f"  - Model loaded: {engine.model_bundle is not None}")
        print(f"  - Check interval: {engine.check_interval}s")
        print(f"  - Dry run: {engine.dry_run}")
        
        # Test processing a bar (without starting the engine)
        print()
        print("Testing single bar processing...")
        df = data_manager.get_buffer()
        
        decision = engine._process_bar(df)
        
        if decision:
            print("✓ Bar processed successfully")
            print(f"  - Signal detected: {decision.get('direction_str')}")
            print(f"  - Probability: {decision.get('probability', 0):.4f}")
            print(f"  - Decision: {decision.get('decision')}")
            print(f"  - Executed: {decision.get('executed')}")
        else:
            print("✓ Bar processed (no signal on last bar)")
        
    except Exception as e:
        print(f"✗ Pipeline integration test failed: {e}")
        import traceback
        traceback.print_exc()
else:
    print("⚠ Skipping (need data manager and model)")

print()

# Final Summary
print("="*80)
print("TEST SUMMARY")
print("="*80)

# Check activity feed for errors
if activity_ui:
    error_count = activity_ui.get_error_count(minutes=60)
    success_count = activity_ui.get_success_count(minutes=60)
    
    print(f"Operations logged: {stats['total_operations']}")
    print(f"Successes: {success_count}")
    print(f"Errors: {error_count}")
    
    if error_count > 0:
        print()
        print("Recent errors:")
        recent_errors = activity_ui.get_recent_errors(count=5)
        for err in recent_errors:
            print(f"  [{err['timestamp']}] {err['category']}.{err['operation']}: {err['message']}")

print()
print("="*80)
print("END-TO-END TEST COMPLETE")
print("="*80)
print()
print("If all tests passed, the system is ready to use!")
print()
print("Next steps:")
print("1. Review activity logs in live_trading/logs/")
print("2. Start the UI: streamlit run streamlit_app.py")
print("3. Navigate to Tab 9")
print("4. Test with CSV data first (dry-run mode)")
print("5. Then test with MT5 data (still dry-run)")
print("6. Only go live after thorough testing")
print()
