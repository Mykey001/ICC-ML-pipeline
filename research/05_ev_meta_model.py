"""
Protocol v2 (research/PROTOCOL_V2.md): expected-value meta-model on the default
EA configuration, evaluated in one-account (sequential) walk-forward against
take-all and long-only baselines, plus a label-permutation test.

Development data only. Writes research/results/v2_ev_model.json.
"""

from __future__ import annotations
import importlib
import json
import os
import time
import warnings
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

from common import RESULTS, SPEC, EXEC, load_data, development, to_config
from icc_ml.ea_backtest import run_sequential_backtest, monthly_pnl, summarize_backtest
from icc_ml.regime import regime_alignment
from icc_ml.strategy_icc import mt5_atr
from icc_ml.train import _walk_forward_splits

warnings.filterwarnings("ignore")
step2 = importlib.import_module("02_select_strategy")
step3 = importlib.import_module("03_train_meta_model")

CFG = to_config(step2.DEFAULT)
HGB = dict(max_iter=200, learning_rate=0.05, max_depth=3, min_samples_leaf=40, l2_regularization=1.0, random_state=42)
VARIANTS = ("ev_classifier", "r_regressor")
TRADE_COLS = ["trade_direction", "risk_pips", "risk_atr"]
N_FOLDS, N_INNER, EMBARGO, MIN_TAKE = 5, 3, 50, 0.25
N_PERMUTATIONS = 20


# ---- data -------------------------------------------------------------------

class Data:
    """Development bars, per-bar features, and the labeled independent trades."""

    def __init__(self):
        full = load_data()
        self.dev = development(full)
        features, regimes = step3.build_feature_frame(full)
        n = len(self.dev)
        self.close = self.dev["close"].to_numpy()
        self.atr = mt5_atr(self.dev, CFG.atr_period)
        self.trend_code = regimes["regime_trend_code"].to_numpy()[:n]
        joined, cols = step3.training_matrix(self.dev, features, regimes, CFG)
        bar_cols = [c for c in cols if c != "regime_alignment"]
        self.bar_matrix = (features.join(regimes[["regime_vol_rank", "regime_vol_code", "regime_trend_code"]])
                           [bar_cols].iloc[:n].to_numpy(dtype=float))
        self.bar_cols = bar_cols
        self.cols = bar_cols + ["regime_alignment"] + TRADE_COLS
        s = joined["signal_bar"].to_numpy()
        joined["trade_direction"] = joined["direction"]
        joined["risk_pips"] = np.abs(self.close[s] - joined["sl_price"].to_numpy()) / SPEC.pip
        joined["risk_atr"] = np.abs(self.close[s] - joined["sl_price"].to_numpy()) / self.atr[s]
        joined["R"] = joined["net_pips"] / joined["risk_pips"]
        self.trades = joined.sort_values("signal_bar").reset_index(drop=True)
        spread = self.dev["spread"].to_numpy(dtype=float)
        self.cost_pips = (np.median(spread[spread > 0]) * SPEC.point + 2 * EXEC.slippage_points * SPEC.point) / SPEC.pip
        self.tp_pips = CFG.tp_pips

    def row(self, bar: int, direction: int, sl_price: float, atr: float) -> np.ndarray:
        """Model input for a live signal, built exactly like the training rows."""
        risk = abs(self.close[bar] - sl_price)
        extra = [regime_alignment(direction, self.trend_code[bar]), direction, risk / SPEC.pip, risk / atr]
        return np.r_[self.bar_matrix[bar], extra]


# ---- variants ---------------------------------------------------------------

def fit(variant: str, t: pd.DataFrame, cols):
    X = t[cols]
    if variant == "ev_classifier":
        model = HistGradientBoostingClassifier(**HGB)
        if len(t) >= 100 and t["win"].value_counts().min() >= 3:
            model = CalibratedClassifierCV(model, method="isotonic", cv=3)
        return model.fit(X, t["win"])
    return HistGradientBoostingRegressor(**HGB).fit(X, t["R"])


def expected_pips(variant, model, X: np.ndarray, risk_pips: np.ndarray, d: Data) -> np.ndarray:
    if variant == "ev_classifier":
        p = model.predict_proba(X)[:, 1]
        return p * d.tp_pips - (1 - p) * risk_pips - d.cost_pips
    return model.predict(X) * risk_pips


def choose_tau(values: np.ndarray, pips: np.ndarray) -> float:
    """Inner-OOS threshold: take-all or a 10..90th percentile, max pips, >= 25% taken."""
    if len(values) < 50:
        return -np.inf
    best_tau, best = -np.inf, pips.sum()
    for q in range(10, 100, 10):
        tau = np.percentile(values, q)
        mask = values > tau
        if mask.mean() >= MIN_TAKE and pips[mask].sum() > best:
            best_tau, best = tau, pips[mask].sum()
    return best_tau


def inner_tau(variant, train: pd.DataFrame, d: Data) -> float:
    train = train.reset_index(drop=True)
    vals, pips = [], []
    for _, tr, te in _walk_forward_splits(train, N_INNER, EMBARGO):
        if len(tr) < 30 or train.loc[tr, "win"].nunique() < 2:
            continue
        m = fit(variant, train.loc[tr], d.cols)
        te_rows = train.loc[te]
        vals.append(expected_pips(variant, m, te_rows[d.cols].to_numpy(dtype=float), te_rows["risk_pips"].to_numpy(), d))
        pips.append(te_rows["net_pips"].to_numpy())
    if not vals:
        return -np.inf
    return choose_tau(np.concatenate(vals), np.concatenate(pips))


# ---- sequential walk-forward -------------------------------------------------

def fold_blocks(trades: pd.DataFrame):
    """(fold, train_idx, first_bar, last_bar) for each outer fold."""
    for fold, tr, te in _walk_forward_splits(trades, N_FOLDS, EMBARGO):
        yield fold, tr, int(trades.loc[te[0], "signal_bar"]), int(trades.loc[te[-1], "signal_bar"])


def sequential_pips(d: Data, first: int, last: int, take=None) -> float:
    """Net pips of trades signalled in [first, last] with `take` active only there."""
    def flt(bar, direction, sl, atr):
        return True if (take is None or not first <= bar <= last) else take(bar, direction, sl, atr)
    t = run_sequential_backtest(d.dev, CFG, SPEC, EXEC, take_signal=flt)
    return float(t.loc[(t["signal_bar"] >= first) & (t["signal_bar"] <= last), "net_pips"].sum())


def evaluate(d: Data, trades: pd.DataFrame, variants=VARIANTS, baselines=True) -> dict:
    """Run the full v2 procedure on `trades` (possibly with permuted outcomes)."""
    out = {v: [] for v in variants}
    if baselines:
        out["take_all"], out["long_only"] = [], []
    oos = {v: [] for v in variants}
    for fold, tr, first, last in fold_blocks(trades):
        train = trades.loc[tr]
        for v in variants:
            model = fit(v, train, d.cols)
            tau = inner_tau(v, train, d)

            def take(bar, direction, sl, atr, v=v, model=model, tau=tau):
                x = d.row(bar, direction, sl, atr).reshape(1, -1)
                return expected_pips(v, model, x, np.array([abs(d.close[bar] - sl) / SPEC.pip]), d)[0] > tau

            out[v].append(sequential_pips(d, first, last, take))
            te_rows = trades[(trades["signal_bar"] >= first) & (trades["signal_bar"] <= last)]
            oos[v].append(pd.DataFrame({
                "value": expected_pips(v, model, te_rows[d.cols].to_numpy(dtype=float), te_rows["risk_pips"].to_numpy(), d),
                "net_pips": te_rows["net_pips"].to_numpy()}))
        if baselines:
            out["take_all"].append(sequential_pips(d, first, last))
            out["long_only"].append(sequential_pips(d, first, last, lambda b, dr, s, a: dr == 1))
    return {"fold_pips": out, "oos": {v: pd.concat(x, ignore_index=True) for v, x in oos.items()}}


_D = None


def _perm_init():
    global _D
    os.environ["OMP_NUM_THREADS"] = "1"
    _D = Data()


def _perm_run(seed: int) -> float:
    """Edge over take-all of the better variant after shuffling training outcomes."""
    rng = np.random.default_rng(seed)
    t = _D.trades.copy()
    perm = rng.permutation(len(t))
    for c in ("win", "net_pips", "R"):
        t[c] = t[c].to_numpy()[perm]
    res = evaluate(_D, t, baselines=False)["fold_pips"]
    return max(sum(res[v]) for v in VARIANTS)


def main():
    t0 = time.time()
    d = Data()
    print(f"{len(d.trades)} trades x {len(d.cols)} features; base win rate {d.trades['win'].mean():.3f}; "
          f"cost {d.cost_pips:.1f} pips; setup {time.time() - t0:.0f}s", flush=True)

    res = evaluate(d, d.trades)
    fp = res["fold_pips"]
    take_all, long_only = sum(fp["take_all"]), sum(fp["long_only"])
    edges = {v: sum(fp[v]) - take_all for v in VARIANTS}
    best = max(VARIANTS, key=edges.get)
    print({k: [round(x) for x in v] for k, v in fp.items()}, f"{time.time() - t0:.0f}s", flush=True)

    # Permutation null: the take-all total is the same in every permuted run
    with ProcessPoolExecutor(max_workers=4, initializer=_perm_init) as pool:
        perm_best = list(pool.map(_perm_run, range(N_PERMUTATIONS)))
    perm_edges = [p - take_all for p in perm_best]
    p_value = (1 + sum(e >= edges[best] for e in perm_edges)) / (N_PERMUTATIONS + 1)

    folds_positive = sum(a > b for a, b in zip(fp[best], fp["take_all"]))
    passed = {
        "beats_take_all_and_long_only": sum(fp[best]) > take_all and sum(fp[best]) > long_only,
        "edge_positive_in_3_of_5_folds": folds_positive >= 3,
        "permutation_p_below_0.05": p_value < 0.05,
    }
    oos = res["oos"][best]
    deploy_tau = choose_tau(oos["value"].to_numpy(), oos["net_pips"].to_numpy())
    out = {
        "base_strategy": "default EA configuration", "n_trades": len(d.trades), "n_features": len(d.cols),
        "fold_pips": fp, "totals": {k: float(sum(v)) for k, v in fp.items()},
        "edge_vs_take_all": edges, "chosen_variant": best, "folds_edge_positive": folds_positive,
        "permutation_edges": perm_edges, "permutation_p": p_value,
        "deployment_tau": float(deploy_tau), "pass": passed, "passes_development": all(passed.values()),
        "runtime_s": time.time() - t0,
    }
    (RESULTS / "v2_ev_model.json").write_text(json.dumps(out, indent=2, default=float))
    print(json.dumps(out, indent=2, default=float))


if __name__ == "__main__":
    main()
