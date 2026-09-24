"""
ICC-ML Studio -- GUI for the full pipeline.

Run:  streamlit run app/streamlit_app.py

Each tab is one pipeline stage and writes its output into st.session_state, so
later tabs can consume earlier results. Stages are intentionally gated: you
cannot train before labels exist. That ordering is not UI decoration -- it is
the same dependency chain that keeps the methodology sound.
"""

from __future__ import annotations
import sys
import io
import json
import importlib.util
from pathlib import Path
from datetime import datetime, date

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from icc_ml.config import StrategyConfig, ExecutionConfig, SymbolSpec, SYMBOL_PRESETS
from icc_ml.data_fetch import validate_ohlcv, get_ohlcv
from icc_ml.indicators import compute_all_indicators
from icc_ml.features import build_all_features
from icc_ml.strategy_icc import generate_icc_signals
from icc_ml.icc_labeling import (simulate_icc_trades, diagnose_trades,
                                   attach_features_to_trades)
from icc_ml.train import (get_feature_columns, train_walk_forward, summarize_folds,
                           fit_final_model, build_model, select_deployment_threshold)
from icc_ml.regime import (compute_regimes, attach_regimes_to_trades, regime_profile,
                            regime_oos_report)
from icc_ml.backtest import (compare_model_vs_baseline, sequential_backtest,
                              performance_metrics, live_parity_checks)
from icc_ml.validation import compute_ic, rolling_ic_stability, redundancy_clusters


st.set_page_config(page_title="ICC-ML Studio", page_icon="📈", layout="wide")

S = st.session_state
for k in ("df", "features", "signals", "trades", "joined", "feature_cols",
          "oos", "fold_results", "summary", "spec", "cfg", "execc"):
    S.setdefault(k, None)


def _stage_badge(done: bool, label: str) -> str:
    return f"{'✅' if done else '⬜'} {label}"


# ===========================================================================
# SIDEBAR -- configuration shared by every stage
# ===========================================================================
with st.sidebar:
    st.title("📈 ICC-ML Studio")
    st.caption("Meta-labeling pipeline for the ICC Swing strategy")

    st.subheader("Pipeline progress")
    st.markdown("  \n".join([
        _stage_badge(S.df is not None, "1. Data"),
        _stage_badge(S.features is not None, "2. Features"),
        _stage_badge(S.signals is not None, "3. ICC signals"),
        _stage_badge(S.joined is not None, "4. Labels"),
        _stage_badge(S.oos is not None, "5. Trained"),
    ]))

    st.divider()
    st.subheader("Symbol specification")
    preset = st.selectbox("Preset", list(SYMBOL_PRESETS.keys()), index=3)
    base = SYMBOL_PRESETS[preset]

    with st.expander("Override broker values", expanded=False):
        st.caption("Defaults are placeholders. Use your broker's real values.")
        digits = st.number_input("Digits", 0, 8, base.digits)
        point = st.number_input("Point", value=float(base.point), format="%.8f")
        contract = st.number_input("Contract size", value=float(base.contract_size))
        spread_pts = st.number_input("Typical spread (points)",
                                      value=float(base.typical_spread_points))
        commission = st.number_input("Commission / lot round turn",
                                      value=float(base.commission_per_lot_roundturn))

    spec = SymbolSpec(preset, int(digits), float(point), float(contract),
                       float(spread_pts), float(commission))
    S.spec = spec
    st.metric("Pip size", f"{spec.pip:g}")

    st.divider()
    st.subheader("Strategy parameters")
    tp_pips = st.number_input("TP pips", value=2500.0, step=50.0)
    tp_price = spec.pips_to_price(tp_pips)
    if spec.digits in (3, 5) and tp_pips > 600:
        st.error(f"TP = {tp_price:.5f} price move. On a {spec.digits}-digit quote "
                  f"this is likely unreachable. Expect a 0% TP hit rate.")
    else:
        st.success(f"TP = {tp_price:g} price move")

    htf_len = st.number_input("HTF pivot length", 1, 10, 2)
    ltf_len = st.number_input("LTF pivot length", 1, 10, 1)
    sl_tf = st.selectbox("SL swing timeframe", ["1h", "4h", "1D"], index=1)
    sl_len = st.number_input("SL swing pivot length", 1, 10, 2)
    sl_buffer = st.number_input("SL buffer (pips)", 0.0, 500.0, 0.0)
    max_hold = st.number_input("Max hold (bars)", 100, 10000, 2000, step=100)

    st.subheader("Execution realism")
    slippage = st.number_input("Slippage (points)", 0.0, 100.0, 5.0)
    both_hit = st.selectbox("SL & TP in same bar", ["sl_first", "tp_first"], index=0,
                             help="sl_first is the pessimistic, correct default.")
    if both_hit == "tp_first":
        st.warning("tp_first inflates results. Use only for sensitivity analysis.")

    S.cfg = StrategyConfig(
        htf_pivot_len=int(htf_len), ltf_pivot_len=int(ltf_len), tp_pips=float(tp_pips),
        sl_swing_timeframe=sl_tf, sl_swing_pivot_len=int(sl_len),
        sl_buffer_pips=float(sl_buffer), max_hold_bars=int(max_hold),
    )
    S.execc = ExecutionConfig(slippage_points=float(slippage),
                               both_hit_same_bar_policy=both_hit)


tabs = st.tabs(["1 · Data", "2 · Features", "3 · Signals", "4 · Labels",
                 "5 · Train", "6 · Validate", "7 · Backtest", "8 · Export", "9 · Live Trading"])


# ===========================================================================
# TAB 1 -- DATA
# ===========================================================================
with tabs[0]:
    st.header("Data acquisition")
    src = st.radio("Source", ["Upload CSV", "MetaTrader 5"],
                    horizontal=True)

    if src == "Upload CSV":
        st.caption("Required columns: time, open, high, low, close, volume — UTC, ascending.")
        up = st.file_uploader("OHLCV CSV", type=["csv"])
        if up and st.button("Load CSV", type="primary"):
            df = pd.read_csv(up)
            df.columns = [c.strip().lower() for c in df.columns]
            missing = {"time", "open", "high", "low", "close"} - set(df.columns)
            if missing:
                st.error(f"Missing columns: {missing}")
            else:
                df["time"] = pd.to_datetime(df["time"])
                if "volume" not in df:
                    df["volume"] = 0.0
                S.df = df.sort_values("time").reset_index(drop=True)
                S.features = S.signals = S.joined = S.oos = None

    else:  # MetaTrader 5
        c1, c2, c3 = st.columns(3)
        sym = c1.text_input("Symbol", preset)
        tf = c2.selectbox("Timeframe", ["M15", "M30", "H1", "H4", "D1"], index=2)
        yrs = c3.number_input("Years of history", 1, 20, 8)
        st.caption("Requires Windows, a running MT5 terminal, and `pip install MetaTrader5`.")
        if st.button("Fetch from MT5", type="primary"):
            try:
                end = datetime.now()
                start = datetime(end.year - int(yrs), end.month, end.day)
                with st.spinner("Fetching..."):
                    df, rep = get_ohlcv(sym, tf, start, end, source="mt5")
                S.df = df
                S.features = S.signals = S.joined = S.oos = None
                st.success(f"Fetched {len(df)} bars")
            except Exception as e:
                st.error(f"MT5 fetch failed: {e}")

    if S.df is not None:
        df = S.df
        rep = validate_ohlcv(df)
        c = st.columns(4)
        c[0].metric("Bars", f"{len(df):,}")
        c[1].metric("From", str(df['time'].min())[:10])
        c[2].metric("To", str(df['time'].max())[:10])
        mbr = rep.get("missing_bar_ratio")
        c[3].metric("Missing bars", f"{mbr:.1%}" if mbr is not None else "n/a")

        issues = []
        if rep["duplicate_timestamps"]:
            issues.append(f"{rep['duplicate_timestamps']} duplicate timestamps")
        if rep["non_monotonic"]:
            issues.append("timestamps not monotonic")
        if rep["zero_or_negative_price_rows"]:
            issues.append(f"{rep['zero_or_negative_price_rows']} zero/negative prices")
        if rep["high_less_than_low_rows"]:
            issues.append(f"{rep['high_less_than_low_rows']} rows with high < low")
        if issues:
            st.error("Data quality problems: " + "; ".join(issues))
        else:
            st.success("Data quality checks passed")

        st.line_chart(df.set_index("time")["close"], height=260)
        with st.expander("Preview"):
            st.dataframe(df.head(50), width="stretch")


# ===========================================================================
# TAB 2 -- FEATURES
# ===========================================================================
with tabs[1]:
    st.header("Indicators & feature engineering")
    if S.df is None:
        st.warning("Load data first (tab 1).")
    else:
        st.caption("Layer 1 computes raw indicators across all 10 categories. "
                    "Layer 2 extracts Direction/Strength/Acceleration and "
                    "State/Magnitude/Recency. See docs/01.")
        if st.button("Compute features", type="primary"):
            with st.spinner("Computing indicators and features..."):
                ind = compute_all_indicators(S.df)
                S.features = build_all_features(ind)
                S.indicators = ind
            st.success(f"{S.features.shape[1] - 1} features computed")

        if S.features is not None:
            f = S.features
            cols = [c for c in f.columns if c != "time"]
            st.metric("Feature count", len(cols))

            groups = {
                "Trend": ["ema", "adx", "di_", "aroon", "vortex", "supertrend", "linreg", "macd"],
                "Momentum": ["rsi", "stoch", "cci", "roc", "willr"],
                "Volatility": ["atr", "bb_", "hv_", "squeeze"],
                "Structure": ["structure", "bos", "choch", "swing"],
                "Volume": ["obv", "volume", "vwap", "mfi", "cmf"],
                "Mean reversion": ["zscore", "hurst", "distance_pct", "extreme"],
                "Regime": ["regime"],
                "Price action": ["candle", "wick", "body", "consecutive", "engulf", "streak"],
                "Liquidity/SMC": ["fvg", "equal_", "sweep", "pdh", "pdl"],
                "Time": ["session", "hour", "dow"],
            }
            rows = []
            for g, keys in groups.items():
                n = sum(any(k in c for k in keys) for c in cols)
                rows.append({"Category": g, "Features": n})
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

            with st.expander("Inspect feature values"):
                pick = st.selectbox("Feature", cols)
                st.line_chart(f.set_index("time")[pick], height=220)


# ===========================================================================
# TAB 3 -- SIGNALS
# ===========================================================================
with tabs[2]:
    st.header("ICC strategy signals (primary model)")
    if S.df is None:
        st.warning("Load data first (tab 1).")
    else:
        st.caption("The ICC state machine decides DIRECTION. The ML model later "
                    "decides TAKE/SKIP. See docs/02.")
        if st.button("Generate signals", type="primary"):
            with st.spinner("Running state machine..."):
                S.signals = generate_icc_signals(S.df, S.cfg, S.spec)

        if S.signals is not None:
            sg = S.signals
            n = int((sg["signal"] != 0).sum())
            c = st.columns(4)
            c[0].metric("Signals", n)
            c[1].metric("Long", int((sg["signal"] == 1).sum()))
            c[2].metric("Short", int((sg["signal"] == -1).sum()))
            c[3].metric("Per 1k bars", f"{n / len(S.df) * 1000:.1f}")

            if n < 300:
                st.warning(f"{n} signals. At least 300 is recommended before "
                            f"walk-forward results carry weight — extend history.")
            else:
                st.success(f"{n} signals — adequate sample")

            plot = S.df[["time", "close"]].copy()
            plot["long"] = np.where(sg["signal"] == 1, S.df["close"], np.nan)
            plot["short"] = np.where(sg["signal"] == -1, S.df["close"], np.nan)
            st.line_chart(plot.set_index("time"), height=300)


# ===========================================================================
# TAB 4 -- LABELS
# ===========================================================================
with tabs[3]:
    st.header("Meta-labels (trade outcome simulation)")
    if S.signals is None or S.features is None:
        st.warning("Need features (tab 2) and signals (tab 3).")
    else:
        st.caption("Each signal is simulated to its real SL/TP exit with spread, "
                    "slippage and commission. Labeling mode ignores the one-position "
                    "constraint on purpose — see docs/03.")
        if st.button("Simulate & label", type="primary"):
            with st.spinner("Simulating trades..."):
                tr = simulate_icc_trades(S.df, S.signals, S.cfg, S.spec, S.execc,
                                          enforce_one_position=False)
                if len(tr):
                    tr = attach_regimes_to_trades(tr, compute_regimes(S.df))
                S.trades = tr
                joined = attach_features_to_trades(tr, S.features).dropna(subset=["win"])
                cols = get_feature_columns(joined)
                keep = [c for c in cols
                        if joined[c].notna().mean() > 0.9 and joined[c].nunique(dropna=True) > 1]
                S.joined = joined.dropna(subset=keep)
                S.feature_cols = keep

        if S.trades is not None:
            d = diagnose_trades(S.trades, S.cfg, S.spec)
            if "error" in d:
                st.error(d["error"])
            else:
                c = st.columns(5)
                c[0].metric("Labeled trades", d["n_taken"])
                c[1].metric("Win rate", f"{d['win_rate']:.1%}")
                c[2].metric("TP hit", f"{d['tp_hit_rate']:.1%}")
                c[3].metric("SL hit", f"{d['sl_hit_rate']:.1%}")
                c[4].metric("Timeout", f"{d['timeout_rate']:.1%}")
                for w in d.get("warnings", []):
                    st.warning(w)
                if not d.get("warnings"):
                    st.success("All label diagnostics passed")

                if S.joined is not None:
                    st.info(f"Training matrix: {len(S.joined)} trades × "
                            f"{len(S.feature_cols)} features")
                    st.caption(f"Baseline win rate to beat: **{d['win_rate']:.1%}**")
                    st.bar_chart(S.trades["exit_reason"].value_counts())

                if "regime" in S.trades.columns:
                    st.subheader("Behaviour by market regime")
                    st.caption("Regime at the signal bar, from data up to that bar only. "
                                "Trend: ADX(14) ≥ 25 → up/down by DI sign, else range. "
                                "Volatility: ATR(14) percentile in its trailing 1500 bars "
                                "(low < ⅓ < normal < ⅔ < high). Alignment: +1 with the trend, "
                                "−1 against it, 0 in a range. Rows with reliable = False have "
                                "too few trades to trust.")
                    view = st.radio("Group by", ["regime", "regime_trend", "regime_vol",
                                                 "regime_alignment"], horizontal=True,
                                    key="label_regime_view")
                    st.dataframe(regime_profile(S.trades, by=view, pip=S.spec.pip),
                                 width="stretch", hide_index=True)


# ===========================================================================
# TAB 5 -- TRAIN
# ===========================================================================
with tabs[4]:
    st.header("Model training (purged walk-forward)")
    if S.joined is None:
        st.warning("Create labels first (tab 4).")
    else:
        c1, c2, c3 = st.columns(3)
        model_name = c1.selectbox("Model", ["HistGradientBoosting", "RandomForest",
                                              "LogisticRegression", "LightGBM (if installed)"])
        n_folds = c2.number_input("Walk-forward folds", 3, 10, 5)
        embargo = c3.number_input("Embargo (bars)", 0, 500, 50)
        calibrate = st.checkbox("Calibrate probabilities (isotonic)", value=True,
                                 help="Required for meaningful probability thresholds.")

        st.caption("Threshold is selected on expected pips, never accuracy — "
                    "payoffs are asymmetric. See docs/04.")

        if st.button("Train", type="primary"):
            with st.spinner("Running purged walk-forward CV..."):
                try:
                    res, oos = train_walk_forward(S.joined, S.feature_cols,
                                                    n_folds=int(n_folds),
                                                    embargo_bars=int(embargo),
                                                    calibrate=calibrate)
                    S.fold_results, S.oos = res, oos
                    S.summary = summarize_folds(res)
                except Exception as e:
                    st.error(f"Training failed: {e}")

        if S.summary and "error" not in S.summary:
            s = S.summary
            c = st.columns(4)
            c[0].metric("Mean AUC", f"{s['mean_auc']:.3f}")
            c[1].metric("Brier", f"{s['mean_brier']:.3f}")
            c[2].metric("Edge (pips)", f"{s['total_edge_pips']:+,.0f}")
            c[3].metric("Folds +ve", f"{s['folds_with_positive_edge']}/{s['n_folds']}")

            if s["folds_with_positive_edge"] >= max(1, int(0.8 * s["n_folds"])):
                st.success("Consistent positive edge across folds.")
            elif s["total_edge_pips"] > 0:
                st.warning("Positive total edge but inconsistent across folds — "
                            "may be one lucky period.")
            else:
                st.error("No edge over the take-all baseline. Do not deploy. "
                          "If this is synthetic data, that is the correct result.")

            st.dataframe(pd.DataFrame(s["per_fold"]), use_container_width=True,
                          hide_index=True)
            st.caption("Each fold's threshold is chosen on out-of-sample predictions from "
                        "an inner walk-forward over that fold's training trades. "
                        "take_all_fallback / threshold 0 means the model found no filter "
                        "that beat taking every signal.")

            if S.oos is not None and "regime" in S.oos.columns:
                st.subheader("Out-of-sample results by regime")
                st.caption("edge_pips < 0 means the model's filter lost money versus taking "
                            "every signal in that regime.")
                view = st.radio("Group by", ["regime", "regime_trend", "regime_vol",
                                             "regime_alignment"], horizontal=True,
                                key="oos_regime_view")
                st.dataframe(regime_oos_report(S.oos, by=view), width="stretch",
                             hide_index=True)
        elif S.summary:
            st.error(S.summary["error"])


# ===========================================================================
# TAB 6 -- VALIDATE
# ===========================================================================
with tabs[5]:
    st.header("Feature & pipeline validation")
    if S.joined is None:
        st.warning("Create labels first (tab 4).")
    else:
        sub = st.radio("Analysis", ["Information Coefficient", "IC stability",
                                      "Redundancy clusters", "Pipeline self-test"],
                        horizontal=True)
        X = S.joined[S.feature_cols]
        y = S.joined["win"]

        if sub == "Information Coefficient":
            if st.button("Compute IC", type="primary"):
                ic = compute_ic(X, y).dropna()
                st.caption("Spearman rank correlation with the label. "
                            "|IC| in 0.05–0.35 is realistic; >0.9 signals leakage.")
                top = ic.head(25).to_frame("IC")
                st.bar_chart(top)
                st.dataframe(top, width="stretch")
                if ic.abs().max() > 0.9:
                    st.error("A feature correlates almost perfectly with the label. "
                              "Investigate for leakage before trusting any result.")

        elif sub == "IC stability":
            w = st.number_input("Rolling window (trades)", 50, 1000, 200)
            if st.button("Compute stability", type="primary"):
                with st.spinner("Rolling IC..."):
                    stab = rolling_ic_stability(X, y, window=int(w), step=max(10, int(w) // 4))
                st.caption("A feature whose IC flips sign often is regime-dependent, "
                            "not universally predictive.")
                st.dataframe(stab.head(30), width="stretch")

        elif sub == "Redundancy clusters":
            thr = st.slider("Correlation threshold", 0.7, 0.99, 0.9)
            if st.button("Find clusters", type="primary"):
                cl = redundancy_clusters(X, corr_threshold=thr)
                st.caption(f"{len(cl)} clusters. Keep the highest-IC member of each.")
                for c in cl:
                    st.code(", ".join(c))

        else:
            st.caption("Two-sided self-test. Null test proves no leakage; signal test "
                        "proves the pipeline can learn. Both must pass. See docs/04.")
            st.code("python -m pytest tests/ -v\n# or\npython tests/validate_pipeline.py",
                     language="bash")
            st.info("Runs on synthetic data and takes several minutes — run it from "
                     "the terminal rather than blocking the GUI.")


# ===========================================================================
# TAB 7 -- BACKTEST
# ===========================================================================
with tabs[6]:
    st.header("Sequential backtest & live parity")
    if S.oos is None:
        st.warning("Train a model first (tab 5).")
    else:
        lots = st.number_input("Lot size", 0.01, 100.0, 0.10, step=0.01)
        bal = st.number_input("Starting balance", 100.0, 10_000_000.0, 10_000.0)

        if st.button("Run backtest", type="primary"):
            cmp_ = compare_model_vs_baseline(S.oos, S.spec, lots=float(lots))
            executed = sequential_backtest(S.oos, use_model_filter=True)
            base_exec = sequential_backtest(S.oos, use_model_filter=False)
            S.backtest = (cmp_, executed, base_exec)

        if S.get("backtest"):
            cmp_, executed, base_exec = S.backtest
            st.caption("The one-position constraint is enforced sequentially here — "
                        "this is what one account could actually have captured.")

            rows = []
            for name, key in [("Model-filtered", "model"), ("Take all (baseline)", "baseline_take_all")]:
                m = cmp_[key]
                if "error" in m:
                    continue
                rows.append({
                    "Strategy": name, "Trades": m["n_trades"],
                    "Win rate": f"{m['win_rate']:.1%}",
                    "Net pips": f"{m['total_net_pips']:+,.0f}",
                    "Profit factor": f"{m['profit_factor']:.2f}",
                    "Max DD %": f"{m['max_drawdown_pct']:.1f}",
                    "Return %": f"{m['return_pct']:+.1f}",
                })
            if rows:
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

                mp = cmp_["model"].get("total_net_pips", 0)
                bp = cmp_["baseline_take_all"].get("total_net_pips", 0)
                if mp > bp:
                    st.success(f"Model beats baseline by {mp - bp:+,.0f} pips.")
                else:
                    st.error(f"Model underperforms baseline by {mp - bp:+,.0f} pips. "
                              f"Filtering is removing winners.")

            if not executed.empty:
                eq = pd.DataFrame({
                    "Model": executed["equity_pips"].values,
                }).reset_index(drop=True)
                st.line_chart(eq, height=300)

            parity = live_parity_checks(S.oos, executed, S.trades)
            st.subheader("Live-parity checks")
            for k, v in parity.items():
                if k in ("all_passed", "failed_checks"):
                    continue
                if isinstance(v, bool):
                    st.write(f"{'✅' if v else '❌'} {k}")
                else:
                    st.write(f"ℹ️ {k}: {v}")
            if parity["all_passed"]:
                st.success("All parity checks passed")
            else:
                st.error(f"Failed: {parity['failed_checks']}")


# ===========================================================================
# TAB 8 -- EXPORT
# ===========================================================================
with tabs[7]:
    st.header("Export for live trading")
    if S.joined is None:
        st.warning("Complete training first.")
    else:
        st.subheader("Go / no-go checklist")
        s = S.summary or {}
        d = diagnose_trades(S.trades, S.cfg, S.spec) if S.trades is not None else {}
        checks = {
            "TP reachable (hit rate > 5%)": d.get("tp_hit_rate", 0) > 0.05,
            "≥300 labeled trades": len(S.joined) >= 300,
            "Positive edge in ≥80% of folds": (
                s.get("folds_with_positive_edge", 0) >= max(1, int(0.8 * s.get("n_folds", 1)))
                if s.get("n_folds") else False),
            "Beats take-all baseline": s.get("total_edge_pips", 0) > 0,
            "Timeout rate < 30%": d.get("timeout_rate", 1) < 0.30,
        }
        for k, v in checks.items():
            st.write(f"{'✅' if v else '❌'} {k}")

        ready = all(checks.values())
        if ready:
            st.success("All criteria met. Forward-test on demo for ≥1 month before live.")
        else:
            st.error("Criteria not met — do not deploy. A strategy with no edge is "
                      "not fixed by a better model.")

        st.divider()
        thr = st.number_input("Deployment threshold", 0.0, 1.0,
                               float(select_deployment_threshold(S.oos))
                               if S.oos is not None else 0.5, step=0.01,
                               help="Default: the threshold that maximises net pips on the "
                                    "pooled walk-forward out-of-sample predictions. "
                                    "0 = take every signal (no filter beat the baseline).")
        name = st.text_input("Model filename", "model_icc_meta.joblib")
        if st.button("Fit final model on all data & save", type="primary"):
            path = ROOT / "models" / name
            path.parent.mkdir(exist_ok=True)
            b = fit_final_model(S.joined, S.feature_cols, float(thr), out_path=str(path),
                                pip=S.spec.pip)
            st.success(f"Saved {path}  ({b['n_training_trades']} trades, "
                        f"{len(b['feature_cols'])} features)")

        st.divider()
        st.subheader("Download datasets")
        c1, c2 = st.columns(2)
        if S.joined is not None:
            c1.download_button("Training matrix (CSV)",
                                S.joined.to_csv(index=False).encode(),
                                "icc_training_matrix.csv", "text/csv")
        if S.oos is not None:
            c2.download_button("OOS predictions (CSV)",
                                S.oos.to_csv(index=False).encode(),
                                "icc_oos_predictions.csv", "text/csv")


# ===========================================================================
# TAB 9 -- FORWARD TESTING DASHBOARD (NEW)
# ===========================================================================
with tabs[8]:
    # Import new forward_test tab
    from forward_test.streamlit_tab9 import render_tab9_realtime
    
    # Render the forward-testing dashboard
    render_tab9_realtime(S, S.spec, S.cfg)

