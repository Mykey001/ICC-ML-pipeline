"""
Streamlit integration for the new forward_test system.

Provides a dashboard to monitor the forward testing engine, view live logs,
and see the most recent trades and signal decisions.
"""
import streamlit as st
import pandas as pd
from pathlib import Path
import json

def render_tab9_realtime(S, spec, cfg):
    st.header("Forward Testing Dashboard")
    st.caption("Monitor the live forward-testing engine for model evaluation.")
    
    # ── Check logs and read data ──────────────────────────────────────────────
    ROOT = Path(__file__).parent.parent
    logs_dir = ROOT / "forward_test/logs"
    journal_dir = logs_dir / "journal"
    
    col1, col2 = st.columns([1, 2])
    
    # Left column: controls and status
    with col1:
        st.subheader("Engine Status")
        
        status_file = journal_dir / "engine_status.json"
        
        if status_file.exists():
            try:
                with open(status_file, "r") as f:
                    status = json.load(f)
                    
                st.info(f"**Mode**: {status['mode']} | **Last Update**: {status['timestamp']}")
                
                st.markdown("#### Config")
                st.code(f"Symbol: {status['symbol']} / {status['timeframe']}\n"
                        f"Model: {status['model_type']}\n"
                        f"Threshold: {status['threshold']:.3f}\n"
                        f"Lot Size: {status['lot_size']}")
                
                st.markdown("#### Live Account")
                acct = status["account"]
                st.metric("Balance", f"${acct['balance']:.2f}")
                st.metric("Equity", f"${acct['equity']:.2f}")
                
                c1, c2 = st.columns(2)
                c1.metric("Open Positions", acct["open_positions"])
                c2.metric("Daily PnL", f"${acct['daily_pnl']:.2f}", delta=acct['daily_pnl'])
                
            except Exception as e:
                st.error(f"Error reading status: {e}")
        else:
            st.warning("Engine is not currently running (or hasn't written status yet).")
            st.info(
                "**To start it:**\n"
                "```bash\n"
                "forward_test/run_forward_test.bat\n"
                "```"
            )
            
        st.divider()
        st.subheader("Today's Log Stats")
        
        # Read the latest summary if possible
        trades_files = sorted(journal_dir.glob("trades_*.csv"), reverse=True)
        signals_files = sorted(journal_dir.glob("signals_*.csv"), reverse=True)
        
        if trades_files:
            latest_trades = pd.read_csv(trades_files[0])
            st.metric("Total Trades Logged (Today)", len(latest_trades))
            
        if signals_files:
            latest_signals = pd.read_csv(signals_files[0])
            take_count = len(latest_signals[latest_signals["decision"] == "TAKE"])
            skip_count = len(latest_signals[latest_signals["decision"] == "SKIP"])
            block_count = len(latest_signals[latest_signals["decision"] == "BLOCKED"])
            st.metric("Signals Processed (Today)", len(latest_signals))
            st.write(f"🟢 **{take_count}** TAKE | 🟡 **{skip_count}** SKIP | 🔴 **{block_count}** BLOCKED")
            
    # Right column: Data tables
    with col2:
        st.subheader("Recent Decisions")
        if signals_files:
            df_sig = pd.read_csv(signals_files[0])
            if not df_sig.empty:
                df_sig_disp = df_sig.tail(10).iloc[::-1]  # Last 10 reversed
                
                # Format for display
                disp = df_sig_disp[["timestamp", "decision", "direction_str", "probability", "threshold", "block_reason"]].copy()
                disp["probability"] = disp["probability"].apply(lambda x: f"{x:.3f}")
                disp["threshold"] = disp["threshold"].apply(lambda x: f"{x:.3f}")
                
                st.dataframe(disp, use_container_width=True, hide_index=True)
            else:
                st.info("No signals logged today yet.")
        else:
            st.warning("No signal logs found.")
            
        st.subheader("Recent Trades")
        if trades_files:
            df_trd = pd.read_csv(trades_files[0])
            if not df_trd.empty:
                df_trd_disp = df_trd.tail(10).iloc[::-1]
                
                disp = df_trd_disp[["ticket", "direction_str", "entry_price", "exit_price", "pnl_usd", "exit_reason"]].copy()
                disp["pnl_usd"] = disp["pnl_usd"].apply(lambda x: f"${x:.2f}")
                
                st.dataframe(disp, use_container_width=True, hide_index=True)
            else:
                st.info("No trades logged today yet.")
        else:
            st.warning("No trade logs found.")
