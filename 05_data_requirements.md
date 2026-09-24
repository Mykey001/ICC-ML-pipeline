# 05 — Data Requirements

What the pipeline needs from you, and why each requirement exists. Read this
before exporting anything.

---

## 1. Schema

Six columns, exactly these names (lowercase), one row per **closed** bar:

```csv
time,open,high,low,close,volume
2019-01-02 00:00:00,1281.65,1284.20,1280.90,1283.75,4821
```

- `time` — ISO format, **UTC**, bar OPEN time
- `high`/`low` — true intrabar extremes (required for SL/TP resolution)
- `volume` — tick volume is fine; if unavailable, volume features are skipped
  automatically rather than producing garbage

Sorted ascending, no duplicate timestamps, no gaps beyond normal market closure.

---

## 2. Instrument — pick one to start

**Recommended: XAUUSD.** With `tp_pips = 2500` the target is $25.00, which is a
realistic swing move. On 5-digit FX pairs 2500 pips is 0.2500 of price and is
effectively unreachable — measured TP hit rate 0%.

If you intend to trade a 5-digit FX pair, `tp_pips` must be changed (a 5-digit
equivalent of a $25 gold move is roughly 250–400 pips), and the EA input must be
changed to match.

Start with **one instrument**. Multi-symbol training is a later optimisation and
introduces normalisation issues that are easier to solve once single-symbol
results are understood.

---

## 3. Timeframe

**Primary: H1.** This is the chart timeframe the EA runs on and the timeframe all
features are computed from.

| Timeframe | Signals/year (est.) | Assessment |
|---|---|---|
| M15 | High | Noisier; spread/slippage dominate |
| **H1** | **Moderate** | **Recommended starting point** |
| H4 | Low | May not reach 300 trades in 5 years |
| D1 | Very low | Insufficient for ML |

The H4 swing-stop data is **derived by resampling H1** inside the pipeline — you
do not need to export it separately. Exporting it separately risks a mismatch
between the two sources.

---

## 4. History depth

| Requirement | Amount | Reason |
|---|---|---|
| Absolute minimum | 3 years | ~300 trades; barely enough for 5 folds |
| **Recommended** | **7–10 years** | Multiple regimes; robust walk-forward |
| Warm-up overhead | +1,500 bars | EMA200, rolling percentiles, Hurst window |

The pipeline discards roughly the first 1,500 bars while indicators stabilise.
Request extra history at the start so this does not eat into your usable period.

**Regime coverage matters more than raw row count.** Ten years spanning 2015–2025
includes trending, ranging, high-volatility (2020) and low-volatility periods. A
model trained only on a trending period will fail when the regime changes — and
walk-forward will not reveal this if every fold sits inside the same regime.

---

## 5. How to export from MT5

**Option A — direct (preferred).** No export needed. On Windows with the terminal
running:

```python
pip install MetaTrader5
```

Then in the GUI choose source `mt5`, or:

```python
from icc_ml.data_fetch import get_ohlcv
df, report = get_ohlcv("XAUUSD", "H1", datetime(2016,1,1), datetime(2026,1,1), source="mt5")
```

This is preferred because it guarantees the training data comes from the same
feed as live execution.

**Option B — CSV export.** MT5 → Tools → History Center → select symbol/timeframe
→ Export. Then rename columns to the schema above and place in `data/raw/`.

> Verify the exported timezone. MT5 broker server time is commonly UTC+2/+3, not
> UTC. If session features are computed on the wrong offset, the London/NY
> session flags will be wrong and those features will silently mislead.

---

## 6. Broker specification — I need these exact values

Defaults in `config.py` are placeholders. Send me, or set yourself, the real
values from **your** broker for the symbol you will trade:

| Value | Where to find it | Used for |
|---|---|---|
| Digits | Symbol specification | Pip size |
| Point | Symbol specification | Price conversion |
| Contract size | Symbol specification | Money P&L |
| Typical spread (points) | Market Watch, observed | Entry/exit cost |
| Commission per lot round turn | Account/broker terms | Net P&L |
| Minimum stop level | Symbol specification | SL validity |

Getting spread and commission wrong is the most common reason a backtest and a
live account diverge on otherwise identical logic.

---

## 7. Optional — real trade history

If you have already run this EA live or on demo, export the trade history
(MT5 → History → Report). It lets us validate the Python port against actual
fills rather than assumptions — the strongest available check that the
simulation matches reality.

---

## 8. Pre-flight checklist

Before training, the pipeline verifies:

- [ ] No duplicate timestamps
- [ ] Monotonically increasing time
- [ ] No zero/negative prices
- [ ] No `high < low` rows
- [ ] Missing-bar ratio within tolerance
- [ ] ≥ 300 ICC signals generated
- [ ] `tp_hit_rate` > 5%
- [ ] `timeout_rate` < 30%

`get_ohlcv()` runs the first five automatically and refuses to proceed on
duplicate or non-monotonic timestamps.
