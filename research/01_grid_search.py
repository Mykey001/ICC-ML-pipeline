"""
Step 1: sequential backtest of all 2,160 configurations on the development period.

Writes research/results/grid_monthly.csv (configs x months, net pips by exit month),
research/results/grid_monthly_trades.csv (configs x months, trades by exit month)
and research/results/grid_configs.csv (parameters, trade count, headline stats).
Holdout bars are never loaded here.
"""

from __future__ import annotations
import time
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from common import RESULTS, SPEC, EXEC, load_data, development, search_space, to_config
from icc_ml.ea_backtest import run_sequential_backtest, monthly_pnl, summarize_backtest

_DEV = None
_MONTHS = None


def _init():
    global _DEV, _MONTHS
    _DEV = development(load_data())
    _MONTHS = pd.period_range(_DEV["time"].iloc[0], _DEV["time"].iloc[-1], freq="M")


def _run(args):
    cid, params = args
    trades = run_sequential_backtest(_DEV, to_config(params), SPEC, EXEC)
    monthly = monthly_pnl(trades, _DEV["time"], _MONTHS)
    counts = monthly_pnl(trades.assign(net_pips=1.0), _DEV["time"], _MONTHS)
    return cid, monthly.to_numpy(), counts.to_numpy(), summarize_backtest(trades, monthly)


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    grid = search_space()
    _init()
    t0 = time.time()
    rows, monthly, counts = [], {}, {}
    with ProcessPoolExecutor(max_workers=4, initializer=_init) as pool:
        for k, (cid, m, c, stats) in enumerate(pool.map(_run, enumerate(grid), chunksize=8), 1):
            monthly[cid], counts[cid] = m, c
            rows.append({"config_id": cid, **grid[cid], **stats})
            if k % 200 == 0:
                print(f"{k}/{len(grid)} configs, {time.time() - t0:.0f}s", flush=True)
    months = _MONTHS.astype(str)
    pd.DataFrame(monthly, index=months).T.sort_index().to_csv(RESULTS / "grid_monthly.csv", index_label="config_id")
    pd.DataFrame(counts, index=months).T.sort_index().to_csv(RESULTS / "grid_monthly_trades.csv", index_label="config_id")
    pd.DataFrame(rows).sort_values("config_id").to_csv(RESULTS / "grid_configs.csv", index=False)
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
