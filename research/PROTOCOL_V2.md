# Protocol v2: expected-value meta-model

Written before any v2 code or run. Same data split, execution model and sealed
holdout as [PROTOCOL.md](PROTOCOL.md). The development period has already been
used by v1; the holdout has not.

## Hypothesis

A meta-model that estimates each ICC trade's **expected net pips** (using its
own stop distance) can choose trades that beat both taking every trade and a
naive long-only rule, for one account trading the EA.

v1 thresholded a win probability, which treats a trade risking 1,200 pips the
same as one risking 8,000. v2 uses the payoff structure explicitly.

## Base strategy

The **current default EA configuration** (HTF 2 / LTF 1, H4 swing SL, TP 2500
pips, no filters). The v1-selected configuration is not used: its selection
failed the overfitting checks.

## Training data

Independent (non-sequential) signals of the base strategy on development data,
labeled with the realistic simulator. Features: the v1 feature set (engineered
features minus raw price levels, obv, vwap; plus regime features), plus
trade-specific inputs known at signal time: direction, SL distance in pips
(from the signal bar's close), SL distance in ATR.

## Two variants (no others)

- **EV-classifier**: calibrated regularised HistGradientBoosting classifier for
  P(win); expected pips = p × TP distance − (1 − p) × SL distance − median
  round-trip cost (spread + slippage), all in pips.
- **R-regressor**: regularised HistGradientBoosting regressor on
  R = net pips / SL distance in pips; expected pips = predicted R × SL distance.

Decision: take the trade if expected pips > τ.

## Threshold τ

Chosen per fold on inner walk-forward OOS predictions (3 inner folds over that
fold's training rows): candidates are "take all" and the 10th…90th percentiles
of the inner expected-pips values; the candidate maximising inner net pips wins,
subject to taking at least 25% of inner trades. Deployment τ: same rule on the
pooled outer-fold OOS values.

## Evaluation (development)

Purged walk-forward, 5 folds, embargo 50 bars (`train._walk_forward_splits`).
For each test fold, one continuous **sequential** backtest over development data
with the filter active only on test-fold bars (take all elsewhere); count trades
signalled inside the fold. Same for two baselines: take all, and long-only (take
only longs inside the fold).

Variant chosen by total sequential edge over take-all.

## Pass criteria (development)

All of:
1. total sequential P&L of the chosen variant > take-all **and** > long-only;
2. edge over take-all positive in ≥ 3 of 5 folds;
3. permutation test p < 0.05: 20 runs with training labels shuffled, each
   repeating the full procedure including the choice between both variants;
   p = (1 + #runs with edge ≥ actual) / 21.

## Holdout (only if all three pass)

Final model on all development trades; deployment τ; one sequential backtest on
full history with the filter switched on at the holdout start. Report net pips,
profit factor, max drawdown and monthly Sharpe for: model filter, take-all,
long-only. "Holds up" if the model filter beats both baselines on holdout net
pips.

## Deviations

1. Implementation detail, not a protocol change: `ea_backtest.run_sequential_backtest`'s
   `take_signal` callback now also receives the signal's SL price and ATR, which the
   expected-pips filter needs.
2. Result: development criteria 1 and 3 failed (see RESULTS.md), so the holdout was
   not evaluated.
