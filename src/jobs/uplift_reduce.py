#!/usr/bin/env python3
"""Festive-sale uplift, reduce step (idea 5).

Output: SCOPE|name <TAB> base_avg_day,sale_avg_day,plain_ratio,uplift,sale_days

  base window    the BASELINE_DAYS days before SALE_START (default 28 = 4 full weeks)
  sale window    SALE_START up to SALE_END (default: AS_OF, else the last day of data)
  plain_ratio    average units/day in the sale window / average units/day in the base window
  uplift         weekday-adjusted: each sale day is divided by the baseline average of ITS OWN
                 weekday before averaging, so a sale window with more weekends than weekdays
                 is not mistaken for a lift.
"""
import datetime as dt
import sys
from statistics import mean

from config import AS_OF, BASELINE_DAYS, SALE_END, SALE_START


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def compute(daily, sale_start, baseline_days, end):
    """daily: {date: units}.  Returns (base_avg, sale_avg, plain_ratio, uplift, sale_days)."""
    sale_start = dt.date.fromisoformat(sale_start)
    end = dt.date.fromisoformat(end)
    base_days = list(daterange(sale_start - dt.timedelta(days=baseline_days),
                               sale_start - dt.timedelta(days=1)))
    sale_days = list(daterange(sale_start, end))
    if not base_days or not sale_days:
        return None
    units = lambda d: float(daily.get(d.isoformat(), 0))
    base_vals = [units(d) for d in base_days]
    sale_vals = [units(d) for d in sale_days]
    base_avg, sale_avg = mean(base_vals), mean(sale_vals)
    by_dow = {w: [units(d) for d in base_days if d.weekday() == w] for w in range(7)}
    dow_avg = {w: mean(v) for w, v in by_dow.items() if v}
    ratios = [units(d) / dow_avg[d.weekday()] for d in sale_days if dow_avg.get(d.weekday(), 0) > 0]
    if base_avg <= 0 or not ratios:
        return None
    return base_avg, sale_avg, sale_avg / base_avg, mean(ratios), len(sale_days)


def main():
    current, daily = None, {}

    def flush():
        if current is None:
            return
        end = SALE_END or AS_OF or max(daily)
        result = compute(daily, SALE_START, BASELINE_DAYS, end)
        if result:
            base, sale, plain, uplift, days = result
            print(f"{current}\t{base:.2f},{sale:.2f},{plain:.3f},{uplift:.3f},{days}")

    for line in sys.stdin:
        key, _, value = line.rstrip("\n").partition("\t")
        if key != current:
            flush()
            current, daily = key, {}
        date, qty = value.split(",")
        daily[date] = daily.get(date, 0) + int(qty)
    flush()


if __name__ == "__main__":
    main()
