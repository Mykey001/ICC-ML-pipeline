"""
Tab 9 - Real-time Live Trading with Complete Transparency

This is the new Tab 9 implementation with:
- Automatic bar monitoring (no manual clicking)
- Real-time activity feed
- Complete pipeline visibility
- Live statistics and monitoring
"""
import sys
from pathlib import Path
import streamlit as st
import pandas as pd
from datetime import datetime
import time

# Add paths
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "live_trading"))

from icc_ml.train import load_model
from icc_ml.config import ExecutionConfig

from live_trading.data_manager import DataManager
from live_trading.realtime_engine import RealtimeTradingEngine
from live_trading.risk_manager import RiskManager, RiskLimits, AccountState, EmergencyStop
from live_trading.monitor import PerformanceMonitor
from live_trading.trading_engine import demo_order_executor, mt5_order_executor
from live_trading.activity_feed_ui import ActivityFeedUI
from live_trading.pipeline_logger import get_pipeline_logger


def render_tab9_realtime(S, spec, cfg):
    """
    Render Tab 9: Real-time Live Trading
    
    Args:
        S: Streamlit session state
        spec: SymbolSpec
        cfg: StrategyConfig
    """
    st.header("🚀 Real-Time Live Trading Dashboard")
    st.caption("Automatic bar monitoring with complete pipeline transparency")
    
    # Initialize session state
    for k in ("rt_engine", "rt_running", "rt_account", "rt_data_manager", 
              "rt_activity_ui", "rt_monitor", "rt_last_refresh"):
        S.setdefault(k, None)
    
    S.setdefault("rt_running", False)
    S.setdefault("rt_decisions", [])
    
    # Initialize activity UI
    if S.rt_activity_ui is None:
        S.rt_activity_ui = ActivityFeedUI()
    
    # ====================================================================
    # SECTION 1: Model Selection
    # ====================================================================
    st.subheader("📁 Model Selection")
    
    model_locations = [
        ROOT / "models",
        Path("C:/Users/MYCkey98/Downloads/models"),
    ]
    
    available_models = []
    for loc in model_locations:
        if loc.exists():
            models = list(loc.glob("*.joblib")) + list(loc.glob("*.pkl"))
            for model_file in models:
                available_models.append({
                    "name": model_file.name,
                    "path": model_file,
                    "size": model_file.stat().st_size / 1024 / 1024,
                    "modified": datetime.fromtimestamp(model_file.stat().st_mtime),
                })
    
    if not available_models:
        st.warning("⚠️ No trained models found. Train and export a model first (Tab 8).")
        return
    
    selected_model_idx = st.selectbox(
        "Select Model",
        range(len(available_models)),
        format_func=lambda x: f"{available_models[x]['name']} ({available_models[x]['size']:.2f} MB)",
    )
    
    model_path = available_models[selected_model_idx]["path"]
    st.success(f"✓ Selected: `{model_path.name}`")
    
    # ====================================================================
    # SECTION 2: Configuration
    # ====================================================================
    st.divider()
    st.subheader("⚙️ Configuration")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Data Source**")
        data_source = st.selectbox("Source", ["csv", "mt5"], index=0)
        
        if data_source == "csv":
            csv_file = st.text_input("CSV Path", "data/raw/XAUUSDm_H1.csv")
        else:
            csv_file = None
        
        symbol_live = st.text_input("Symbol", spec.name)
        timeframe_live = st.selectbox("Timeframe", ["M15", "M30", "H1", "H4"], index=2)
        check_interval = st.number_input("Check Interval (seconds)", 5, 300, 10, step=5)
    
    with col2:
        st.markdown("**Risk Management**")
        max_positions = st.number_input("Max Positions", 1, 5, 1)
        default_lot_size = st.number_input("Lot Size", 0.01, 10.0, 0.10, step=0.01)
        max_daily_loss = st.number_input("Max Daily Loss ($)", 100.0, 10000.0, 500.0, step=50.0)
        max_daily_trades = st.number_input("Max Daily Trades", 1, 20, 5)
    
    with col3:
        st.markdown("**Execution**")
        dry_run = st.checkbox("Dry Run (no real orders)", value=True)
        if not dry_run:
            st.warning("⚠️ LIVE TRADING MODE!")
        
        starting_balance = st.number_input("Starting Balance ($)", 100.0, 1000000.0, 10000.0, step=100.0)
        
        auto_refresh = st.checkbox("Auto-refresh UI (every 3s)", value=False)
    
    # ====================================================================
    # SECTION 3: Control Buttons
    # ====================================================================
    st.divider()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if not S.rt_running:
            if st.button("▶️ START", type="primary", use_container_width=True):
                try:
                    # Create components
                    risk_limits = RiskLimits(
                        max_positions=max_positions,
                        default_lot_size=default_lot_size,
                        max_daily_loss_usd=max_daily_loss,
                        max_daily_trades=max_daily_trades,
                        max_drawdown_pct=15.0,
                    )
                    
                    S.rt_account = AccountState(
                        balance=starting_balance,
                        equity=starting_balance,
                        open_positions=0,
                        daily_pnl=0.0,
                        daily_trades=0,
                    )
                    
                    S.rt_data_manager = DataManager(
                        symbol=symbol_live,
                        timeframe=timeframe_live,
                        buffer_size=2000,
                        data_source=data_source,
                        csv_path=str(ROOT / csv_file) if csv_file else None,
                    )
                    
                    if not S.rt_data_manager.initialize():
                        st.error("❌ Failed to initialize data manager")
                        st.stop()
                    
                    risk_manager = RiskManager(risk_limits)
                    emergency_stop = EmergencyStop()
                    S.rt_monitor = PerformanceMonitor(log_dir=str(ROOT / "live_trading" / "logs"))
                    
                    order_executor = mt5_order_executor if (data_source == "mt5" and not dry_run) else demo_order_executor
                    
                    exec_cfg = ExecutionConfig(slippage_points=5.0)
                    
                    S.rt_engine = RealtimeTradingEngine(
                        model_path=str(model_path),
                        data_manager=S.rt_data_manager,
                        risk_manager=risk_manager,
                        emergency_stop=emergency_stop,
                        performance_monitor=S.rt_monitor,
                        strategy_config=cfg,
                        symbol_spec=spec,
                        execution_config=exec_cfg,
                        order_executor=order_executor,
                        check_interval=check_interval,
                        dry_run=dry_run,
                    )
                    
                    S.rt_engine.start(S.rt_account)
                    S.rt_running = True
                    
                    st.success("✅ Real-time engine started!")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Failed to start: {e}")
                    import traceback
                    with st.expander("Error Details"):
                        st.code(traceback.format_exc())
        else:
            if st.button("⏸️ STOP", type="secondary", use_container_width=True):
                if S.rt_engine:
                    S.rt_engine.stop()
                if S.rt_data_manager:
                    S.rt_data_manager.shutdown()
                S.rt_running = False
                st.success("✅ Stopped")
                st.rerun()
    
    with col2:
        if st.button("🔄 REFRESH", use_container_width=True):
            S.rt_last_refresh = datetime.now()
            st.rerun()
    
    with col3:
        if st.button("🗑️ CLEAR ACTIVITY", use_container_width=True):
            if S.rt_activity_ui:
                S.rt_activity_ui.clear_activity()
            st.rerun()
    
    with col4:
        if S.rt_activity_ui and st.button("💾 EXPORT LOG", use_container_width=True):
            log_path = ROOT / "live_trading" / "logs" / f"activity_{datetime.now():%Y%m%d_%H%M%S}.log"
            S.rt_activity_ui.export_activity_log(str(log_path))
            st.success(f"✓ Exported to {log_path.name}")
    
    # Auto-refresh logic
    if auto_refresh and S.rt_running:
        time.sleep(3)
        st.rerun()
    
    # ====================================================================
    # SECTION 4: System Status
    # ====================================================================
    st.divider()
    
    if S.rt_running:
        st.success("🟢 **SYSTEM RUNNING**")
        
        # Current operation
        if S.rt_activity_ui:
            current_op = S.rt_activity_ui.get_current_operation()
            if current_op:
                st.info(f"📍 Current: {current_op}")
        
        # Status metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Mode", "DRY RUN" if dry_run else "🔴 LIVE")
            st.metric("Source", data_source.upper())
        
        with col2:
            if S.rt_account:
                st.metric("Balance", f"${S.rt_account.balance:,.2f}")
                st.metric("Equity", f"${S.rt_account.equity:,.2f}")
        
        with col3:
            if S.rt_account:
                st.metric("Daily P&L", f"${S.rt_account.daily_pnl:,.2f}",
                         delta_color="normal" if S.rt_account.daily_pnl >= 0 else "inverse")
                st.metric("Daily Trades", S.rt_account.daily_trades)
        
        with col4:
            if S.rt_account:
                st.metric("Open Positions", S.rt_account.open_positions)
            
            if S.rt_data_manager:
                df_buffer = S.rt_data_manager.get_buffer()
                if len(df_buffer) > 0:
                    latest_time = df_buffer.iloc[-1]["time"]
                    st.metric("Latest Bar", str(latest_time)[:16])
    else:
        st.info("🔴 **SYSTEM STOPPED** - Click START to begin")
    
    # ====================================================================
    # SECTION 5: Live Activity Feed
    # ====================================================================
    st.divider()
    st.subheader("📊 Live Activity Feed")
    st.caption("Real-time pipeline execution log - every step is tracked")
    
    if S.rt_activity_ui:
        # Activity controls
        col1, col2 = st.columns([3, 1])
        with col1:
            activity_lines = st.slider("Activity lines to show", 20, 200, 100, step=10)
        with col2:
            show_raw = st.checkbox("Show raw format", value=False)
        
        # Display activity
        if show_raw:
            # Raw text format with colors
            activity_text = S.rt_activity_ui.get_formatted_activity(count=activity_lines, colorize=True)
            st.markdown(
                f"""
                <div style="background-color: #1e1e1e; padding: 15px; border-radius: 5px; 
                            font-family: 'Courier New', monospace; font-size: 11px; 
                            overflow-y: scroll; max-height: 500px; white-space: pre-wrap;">
                {activity_text}
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            # Table format
            activity_df = S.rt_activity_ui.get_activity_dataframe(count=activity_lines)
            if not activity_df.empty:
                # Color code by level
                def color_level(row):
                    if row["Level"] in ["ERROR", "CRITICAL"]:
                        return ['background-color: #ff444420'] * len(row)
                    elif row["Level"] == "WARNING":
                        return ['background-color: #ffaa0020'] * len(row)
                    elif row["Level"] == "SUCCESS":
                        return ['background-color: #44ff4420'] * len(row)
                    else:
                        return [''] * len(row)
                
                styled_df = activity_df.style.apply(color_level, axis=1)
                st.dataframe(styled_df, use_container_width=True, hide_index=True, height=500)
            else:
                st.info("No activity yet. Start trading to see live updates.")
    
    # ====================================================================
    # SECTION 6: Pipeline Statistics
    # ====================================================================
    st.divider()
    st.subheader("📈 Pipeline Statistics")
    
    if S.rt_activity_ui:
        stats = S.rt_activity_ui.get_pipeline_stats()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Operations", stats.get("total_operations", 0))
            st.metric("Timed Operations", stats.get("timed_operations", 0))
        
        with col2:
            st.metric("Avg Duration", f"{stats.get('avg_duration_ms', 0):.0f}ms")
            if stats.get("last_activity"):
                elapsed = (datetime.now() - stats["last_activity"]).total_seconds()
                st.metric("Last Activity", f"{elapsed:.0f}s ago")
            else:
                st.metric("Last Activity", "N/A")
        
        with col3:
            errors = S.rt_activity_ui.get_error_count(minutes=60)
            successes = S.rt_activity_ui.get_success_count(minutes=60)
            st.metric("Errors (1h)", errors, delta_color="inverse" if errors > 0 else "off")
            st.metric("Successes (1h)", successes)
        
        with col4:
            # Category breakdown
            if stats.get("category_counts"):
                top_category = max(stats["category_counts"].items(), key=lambda x: x[1])
                st.metric("Most Active Category", f"{top_category[0]} ({top_category[1]})")
            else:
                st.metric("Most Active Category", "N/A")
        
        # Longest operations
        if stats.get("longest_operations"):
            with st.expander("⏱️ Longest Operations"):
                longest_df = pd.DataFrame(stats["longest_operations"])
                st.dataframe(longest_df, use_container_width=True, hide_index=True)
        
        # Category breakdown chart
        if stats.get("category_counts"):
            with st.expander("📊 Operations by Category"):
                cat_df = pd.DataFrame(list(stats["category_counts"].items()), columns=["Category", "Count"])
                st.bar_chart(cat_df.set_index("Category"))
    
    # ====================================================================
    # SECTION 7: Trading Performance
    # ====================================================================
    if S.rt_monitor and S.rt_running:
        st.divider()
        st.subheader("💼 Trading Performance")
        
        try:
            perf_stats = S.rt_monitor.get_stats()
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Signals", perf_stats.total_signals)
                st.metric("Signals Taken", perf_stats.signals_taken)
            
            with col2:
                st.metric("Signals Skipped", perf_stats.signals_skipped)
                st.metric("Signals Blocked", perf_stats.signals_blocked)
            
            with col3:
                if perf_stats.signals_taken > 0:
                    take_rate = perf_stats.signals_taken / perf_stats.total_signals * 100
                    st.metric("Take Rate", f"{take_rate:.1f}%")
                
                if perf_stats.trades_closed > 0:
                    st.metric("Trades Closed", perf_stats.trades_closed)
            
            with col4:
                if perf_stats.trades_closed > 0:
                    st.metric("Win Rate", f"{perf_stats.win_rate*100:.1f}%")
                    st.metric("Total P&L", f"${perf_stats.total_pnl:.2f}")
        
        except Exception as e:
            st.warning(f"Performance stats unavailable: {e}")
    
    # ====================================================================
    # SECTION 8: Recent Errors (if any)
    # ====================================================================
    if S.rt_activity_ui:
        recent_errors = S.rt_activity_ui.get_recent_errors(count=5)
        
        if recent_errors:
            st.divider()
            st.subheader("⚠️ Recent Errors")
            
            for err in recent_errors:
                st.error(f"[{err['timestamp']}] {err['category']}.{err['operation']}: {err['message']}")
    
    # ====================================================================
    # SECTION 9: Instructions
    # ====================================================================
    with st.expander("📖 How to Use"):
        st.markdown("""
        ### Real-Time Trading System
        
        **This system runs automatically - no manual clicking required!**
        
        #### Features:
        - ✅ Automatic bar monitoring every N seconds
        - ✅ Complete pipeline transparency (see every step)
        - ✅ Real-time activity feed with color-coded logs
        - ✅ Detailed timing for each operation
        - ✅ Live statistics and performance tracking
        - ✅ No simulation - uses actual model and real pipeline
        
        #### Pipeline Steps (All Logged):
        1. **DATA**: Fetch new bar from MT5/CSV
        2. **INDICATORS**: Compute 10 categories (Trend, Momentum, Volatility, etc.)
        3. **FEATURES**: Build 6 transformation groups (Direction, Strength, etc.)
        4. **SIGNALS**: Run ICC state machine
        5. **MODEL**: Score signal with trained model
        6. **RISK**: Check risk limits
        7. **EXECUTION**: Place order (or log in dry-run)
        
        #### Controls:
        - **START**: Begin automatic monitoring
        - **STOP**: Stop engine and close connections
        - **REFRESH**: Manually refresh UI
        - **CLEAR ACTIVITY**: Clear activity log
        - **EXPORT LOG**: Save activity to file
        
        #### Auto-Refresh:
        - Enable "Auto-refresh UI" to see updates every 3 seconds
        - Disable for manual control
        
        #### Activity Feed:
        - Shows every operation with timestamp and duration
        - Color-coded: Green=Success, Blue=Info, Yellow=Warning, Red=Error
        - Switch between table view and raw text view
        
        #### Safety:
        - Always test on CSV first
        - Use dry-run mode initially
        - Monitor for errors in activity feed
        - Check MT5 connection status before live trading
        """)
