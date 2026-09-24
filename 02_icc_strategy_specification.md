# 02 — ICC Strategy Specification

Formal specification of the ICC Swing strategy as implemented in
`ea/ICC_Swing_EA_Simplified.mq5` and ported to `src/icc_ml/strategy_icc.py`.

This document is the contract between the two implementations. If they ever
disagree, this file defines which is correct.

---

## Concept

ICC = **Indication → Correction → Continuation**. A three-phase state machine:

1. **Indication** — price breaks a higher-timeframe structural level, signalling
   a possible regime shift
2. **Correction** — price pulls back, forming a finer-timeframe pivot that
   becomes the trigger level
3. **Continuation** — price breaks back through that trigger in the original
   direction; this is the entry

Both "HTF" and "LTF" pivots are computed on the **same chart timeframe**; only
the pivot *length* differs (2 bars vs 1 bar). This matches the original
TradingView indicator's behaviour.

---

## Pivot definition

A pivot high at bar `c` with length `L` requires:

```
high[c] > high[c-i]  AND  high[c] > high[c+i]    for all i in 1..L
```

Strict inequality on both sides. Pivot low is the mirror image with `low` and `<`.

### Confirmation lag (critical)

A pivot at bar `c` cannot be known until `L` bars later. The EA checks exactly
one candidate per closed bar: at as-series shift `1+L`, i.e. `L` bars before the
just-closed bar.

The Python port replicates this exactly — at chronological bar `t` it tests
candidate index `t - L`. **A pivot is never available before it would have been
knowable live.** This is the single most important fidelity requirement in the
port.

---

## State machine

| Stage | Meaning |
|---|---|
| `0` | Neutral — no active setup |
| `1` | Bullish indication (HTF resistance broken upward) |
| `2` | Bullish correction — trigger zone armed |
| `-1` | Bearish indication (HTF support broken downward) |
| `-2` | Bearish correction — trigger zone armed |

### Transitions

**Indication (0 → ±1)**

```
bull_break = close[t-1] < htf_res_prev  AND  close[t] > htf_res
bear_break = close[t-1] > htf_sup_prev  AND  close[t] < htf_sup
```

This is Pine's `crossover(x, y)` semantics. `htf_res_prev` is snapshotted
*before* the current bar's pivot updates are applied; `htf_res` is the value
*after*. Preserving that ordering is required for the port to match.

**Correction (±1 → ±2)**

- From stage `1`: track running max of `high`; when an LTF pivot **high**
  confirms → stage `2`, `trigger_zone = ltf_res`
- From stage `-1`: track running min of `low`; when an LTF pivot **low**
  confirms → stage `-2`, `trigger_zone = ltf_sup`

**In correction (stage ±2)**

- *Invalidation*: stage `2` resets to `0` if `close < htf_sup`; stage `-2`
  resets if `close > htf_res`
- *Stop tracking*: stage `2` sets `sl_level = ltf_sup` when a new LTF pivot low
  confirms above `htf_sup`; mirrored for stage `-2`
- *Trigger trailing*: each new LTF pivot in the trend direction updates
  `trigger_zone`

**Entry (±2 → signal)**

```
long_cond  = stage ==  2 AND close[t-1] < trigger_zone_prev AND close[t] > trigger_zone
short_cond = stage == -2 AND close[t-1] > trigger_zone_prev AND close[t] < trigger_zone
```

Both require a valid `sl_level`. After either fires, **stage resets to 0 and
`sl_level` clears regardless of whether the order was actually placed** — the
port replicates this so signal timing cannot drift between implementations.

---

## Stop loss

Two modes, controlled by `use_custom_swing_sl`:

**Custom swing SL (default).** Searches a separate, usually higher timeframe
(default H4) for the most recent confirmed swing point on the correct side of
entry, walking back through up to `sl_max_candidates` pivots. Applies
`sl_buffer_pips`. Only swings whose confirmation time is at or before the signal
bar are eligible.

**Fallback.** If no valid swing is found, uses the LTF-pivot `sl_level` — unless
`require_custom_swing_sl` is true, in which case the signal is rejected.

---

## Take profit

Fixed distance from entry: `tp_pips × pip_size`.

### Pip convention — read this before changing symbols

`PipSize()` returns `10 × point` on 3/5-digit quotes and `1 × point` otherwise.
The default `tp_pips = 2500` therefore means very different things:

| Symbol | Digits | Pip | 2500 pips | Verdict |
|---|---|---|---|---|
| XAUUSD | 2 | 0.01 | $25.00 | Sane swing target |
| US30 | 2 | 0.01 | 25 points | Sane |
| EURUSD | 5 | 0.0001 | 0.2500 | **Unreachable** |
| GBPUSD | 5 | 0.0001 | 0.2500 | **Unreachable** |

Measured on synthetic data: EURUSD-scaled gave a **0% TP hit rate** (every trade
resolved at the stop); XAUUSD-scaled gave **44%**.

`icc_labeling.diagnose_trades()` emits a warning whenever `tp_hit_rate < 2%`.
Never ignore it.

---

## Execution timing

The EA acts inside `OnTick()` after a bar closes, so the fill occurs at the
**open of the next bar**, not at the signal bar's close.

```
bar t      : signal generated (all features computed from data up to close[t])
bar t+1    : position opened at open[t+1] ± spread ± slippage
bar t+1..N : SL/TP monitored intrabar via high/low
```

Filling at `close[t]` would be lookahead and would materially inflate results.

---

## Parameter reference

| Parameter | Default | Python field |
|---|---|---|
| HTF_PivotLen | 2 | `htf_pivot_len` |
| LTF_PivotLen | 1 | `ltf_pivot_len` |
| TP_Pips | **2500** | `tp_pips` |
| UseCustomSwingSL | true | `use_custom_swing_sl` |
| SL_SwingTimeframe | H4 | `sl_swing_timeframe` |
| SL_SwingPivotLen | 2 | `sl_swing_pivot_len` |
| SL_MaxCandidates | 20 | `sl_max_candidates` |
| SL_BufferPips | 0 | `sl_buffer_pips` |
| RequireCustomSwingSL | false | `require_custom_swing_sl` |
| OnePositionAtATime | true | `one_position_at_a_time` |
| FixedLots | 0.10 | `fixed_lots` |

---

## Known behavioural consequence

With a 2500-pip target and a structural stop, trades hold for a long time
(~420 bars on H1 synthetic data). Combined with `OnePositionAtATime = true`,
this blocks roughly **90% of signals** in live sequential execution.

This has a direct methodological consequence for training data — see
`04_labeling_and_meta_labeling.md`, section "Labeling mode vs backtest mode."
