#!/usr/bin/env python3
"""Gap engine, reduce step (ideas 1, 2 and 3).

For every sku|warehouse the reducer receives that pair's whole demand history (D records)
and its inventory row (I record) and produces ONE CSV row (columns: schema.GAP_FIELDS):

  1. forecast daily demand with the configured method        (idea 1)
  2. classify stock-out risk CRITICAL / WATCH / OK / OVERSTOCK (idea 2)
  3. compute safety stock, reorder point, order quantity, latest order date (idea 3)
"""
import datetime as dt
import sys

from config import (AS_OF, FORECAST_METHOD, OVERSTOCK_DAYS, REVIEW_DAYS, SERVICE_LEVEL,
                    STD_DAYS)
from forecast import demand_std, forecast
from policy import horizon_needed, plan


def build_row(key, demand, inv):
    sku, wh = key.split("|")
    on_hand, on_order = int(inv[0]), int(inv[1])
    supplier, tier = inv[2], inv[7]
    lead_mean, lead_std, fill = float(inv[4]), float(inv[5]), float(inv[6])

    end = AS_OF or max(demand)
    f = forecast(demand, horizon_needed(lead_mean, REVIEW_DAYS), FORECAST_METHOD, end)
    sigma = demand_std(demand, STD_DAYS, end)
    p = plan(on_hand=on_hand, on_order=on_order, forecast_by_day=f, sigma_d=sigma,
             lead_mean=lead_mean, lead_std=lead_std, fill_rate=fill,
             service_level=SERVICE_LEVEL, review_days=REVIEW_DAYS, overstock_days=OVERSTOCK_DAYS)
    order_by = dt.date.fromisoformat(end) + dt.timedelta(days=p["order_in_days"])
    return [sku, wh, supplier, tier, on_hand, on_order, f"{lead_mean:.2f}", f"{lead_std:.2f}",
            f"{fill:.3f}", f"{p['forecast_day']:.2f}", f"{sigma:.2f}", f"{p['safety_stock']:.1f}",
            f"{p['reorder_point']:.1f}", f"{p['order_up_to']:.1f}", f"{p['cover_days']:.1f}",
            p["risk"], p["order_qty"], order_by.isoformat(), p["days_late"], FORECAST_METHOD]


def flush(key, demand, inv):
    if key is None or inv is None or not demand:
        return
    print(",".join(str(x) for x in build_row(key, demand, inv)))


def main():
    current, demand, inv = None, {}, None
    for line in sys.stdin:
        key, _, value = line.rstrip("\n").partition("\t")
        if key != current:
            flush(current, demand, inv)
            current, demand, inv = key, {}, None
        parts = value.split(",")
        if parts[0] == "D":
            demand[parts[1]] = demand.get(parts[1], 0) + int(parts[2])
        else:
            inv = parts[1:]
    flush(current, demand, inv)


if __name__ == "__main__":
    main()
