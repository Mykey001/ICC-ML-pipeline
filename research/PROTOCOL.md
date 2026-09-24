# Strategy optimisation and meta-model protocol

Written **before** any optimisation run. Nothing below is changed after results
are seen; any deviation is recorded in the "Deviations" section with a reason.

## Data

- XAUUSDm H1, broker export 2022-01-16 23:00 → 2026-09-16 12:00 (27,594 bars).
- **Development**: bars with time < 2025-09-16 (21,670 bars). All optimisation,
  model selection and training uses only these.
- **Holdout**: 2025-09-16 → 2026-09-16 (5,924 bars). Evaluated **once**, after
  the strategy configuration, model and threshold are frozen. Indicators may use
  earlier bars for warm-up (causal).
- Known contamination: during the earlier audit, full-period summaries that
  include the holdout were viewed (win rate by year, regime profile). The search
  space below includes a trend filter partly motivated by those summaries.

## Execution model (both periods)

- EA semantics: signal on bar close, market entry at next bar open.
- Prices in the data are bid. Long: fill at ask (open + spread), SL/TP triggered
  on bid. Short: fill at bid, SL/TP triggered on ask (bid + spread). Spread from
  the per-bar `spread` column (0 values replaced by the median).
- Slippage 5 points adverse on the market entry and on stop-loss exits; take
  profit is a limit and fills at its price (or better on a gap).
- Gaps through SL/TP fill at the bar open. SL and TP in the same bar → SL first.
- One position at a time with EA blocking semantics (a setup that triggers while
  a position is open is ignored without resetting the state machine).
- 0.10 lots, commission 0 (preset value; broker commission unknown).

## Search space (EA inputs; new inputs default to current EA behaviour)

| Input | Values |
|---|---|
| HTF_PivotLen | 2, 3, 4 |
| LTF_PivotLen | 1, 2 |
| Stop loss | swing H4, swing D1, off (LTF pivot SL) — SL_SwingPivotLen 2 |
| SL_BufferPips | 0, 200 |
| Take profit (new TP_Mode) | fixed 1500 / 2500 / 4000 pips; R-multiple 0.75 / 1.0 / 1.5 / 2.0 of SL distance; ATR(14) × 3 / 5 / 8 |
| Trend filter (new) | none; EMA(200) on chart timeframe — longs only above, shorts only below |
| Max SL distance (new) | off; 5 × ATR(14); 7 × ATR(14) |

3 × 2 × 3 × 2 × 10 × 2 × 3 = **2,160 configurations**.

## Metric and selection rule

- Per configuration: sequential backtest; net P&L per calendar month (pips).
- Score = mean monthly net pips / std of monthly net pips (monthly Sharpe).
  Configurations averaging fewer than 15 trades per year are ineligible.
- Selection on any set of periods: the eligible configuration with the highest
  score on those periods.

## Honesty checks

1. **Walk-forward of the optimisation process** on development data: half-year
   blocks; for each block from 2023-H1 on, select with the rule above using only
   earlier blocks and record the next block's result. Compare with the current
   default configuration over the same blocks.
2. **Probability of backtest overfitting** (CSCV, 8 time blocks, all 2,160
   configurations).
3. **Random-timing benchmark**: keep each trade's direction and exit rules,
   randomise the entry bar within the same calendar month (1,000 draws);
   p-value = share of draws with total net pips ≥ the strategy's.

## Meta-model

- Trained on independent (non-sequential) signals of the selected configuration,
  development period only. Purged walk-forward with inner-fold thresholds
  (`train.train_walk_forward`).
- Features: engineered features minus raw price levels and history-dependent
  cumulative series (obv, vwap), plus regime features.
- At most three model variants compared on development walk-forward:
  HistGradientBoosting (default), HistGradientBoosting (stronger regularisation),
  logistic regression. Pick the one with the highest total walk-forward edge.
- Deployment threshold: `select_deployment_threshold` on pooled walk-forward OOS.

## Pass criteria (decided now)

Strategy has an edge on development if **all** hold:
- walk-forward process: total OOS net pips > 0 and OOS monthly Sharpe > 0;
- PBO < 0.5;
- random-timing p < 0.05.

Meta-model adds value on development if walk-forward total edge > 0 and edge is
positive in at least 60% of folds.

Holdout (single evaluation): report net pips, profit factor, max drawdown,
monthly Sharpe and random-timing p for the strategy alone and with the model
filter. The strategy "holds up" if holdout net pips > 0 and profit factor > 1.1;
the model "holds up" if model-filtered holdout net pips ≥ unfiltered.

## Deviations

1. The first grid run was stopped before it finished (no results were viewed) and
   restarted to also record trades per month, which walk-forward eligibility
   needs. Search space and backtest were unchanged.
2. An extra, exploratory random-timing benchmark was run on the current default
   configuration after selection, for context. It played no part in selection.
3. The holdout has **not** been evaluated. Both development criteria failed
   (strategy: PBO and random-timing; meta-model: no positive walk-forward edge),
   so the holdout is kept sealed for a future candidate that passes development.
