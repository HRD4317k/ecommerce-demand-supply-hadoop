"""Demand forecasting (idea 1): six simple, explainable methods.

Used by the gap-engine reducer (inside Hadoop) and by ``analysis/backtest.py`` (to
score the methods against each other).  Pure Python, no third-party imports, so it
runs on a bare cluster node.

``series`` is a dict ``{"YYYY-MM-DD": units}`` for one SKU at one warehouse.  Days with
no entry count as zero demand.  Negative net demand (more returns than orders on a day)
is clipped to zero because a forecast of negative demand is meaningless.
"""
import datetime as dt
from statistics import mean

METHODS = ("naive7", "ma28", "damped", "dow_damped", "seasonal_naive", "adaptive")
WINDOW = 28
SHIFT_LOW, SHIFT_HIGH = 0.75, 1.33   # last-7-day / 28-day ratio outside this band = level shift


def dense(series, days=WINDOW, end=None):
    """Return (dates, values) for the last ``days`` days up to ``end`` (default: newest date)."""
    last = dt.date.fromisoformat(end) if end else dt.date.fromisoformat(max(series))
    dates = [last - dt.timedelta(days=i) for i in range(days - 1, -1, -1)]
    return dates, [max(0.0, float(series.get(d.isoformat(), 0.0))) for d in dates]


def damped_level(vals):
    """Average of the last 7 days times a damped trend (last 7 vs previous 7, clipped to 0.8-1.6)."""
    recent, previous = mean(vals[-7:]), (mean(vals[-14:-7]) if len(vals) >= 14 else mean(vals[-7:]))
    growth = recent / previous if previous > 0 else 1.0
    return recent * min(max(growth, 0.8), 1.6)


def adaptive_level(vals):
    """Stable demand: the long 28-day average (less noise).  Level shift: the last 7 days.

    A shift is declared when the last-7-day average is more than ~25% away from the
    28-day average, for example when a festive sale starts.
    """
    long_avg, short_avg = mean(vals), mean(vals[-7:])
    if long_avg > 0 and not (SHIFT_LOW <= short_avg / long_avg <= SHIFT_HIGH):
        return short_avg
    return long_avg


def weekday_index(dates, vals):
    """Seasonal index per weekday (Monday=0) via a centred 7-day moving average.

    Each day is divided by the average of the 7 days around it, so a level shift (for
    example a sale starting mid-window) does not pollute the weekday shape.  The result
    is normalised to mean 1.
    """
    ratios = {w: [] for w in range(7)}
    for i in range(3, len(vals) - 3):
        centre = mean(vals[i - 3:i + 4])
        if centre > 0:
            ratios[dates[i].weekday()].append(vals[i] / centre)
    idx = {w: (mean(r) if r else 1.0) for w, r in ratios.items()}
    norm = mean(idx.values())
    return {w: v / norm for w, v in idx.items()}


def forecast(series, horizon, method="dow_damped", end=None):
    """Forecast daily demand for the ``horizon`` days after ``end``; returns a list of floats."""
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; choose from {METHODS}")
    dates, vals = dense(series, WINDOW, end)
    last = dates[-1]
    if method == "naive7":
        return [mean(vals[-7:])] * horizon
    if method == "ma28":
        return [mean(vals)] * horizon
    if method == "damped":
        return [damped_level(vals)] * horizon
    if method == "adaptive":
        return [adaptive_level(vals)] * horizon
    if method == "seasonal_naive":
        return [vals[-7 + (i % 7)] for i in range(horizon)]
    base = damped_level(vals)                      # dow_damped
    idx = weekday_index(dates, vals)
    days = [last + dt.timedelta(days=i) for i in range(1, horizon + 1)]
    return [base * idx[d.weekday()] for d in days]


def demand_std(series, days=14, end=None):
    """Population std-dev of daily demand over the last ``days`` days."""
    _, vals = dense(series, days, end)
    m = mean(vals)
    return (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
