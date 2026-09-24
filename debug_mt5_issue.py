"""
Debug script to identify the MT5 import issue causing 98% win rate.
"""
import pandas as pd
import numpy as np
from datetime import datetime
from icc_ml.config import StrategyConfig, ExecutionConfig, SymbolSpec, SYMBOL_PRESETS
from icc_ml.data_fetch import get_ohlcv
from icc_ml.strategy_icc import generate_icc_signals
from icc_ml.icc_labeling import simulate_icc_trades, label_summary

# Load config
cfg = StrategyConfig.from_yaml("default.yaml")
spec = SYMBOL_PRESETS["XAUUSDm"]
exec_cfg = ExecutionConfig.from_yaml("default.yaml")

# Load CSV data (known good)
print("=" * 60)
print("TESTING CSV DATA (KNOWN GOOD - 67% win rate)")
print("=" * 60)
df_csv = pd.read_csv("data/raw/XAUUSDm_H1.csv")
df_csv["time"] = pd.to_datetime(df_csv["time"])
print(f"\nCSV Data shape: {df_csv.shape}")
print(f"CSV Columns: {list(df_csv.columns)}")
print(f"CSV dtypes:\n{df_csv.dtypes}\n")
print("First 3 rows:")
print(df_csv.head(3))
print(f"\nPrice range: {df_csv['close'].min():.3f} to {df_csv['close'].max():.3f}")

# Generate signals
signals_csv = generate_icc_signals(df_csv, cfg, spec)
n_signals_csv = (signals_csv["signal"] != 0).sum()
print(f"\nSignals generated: {n_signals_csv}")

# Check signal details
sig_rows = signals_csv[signals_csv["signal"] != 0].head(3)
print("\nFirst 3 signals (SL and TP prices):")
for idx, row in sig_rows.iterrows():
    entry_price = df_csv.loc[idx, "close"]
    sl_price = row["sl_price"]
    tp_price = row["tp_price"]
    direction = "LONG" if row["signal"] == 1 else "SHORT"
    
    if row["signal"] == 1:
        sl_dist = abs(entry_price - sl_price)
        tp_dist = abs(tp_price - entry_price)
    else:
        sl_dist = abs(sl_price - entry_price)
        tp_dist = abs(entry_price - tp_price)
    
    sl_pips = spec.price_to_pips(sl_dist)
    tp_pips = spec.price_to_pips(tp_dist)
    
    print(f"{direction} @ bar {idx}")
    print(f"  Entry: {entry_price:.3f}")
    print(f"  SL: {sl_price:.3f} (distance: {sl_pips:.0f} pips)")
    print(f"  TP: {tp_price:.3f} (distance: {tp_pips:.0f} pips)")
    print(f"  R:R = 1:{tp_pips/sl_pips:.2f}")

# Simulate trades
trades_csv = simulate_icc_trades(df_csv, signals_csv, cfg, spec, exec_cfg, enforce_one_position=False)
summary_csv = label_summary(trades_csv)

print(f"\n{'='*60}")
print("CSV RESULTS:")
print(f"{'='*60}")
print(f"Trades: {summary_csv['n_trades']}")
print(f"Win rate: {summary_csv['win_rate']:.1%}")
print(f"TP hit rate: {summary_csv['tp_rate']:.1%}")
print(f"SL hit rate: {summary_csv['sl_rate']:.1%}")
print(f"Timeout rate: {summary_csv['timeout_rate']:.1%}")
print(f"Avg net P&L: {summary_csv['avg_net_pips']:.1f} pips")
print(f"Total net P&L: {summary_csv['total_net_pips']:.0f} pips")

# Check SL/TP distances distribution
if len(trades_csv) > 0:
    trades_csv['sl_distance'] = abs(trades_csv['entry_price'] - trades_csv['sl_price'])
    trades_csv['tp_distance'] = abs(trades_csv['tp_price'] - trades_csv['entry_price'])
    trades_csv['sl_pips'] = trades_csv['sl_distance'].apply(spec.price_to_pips)
    trades_csv['tp_pips'] = trades_csv['tp_distance'].apply(spec.price_to_pips)
    
    print(f"\nSL distance (pips) - Mean: {trades_csv['sl_pips'].mean():.0f}, Median: {trades_csv['sl_pips'].median():.0f}, Max: {trades_csv['sl_pips'].max():.0f}")
    print(f"TP distance (pips) - Mean: {trades_csv['tp_pips'].mean():.0f}, Median: {trades_csv['tp_pips'].median():.0f}, Max: {trades_csv['tp_pips'].max():.0f}")
    print(f"Avg R:R = 1:{(trades_csv['tp_pips'] / trades_csv['sl_pips']).mean():.2f}")

print("\n" + "="*60)
print("DIAGNOSIS COMPLETE")
print("="*60)
print("\nIf CSV shows 67% win rate, then MT5 import is the issue.")
print("Check for:")
print("1. Extra columns from MT5 (spread, real_volume)")
print("2. Different time indexing or timezone issues")
print("3. Data type mismatches (float32 vs float64)")
print("4. Price precision issues (digits)")
