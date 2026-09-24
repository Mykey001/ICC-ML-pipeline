"""
Step 2: select the strategy configuration and run the honesty checks (PROTOCOL.md).

- Selection rule: highest monthly Sharpe among configurations averaging >= 15
  trades per year over the months used for selection.
- Walk-forward of the selection process over half-year blocks (anchored).
- Probability of backtest overfitting (CSCV, 8 blocks).
- Random-timing benchmark for the selected configuration.

Development data only. Writes research/results/selection.json.
"""

from __future__ import annotations
import itertools
import json

import numpy as np
import pandas as pd

from common import (RESULTS, SPEC, EXEC, MIN_TRADES_PER_YEAR, load_data, development,
                    to_config, config_label, monthly_sharpe)
from icc_ml.ea_backtest import run_sequential_backtest, monthly_pnl, summarize_backtest
from icc_ml.icc_labeling import market_arrays, simulate_position
from icc_ml.strategy_icc import mt5_atr

DEFAULT = dict(htf_pivot_len=2, ltf_pivot_len=1, sl="swing_h4", sl_buffer_pips=0, tp_kind="fixed",
               tp_mode="fixed_pips", tp_pips=2500.0, trend_filter="none", max_sl_atr=0.0)


def load_grid():
    monthly = pd.read_csv(RESULTS / "grid_monthly.csv", index_col=0)
    counts = pd.read_csv(RESULTS / "grid_monthly_trades.csv", index_col=0)
    configs = pd.read_csv(RESULTS / "grid_configs.csv").set_index("config_id")
    return monthly, counts, configs


def select(monthly: pd.DataFrame, counts: pd.DataFrame, cols) -> tuple:
    """Apply the selection rule on the given months; returns (config_id, scores)."""
    years = len(cols) / 12
    eligible = counts[cols].sum(axis=1) >= MIN_TRADES_PER_YEAR * years
    scores = monthly_sharpe(monthly[cols]).where(eligible)
    return scores.idxmax(), scores


def half_year(col: str) -> str:
    y, m = col.split("-")
    return f"{y}H{1 if int(m) <= 6 else 2}"


def walk_forward(monthly, counts, default_id):
    blocks = pd.Series([half_year(c) for c in monthly.columns], index=monthly.columns)
    order = list(dict.fromkeys(blocks))
    rows, proc, dflt = [], [], []
    for k, blk in enumerate(order):
        if blk < "2023H1":
            continue
        train = [c for c in monthly.columns if blocks[c] in order[:k]]
        test = [c for c in monthly.columns if blocks[c] == blk]
        cid, _ = select(monthly, counts, train)
        proc.append(monthly.loc[cid, test])
        dflt.append(monthly.loc[default_id, test])
        rows.append({"test_block": blk, "selected_config": int(cid),
                     "selected_pips": float(monthly.loc[cid, test].sum()),
                     "default_pips": float(monthly.loc[default_id, test].sum())})
    proc, dflt = pd.concat(proc), pd.concat(dflt)
    return rows, {"process_oos_pips": float(proc.sum()), "process_oos_monthly_sharpe": float(monthly_sharpe(proc)),
                  "default_oos_pips": float(dflt.sum()), "default_oos_monthly_sharpe": float(monthly_sharpe(dflt))}


def pbo(monthly, counts, n_blocks=8):
    groups = np.array_split(np.arange(monthly.shape[1]), n_blocks)
    logits = []
    for is_blocks in itertools.combinations(range(n_blocks), n_blocks // 2):
        is_cols = monthly.columns[np.concatenate([groups[b] for b in is_blocks])]
        oos_cols = monthly.columns[np.concatenate([groups[b] for b in range(n_blocks) if b not in is_blocks])]
        best, is_scores = select(monthly, counts, is_cols)
        oos_scores = monthly_sharpe(monthly[oos_cols])[is_scores.notna()].fillna(-np.inf)
        rank = (oos_scores < oos_scores[best]).sum() + 0.5 * ((oos_scores == oos_scores[best]).sum() - 1) + 1
        w = rank / (len(oos_scores) + 1)
        logits.append(np.log(w / (1 - w)))
    logits = np.array(logits)
    return {"pbo": float((logits <= 0).mean()), "n_splits": len(logits), "median_logit": float(np.median(logits))}


def random_timing(dev, cfg, trades, n_draws=1000, seed=0):
    """Same trades, same direction and SL distance, entry bar randomised within the month."""
    m = market_arrays(dev, SPEC)
    atr = mt5_atr(dev, cfg.atr_period)
    close = dev["close"].to_numpy()
    month = dev["time"].dt.to_period("M").to_numpy()
    bars_by_month = {p: np.flatnonzero(month == p) for p in np.unique(month)}
    rng = np.random.default_rng(seed)
    base = []
    for t in trades.itertuples():
        s = t.signal_bar
        pool = bars_by_month[month[s]]
        pool = pool[(pool < len(dev) - 1) & ~np.isnan(atr[pool])]
        base.append((t.direction, abs(close[s] - t.sl_price), pool))
    totals = np.empty(n_draws)
    for k in range(n_draws):
        total = 0.0
        for d, risk, pool in base:
            r = rng.choice(pool)
            res = simulate_position(m, r, d, close[r] - d * risk, atr[r], cfg, SPEC, EXEC)
            if res is not None and res["exit_reason"] != "open_at_end":
                total += res["net_pips"]
        totals[k] = total
    actual = float(trades["net_pips"].sum())
    return {"strategy_pips": actual, "random_mean_pips": float(totals.mean()),
            "random_p95_pips": float(np.percentile(totals, 95)), "p_value": float((totals >= actual).mean()),
            "n_draws": n_draws}


def main():
    monthly, counts, configs = load_grid()
    match = np.ones(len(configs), bool)
    for k, v in DEFAULT.items():
        match &= (configs[k] == v).to_numpy()
    default_id = int(configs.index[match][0])

    chosen, scores = select(monthly, counts, list(monthly.columns))
    top = scores.sort_values(ascending=False).head(10)
    wf_rows, wf = walk_forward(monthly, counts, default_id)
    overfit = pbo(monthly, counts)

    dev = development(load_data())
    p = {k: v for k, v in configs.loc[chosen].to_dict().items() if k in list(DEFAULT) + ["tp_r_multiple", "tp_atr_mult"]}
    p = {k: v for k, v in p.items() if not (isinstance(v, float) and np.isnan(v))}
    cfg = to_config(p)
    trades = run_sequential_backtest(dev, cfg, SPEC, EXEC)
    stats = summarize_backtest(trades, monthly_pnl(trades, dev["time"]))
    bench = random_timing(dev, cfg, trades)

    passed = {
        "walk_forward_oos_pips_positive": wf["process_oos_pips"] > 0,
        "walk_forward_oos_sharpe_positive": wf["process_oos_monthly_sharpe"] > 0,
        "pbo_below_0.5": overfit["pbo"] < 0.5,
        "random_timing_p_below_0.05": bench["p_value"] < 0.05,
    }
    out = {
        "chosen_config_id": int(chosen), "chosen_params": p, "chosen_label": config_label(p),
        "chosen_dev_stats": stats, "default_config_id": default_id,
        "default_dev_stats": configs.loc[default_id, ["n_trades", "net_pips", "profit_factor", "monthly_sharpe",
                                                       "max_drawdown_pips", "win_rate"]].to_dict(),
        "top10": [{"config_id": int(i), "score": float(s), "label": config_label(configs.loc[i].to_dict()),
                   "n_trades": int(configs.loc[i, "n_trades"]), "net_pips": float(configs.loc[i, "net_pips"])}
                  for i, s in top.items()],
        "n_eligible": int(scores.notna().sum()),
        "walk_forward": wf, "walk_forward_blocks": wf_rows, "pbo": overfit, "random_timing": bench,
        "pass": passed, "edge_on_development": all(passed.values()),
    }
    (RESULTS / "selection.json").write_text(json.dumps(out, indent=2, default=float))
    print(json.dumps(out, indent=2, default=float))


if __name__ == "__main__":
    main()
