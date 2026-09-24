# 03 — Labeling and Meta-Labeling

## Why meta-labeling

There are two ways to apply ML to a trading strategy:

| Approach | Target | Difficulty |
|---|---|---|
| Direct prediction | "Which way will price go?" | Very hard — low signal-to-noise, unstable |
| **Meta-labeling** | "Should I take *this* signal?" | Much easier — binary, conditioned on a setup |

We use meta-labeling, following López de Prado. The division of labour:

- **Primary model** = the ICC strategy. Decides *direction* and *when*. Rule-based, unchanged.
- **Meta-model** = the ML classifier. Decides *take or skip*. Learns from market state.

This matters because the ICC strategy already encodes real structural logic. The
model's job is not to replace it but to learn *which market conditions make its
signals work* — and to suppress the rest. That directly serves the stated goal:
**take trades that reach the take-profit target, filter signals that end in losses.**

---

## The label

For every ICC signal, we simulate the trade to its real conclusion using the
strategy's own exit rules — the swing stop and the `tp_pips` target — and record:

```
win = 1  if net_pips > 0  (after spread, slippage, commission)
win = 0  otherwise
```

### Why not generic triple-barrier?

A generic ATR-barrier label asks a question the live system never asks. The live
EA exits at a structural swing stop or a 2500-pip target. If the model is trained
on ±1.5 ATR barriers, it learns to predict an event that will never occur in
production. **Train/live divergence is guaranteed regardless of feature quality.**

The generic implementation remains in `labeling.py` for research use, but the
production path is `icc_labeling.simulate_icc_trades()`.

---

## Execution realism

Every assumption below exists to stop the backtest flattering itself. These are,
in order, the most common sources of a backtest that cannot be reproduced live:

| Assumption | Implementation |
|---|---|
| Fill at next bar open | `entry_price = open[t+1]`, never `close[t]` |
| Spread | Applied on both entry and exit |
| Slippage | Adverse on both sides, `slippage_points` |
| Commission | Per-lot round turn, converted to pips |
| **SL and TP in the same bar** | **Assume SL first** |

That last one deserves emphasis. When a bar's high/low range contains both
levels, OHLC data cannot tell you which was touched first. Assuming TP is the
classic way backtests invent profit that does not exist. The pessimistic
assumption is configurable via `both_hit_same_bar_policy` but should stay at
`"sl_first"` for any result you intend to trade.

---

## Labeling mode vs backtest mode

This is a deliberate and important design decision.

`simulate_icc_trades(..., enforce_one_position=False|True)`

### Labeling mode (`False`) — for building the training set

Every signal is simulated independently, as though capital were unlimited.

**Rationale.** The meta-model learns "is this setup good?" That is a property of
*market state at the signal bar*. Whether an unrelated earlier trade happened to
still be open is a property of *trade history*, not of the setup. Enforcing the
block during labeling would:

1. Discard ~90% of training data (measured: 253 signals → 18 usable)
2. Make the label depend on scheduling luck rather than market conditions —
   an unlearnable target

### Backtest mode (`True`) — for measuring realised P&L

Applies the EA's `HasOpenPosition()` block sequentially, so reported returns
reflect what one account could actually have captured.

**Summing the P&L of all model-approved trades without this constraint reports
money no single account could have made.**

---

## Diagnostics before training

`diagnose_trades()` runs automatically and raises warnings for:

| Check | Threshold | Why |
|---|---|---|
| `tp_hit_rate` | < 2% | TP unreachable for this symbol's pip convention |
| `timeout_rate` | > 30% | Too many labels decided by an arbitrary timeout |
| `n_taken` | < 100 | Too few trades for walk-forward to mean anything |

Resolve every warning before training. A model trained on degenerate labels will
still produce confident-looking output.

---

## Class balance

Measured baseline win rate on synthetic XAUUSD H1: **37–44%**.

That is the number the model must beat. A meta-model reporting 55% accuracy has
added nothing if the unfiltered strategy already won 55% of the time. Every
reported result is therefore accompanied by the take-all baseline.
