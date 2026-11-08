#!/usr/bin/env python3
"""Turn the engine's numbers into things a planner can act on.

Reads   gap_report.csv, transfers.csv, bundles.tsv  (in --out)
Writes  alerts.csv           every CRITICAL / WATCH pair with the recommended action (most urgent first)
        purchase_orders.csv  the supplier orders still needed after transfers (ideas 3 and 4)
        bundle_alerts.csv    strong bundles where one item is at risk (idea 7)
"""
import argparse
import datetime as dt
import math
import os

import pandas as pd

from io_utils import read_bundles, read_gap

BUNDLE_MIN_LIFT = 3.0
SEVERITY = {"CRITICAL": 0, "WATCH": 1}


def build_alerts(gap, transfers, as_of):
    incoming = {}
    for t in transfers.rename(columns={"from": "source"}).itertuples():
        units, src = incoming.get((t.sku, t.to), (0, []))
        incoming[(t.sku, t.to)] = (units + t.units, src + [f"{t.units} from {t.source}"])
    rows = []
    for r in gap[gap.risk.isin(SEVERITY)].itertuples():
        units_in, sources = incoming.get((r.sku, r.warehouse), (0, []))
        order_after = max(0, r.order_qty - units_in)
        parts = []
        if units_in:
            parts.append("TRANSFER " + " + ".join(sources))
        if order_after:
            when = "NOW" if r.order_by <= as_of else f"by {r.order_by}"
            parts.append(f"ORDER {order_after} from {r.supplier_id} {when}")
        if r.risk == "CRITICAL" and r.days_late > 0:
            parts.append(f"stock-out expected {r.days_late} day(s) before a new order could land: expedite")
        arrival = dt.date.fromisoformat(as_of) + dt.timedelta(days=math.ceil(r.lead_mean))
        rows.append({"severity": r.risk, "sku": r.sku, "warehouse": r.warehouse,
                     "supplier_id": r.supplier_id, "supplier_tier": r.tier, "on_hand": r.on_hand,
                     "on_order": r.on_order, "cover_days": r.cover_days, "lead_days": r.lead_mean,
                     "days_late": r.days_late, "transfer_in": units_in, "order_qty": order_after,
                     "order_by": r.order_by, "earliest_arrival": arrival.isoformat(),
                     "action": "; ".join(parts) or "monitor"})
    alerts = pd.DataFrame(rows)
    if alerts.empty:
        return alerts
    alerts["_sev"] = alerts["severity"].map(SEVERITY)
    return alerts.sort_values(["_sev", "days_late", "cover_days"], ascending=[True, False, True]) \
                 .drop(columns="_sev").reset_index(drop=True)


def build_bundle_alerts(gap, bundles, min_lift=BUNDLE_MIN_LIFT):
    risk = {(r.sku, r.warehouse): r.risk for r in gap.itertuples()}
    cover = {(r.sku, r.warehouse): r.cover_days for r in gap.itertuples()}
    rows = []
    for b in bundles[bundles.lift >= min_lift].itertuples():
        for wh in sorted({w for _, w in risk}):
            ra, rb = risk.get((b.sku_a, wh)), risk.get((b.sku_b, wh))
            if ra is None or rb is None:
                continue
            a_bad, b_bad = ra in SEVERITY, rb in SEVERITY
            if a_bad and b_bad:
                kind = "DOUBLE_STOCKOUT"
                msg = f"both {b.sku_a} and {b.sku_b} are short at {wh}; bundle sales will be lost"
            elif a_bad or b_bad:
                bad, ok = (b.sku_a, b.sku_b) if a_bad else (b.sku_b, b.sku_a)
                kind = "PARTNER_AT_RISK"
                msg = f"{bad} is short at {wh}; its partner {ok} (lift {b.lift:.1f}) will lose cross-sell sales"
            else:
                continue
            rows.append({"warehouse": wh, "sku_a": b.sku_a, "sku_b": b.sku_b, "lift": b.lift,
                         "risk_a": ra, "risk_b": rb, "cover_a": cover[(b.sku_a, wh)],
                         "cover_b": cover[(b.sku_b, wh)], "type": kind, "message": msg})
    return pd.DataFrame(rows, columns=["warehouse", "sku_a", "sku_b", "lift", "risk_a", "risk_b",
                                       "cover_a", "cover_b", "type", "message"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--as-of", default=os.environ.get("AS_OF") or dt.date.today().isoformat())
    a = ap.parse_args()
    gap = read_gap(os.path.join(a.out, "gap_report.csv"))
    transfers = pd.read_csv(os.path.join(a.out, "transfers.csv"))
    bundles = read_bundles(os.path.join(a.out, "bundles.tsv"))

    alerts = build_alerts(gap, transfers, a.as_of)
    alerts.to_csv(os.path.join(a.out, "alerts.csv"), index=False)
    po = alerts[alerts["order_qty"] > 0][["supplier_id", "sku", "warehouse", "order_qty", "order_by",
                                          "earliest_arrival"]] if not alerts.empty else alerts
    po.sort_values(["supplier_id", "sku", "warehouse"]).to_csv(os.path.join(a.out, "purchase_orders.csv"), index=False)
    ba = build_bundle_alerts(gap, bundles)
    ba.to_csv(os.path.join(a.out, "bundle_alerts.csv"), index=False)
    print(f"alerts: {len(alerts)} ({(alerts.severity == 'CRITICAL').sum() if not alerts.empty else 0} critical), "
          f"{len(po)} purchase-order lines, {len(ba)} bundle alerts")


if __name__ == "__main__":
    main()
