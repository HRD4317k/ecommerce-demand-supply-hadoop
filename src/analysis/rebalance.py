#!/usr/bin/env python3
"""Warehouse rebalancing (idea 4): move surplus stock to warehouses that are about to run out.

For each SKU a small transportation problem is solved (integer linear program, SciPy/HiGHS):

  donors      warehouses holding more than their order-up-to level S   -> units they can give
  recipients  warehouses at WATCH or CRITICAL risk                      -> units needed to get back to
              their reorder point s (need = ceil(s - inventory position))
  arcs        donor -> recipient, allowed only when the transfer is FASTER than the recipient's
              own supplier lead time (otherwise a normal purchase order is just as quick)

  minimise  sum(cost_ij * x_ij) + PENALTY * sum(unmet_j)
  subject to  sum_j x_ij <= surplus_i          (a donor cannot give more than its surplus)
              sum_i x_ij + unmet_j >= need_j   (cover the need, or record what is left over)
              x_ij integer >= 0

PENALTY is far larger than any freight cost, so covering a stock-out always beats saving freight.
Freight costs and transfer times between warehouses are ASSUMPTIONS (see DEFAULT_LANES): replace
them with real lane data or pass --lanes lanes.json.
"""
import argparse
import json
import math
import os

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from io_utils import read_gap

# (from, to): (rupees per unit, days).  Symmetric.  Replace with real freight data.
DEFAULT_LANES = {("KOL", "DEL"): (18.0, 3), ("KOL", "BLR"): (22.0, 3), ("DEL", "BLR"): (20.0, 2)}
PENALTY = 1000.0


def lane(lanes, a, b):
    return lanes.get((a, b)) or lanes.get((b, a))


def solve_sku(rows, lanes):
    """rows: DataFrame of one SKU's warehouses.  Returns (transfers, needs) lists."""
    need, surplus, lead = {}, {}, {}
    for r in rows.itertuples():
        position = r.on_hand + r.on_order
        if r.risk in ("CRITICAL", "WATCH"):
            n = math.ceil(r.reorder_point - position)
            if n > 0:
                need[r.warehouse] = n
                lead[r.warehouse] = r.lead_mean
        elif position > r.order_up_to:
            s = min(int(r.on_hand), math.floor(position - r.order_up_to))
            if s > 0:
                surplus[r.warehouse] = s
    arcs = [(i, j) for i in surplus for j in need
            if i != j and lane(lanes, i, j) and lane(lanes, i, j)[1] < lead[j]]
    if not arcs:
        return [], need
    recipients = list(need)
    m, n = len(arcs), len(recipients)
    c = np.array([lane(lanes, i, j)[0] for i, j in arcs] + [PENALTY] * n)
    a_ub, b_ub = [], []
    for donor in surplus:                                   # donor capacity
        a_ub.append([1.0 if i == donor else 0.0 for i, _ in arcs] + [0.0] * n)
        b_ub.append(surplus[donor])
    for k, rec in enumerate(recipients):                    # cover the need or record it as unmet
        a_ub.append([-1.0 if j == rec else 0.0 for _, j in arcs] + [-1.0 if q == k else 0.0 for q in range(n)])
        b_ub.append(-need[rec])
    res = linprog(c, A_ub=np.array(a_ub), b_ub=np.array(b_ub), bounds=[(0, None)] * (m + n),
                  integrality=np.ones(m + n), method="highs")
    if not res.success:
        return [], need
    transfers = []
    for (i, j), x in zip(arcs, res.x[:m]):
        units = int(round(x))
        if units > 0:
            cost, days = lane(lanes, i, j)
            transfers.append({"from": i, "to": j, "units": units, "freight_cost": units * cost,
                              "transfer_days": days})
    return transfers, need


def rebalance(gap, lanes=None):
    lanes = lanes or DEFAULT_LANES
    out = []
    for sku, rows in gap.groupby("sku"):
        transfers, need = solve_sku(rows, lanes)
        got = {}
        for t in transfers:
            got[t["to"]] = got.get(t["to"], 0) + t["units"]
            out.append({"sku": sku, **t, "need_at_destination": need[t["to"]]})
    cols = ["sku", "from", "to", "units", "freight_cost", "transfer_days", "need_at_destination"]
    return pd.DataFrame(out, columns=cols)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--gap", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lanes", help="JSON file: list of [from, to, cost_per_unit, days]")
    ap.add_argument("--meta", help="data/meta.json; its \"lanes\" entry is used when --lanes is not given")
    a = ap.parse_args()
    lanes = DEFAULT_LANES
    raw = json.load(open(a.lanes)) if a.lanes else (json.load(open(a.meta)).get("lanes") if a.meta else None)
    if raw:
        lanes = {(x[0], x[1]): (float(x[2]), int(x[3])) for x in raw}
    gap = read_gap(a.gap)
    transfers = rebalance(gap, lanes)
    transfers.to_csv(os.path.join(a.out, "transfers.csv"), index=False)
    summary = {"transfers": int(len(transfers)), "units_moved": int(transfers["units"].sum()),
               "freight_cost": float(transfers["freight_cost"].sum()),
               "skus_helped": int(transfers["sku"].nunique())}
    with open(os.path.join(a.out, "rebalance_summary.json"), "w") as handle:
        json.dump(summary, handle, indent=2)
    print(f"rebalancing: {summary['transfers']} transfers, {summary['units_moved']} units, "
          f"freight cost {summary['freight_cost']:.0f}, {summary['skus_helped']} SKUs helped")


if __name__ == "__main__":
    main()
