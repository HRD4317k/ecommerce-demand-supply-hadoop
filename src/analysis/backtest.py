#!/usr/bin/env python3
"""Forecast backtest (idea 1): which method predicts demand best?

Rolling-origin evaluation.  For each origin date T (the last ``--origins`` possible days)
and each SKU-warehouse series, every method forecasts the next ``--horizon`` days using
only data up to T; the forecast is compared with what actually happened.

Metrics
  wape_daily  sum |forecast - actual| / sum actual           (day by day; noisy by nature)
  wape_week   same, but on the total over the horizon per series (what ordering decisions use)
  bias        (sum forecast - sum actual) / sum actual       (negative = under-forecasting)

Origins are bucketed against the sale window so the effect of a demand shock is visible:
  normal      the horizon does not touch the sale
  sale-shock  the sale starts inside the horizon (no method can see it coming)
  in-sale     the origin is inside the sale window
  post-sale   the origin is within 14 days after the sale ended (demand hangover)

Origin dates: by default the last ``--origins`` days.  With ``--spread`` the origins are one per week
across the whole history, plus every day around the sale window, so a one-day event such as Black Friday
is actually inside the test.
"""
import argparse
import datetime as dt
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "jobs"))
from forecast import METHODS, dense, forecast  # noqa: E402
from io_utils import read_daily  # noqa: E402


def build_series(daily):
    series = {}
    for sku, wh, date, net in zip(daily["sku"], daily["warehouse"], daily["date"], daily["net"]):
        series.setdefault((sku, wh), {})[date] = float(net)
    return series


POST_SALE_DAYS = 14


def bucket_of(origin, horizon, sale_start, sale_end=None):
    sale_end = sale_end or dt.date.max
    if sale_start <= origin <= sale_end:
        return "in-sale"
    if origin < sale_start <= origin + dt.timedelta(days=horizon):
        return "sale-shock"
    if sale_end < origin <= sale_end + dt.timedelta(days=POST_SALE_DAYS):
        return "post-sale"
    return "normal"


def pick_origins(first, as_of, horizon, origins, sale_start, sale_end, spread):
    """Origin dates to evaluate (each needs 28 days of history before and ``horizon`` days after)."""
    latest = as_of - dt.timedelta(days=horizon)
    earliest = first + dt.timedelta(days=28)
    if not spread:
        return [latest - dt.timedelta(days=k) for k in range(origins)]
    days = set()
    d = latest
    while d >= earliest:                                         # one origin per week, newest first
        days.add(d)
        d -= dt.timedelta(days=7)
    lo = sale_start - dt.timedelta(days=horizon + 7)             # every day around the sale
    hi = (sale_end or sale_start) + dt.timedelta(days=POST_SALE_DAYS)
    d = lo
    while d <= hi:
        if earliest <= d <= latest:
            days.add(d)
        d += dt.timedelta(days=1)
    return sorted(days)


def run_backtest(daily, sale_start, horizon=7, origins=28, methods=METHODS, sale_end=None, spread=False):
    series = build_series(daily)
    as_of = dt.date.fromisoformat(max(daily["date"]))
    first = dt.date.fromisoformat(min(daily["date"]))
    sale_start = dt.date.fromisoformat(sale_start)
    sale_end = dt.date.fromisoformat(sale_end) if sale_end else None
    dates = pick_origins(first, as_of, horizon, origins, sale_start, sale_end, spread)
    records = []
    for origin in dates:
        bucket = bucket_of(origin, horizon, sale_start, sale_end)
        for key, s in series.items():
            _, actual = dense(s, horizon, (origin + dt.timedelta(days=horizon)).isoformat())
            for method in methods:
                f = forecast(s, horizon, method, origin.isoformat())
                records.append((method, bucket, sum(abs(a - b) for a, b in zip(f, actual)),
                                abs(sum(f) - sum(actual)), sum(f) - sum(actual), sum(actual)))
    frame = pd.DataFrame(records, columns=["method", "bucket", "abs_daily", "abs_week", "signed", "actual"])
    rows = []
    for (method, bucket), g in list(frame.groupby(["method", "bucket"])) + \
            [((m, "all"), g) for m, g in frame.groupby("method")]:
        total = g["actual"].sum()
        rows.append({"method": method, "bucket": bucket, "wape_daily": g["abs_daily"].sum() / total,
                     "wape_week": g["abs_week"].sum() / total, "bias": g["signed"].sum() / total,
                     "n_forecasts": len(g)})
    return pd.DataFrame(rows).sort_values(["bucket", "wape_week"]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--daily", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sale-start", required=True)
    ap.add_argument("--horizon", type=int, default=7)
    ap.add_argument("--origins", type=int, default=28)
    ap.add_argument("--sale-end", default="", help="last sale day (default: until the end of the data)")
    ap.add_argument("--spread", action="store_true", help="weekly origins over the whole history + daily around the sale")
    a = ap.parse_args()
    daily = read_daily(a.daily)
    result = run_backtest(daily, a.sale_start, a.horizon, a.origins, sale_end=a.sale_end or None, spread=a.spread)
    n_origins = len(pick_origins(dt.date.fromisoformat(min(daily["date"])), dt.date.fromisoformat(max(daily["date"])),
                                 a.horizon, a.origins, dt.date.fromisoformat(a.sale_start),
                                 dt.date.fromisoformat(a.sale_end) if a.sale_end else None, a.spread))
    result.round(4).to_csv(os.path.join(a.out, "backtest.csv"), index=False)
    overall = result[result.bucket == "all"].sort_values("wape_week")
    best = overall.iloc[0]["method"]
    with open(os.path.join(a.out, "backtest_summary.json"), "w") as handle:
        json.dump({"best_method_overall": best, "horizon_days": a.horizon, "origins": n_origins, "series": int(len(daily[["sku", "warehouse"]].drop_duplicates())),
                   "spread": a.spread}, handle, indent=2)
    print(overall.round(3).to_string(index=False))
    print(f"best overall (7-day total WAPE): {best}")


if __name__ == "__main__":
    main()
