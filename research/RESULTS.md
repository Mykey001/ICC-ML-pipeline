# Optimisation and meta-model results

Protocol: [PROTOCOL.md](PROTOCOL.md), committed before any run. Development
period 2022-01-16 → 2025-09-15 (XAUUSDm H1). The holdout (2025-09-16 →
2026-09-16) has **not** been used.

## Verdict

**No edge was found.** Neither the optimised ICC strategy nor the meta-model
passed the pre-registered development criteria, so nothing here should be
deployed, and the holdout was left sealed.

## 1. Strategy optimisation (2,160 EA configurations)

Sequential single-account backtests with real per-bar spread, slippage and EA
position blocking. 1,583 configurations met the minimum-trade rule. 360
configurations (HTF_PivotLen = LTF_PivotLen = 2) can never trade: the LTF and HTF
pivots coincide, so the EA's SL rule `ltf_sup > htf_sup` never holds.

Best in-sample configuration: **HTF 3 / LTF 1, LTF-pivot SL, TP 4000 pips,
MaxSL 5 × ATR**: 465 trades, +97,017 pips, profit factor 1.26, monthly Sharpe 0.47,
win rate 25%. The current default: 344 trades, +54,025 pips, profit factor 1.12,
monthly Sharpe 0.12.

| Honesty check | Result | Criterion | Pass |
|---|---|---|---|
| Walk-forward of the selection process (6 half-years) | +35,356 OOS pips, monthly Sharpe 0.13 | > 0 | yes |
| … same blocks with the untouched default | +49,969 pips, Sharpe 0.14 | (reference) | optimising did worse |
| Probability of backtest overfitting (CSCV, 70 splits) | 0.54 | < 0.5 | **no** |
| Random-timing benchmark (1,000 draws) | p = 0.31 (random mean +73,949 pips) | < 0.05 | **no** |

The selected configuration changed from half-year to half-year and alternated
between winning and losing blocks. A PBO above 0.5 means the in-sample winner is
more likely than not to be below median out of sample.

Exploratory (not used for selection): the default configuration's entries are
*worse* than random entries with the same direction and exits (p = 0.82; random
mean +102,838 vs +54,025 pips). All of its profit is on the long side (longs
+87,932, shorts −33,907 pips), consistent with gold's 2022–2025 rally rather than
entry skill.

## 2. Meta-model (selected strategy, independent signals)

744 labeled trades × 216 features (raw price levels, obv and vwap excluded;
regime features included). Purged walk-forward, 5 folds, inner-fold thresholds.

| Variant | Mean AUC | Walk-forward edge vs take-all | Folds with +edge |
|---|---|---|---|
| HistGradientBoosting | 0.572 | −16,606 pips | 1/5 |
| HistGradientBoosting (regularised) | 0.578 | −39,050 pips | 0/5 |
| Logistic regression | 0.575 | −27,048 pips | 0/5 |

Criterion (total edge > 0 and positive in ≥ 60% of folds): **not met**. The
models rank trades slightly better than chance, but with a 23% win rate the
profit comes from a few large winners; any filter that removes losers also
removes enough winners to lose money. Edge was negative in every trend and
volatility regime. The pooled-OOS deployment threshold is 0.0 (do not filter).

`models/model_icc_meta_v2.joblib` was saved as the protocol requires, but its
threshold is 0.0 and it must not be deployed as a filter.

## Reproduce

```bash
python research/01_grid_search.py        # ~12 min on 4 cores
python research/02_select_strategy.py
python research/03_train_meta_model.py
# research/04_holdout.py - single use; only for a candidate that passes development
```
