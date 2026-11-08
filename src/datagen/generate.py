#!/usr/bin/env python3
"""Synthetic e-commerce data for the demand-supply pipeline.

Writes into --out:
  orders.csv      order_id,date,sku,category,warehouse,qty,price        (one row per order line;
                  lines sharing an order_id form a basket)
  returns.csv     return_id,order_id,sku,category,warehouse,return_date,qty,reason
  inventory.csv   sku,warehouse,on_hand,on_order,supplier_id,nominal_lead_days
  deliveries.csv  po_id,supplier_id,sku,warehouse,order_date,promised_date,delivered_date,
                  qty_ordered,qty_received
  meta.json       as_of, sale_start, planted bundle pairs, ...

Patterns planted on purpose so every idea has something real to find:
  * weekend bumps, a slow upward trend and a festive sale (demand x1.9) in the last days   -> ideas 1, 5
  * some SKU-warehouse pairs stocked thin, others heavily                                   -> ideas 2, 3, 4
  * suppliers with different lead times, reliability and over-optimistic quotes            -> idea 6
  * six SKU pairs that tend to be bought in the same basket                                -> idea 7
  * category return rates (Fashion highest, Grocery lowest)                                -> idea 8

All data is random and synthetic; no real customers, products or suppliers.
"""
import argparse
import csv
import datetime as dt
import json
import os
import random
from collections import defaultdict

CATS = {"Electronics": 12, "Fashion": 14, "Home": 8, "Grocery": 6}
WAREHOUSES = [("KOL", 0.40), ("DEL", 0.35), ("BLR", 0.25)]
AFFINITY = [("ELE001", "ELE002"), ("ELE003", "ELE004"), ("FAS001", "FAS002"),
            ("FAS005", "FAS006"), ("HOM001", "HOM002"), ("GRO001", "GRO002")]
RETURN_RATE = {"Electronics": 0.08, "Fashion": 0.18, "Home": 0.06, "Grocery": 0.02}
RETURN_REASONS = {
    "Electronics": ["defective", "not as described", "changed mind"],
    "Fashion": ["size/fit", "not as described", "changed mind", "damaged"],
    "Home": ["damaged", "not as described", "changed mind"],
    "Grocery": ["damaged", "expired"],
}
# supplier id: (true mean lead days, lead std, fill rate, how many days the quote is optimistic)
SUPPLIERS = {
    "SUP1": (4, 0.6, 0.98, 0), "SUP2": (5, 1.0, 0.96, 0), "SUP3": (6, 1.2, 0.95, 1),
    "SUP4": (7, 1.5, 0.93, 1), "SUP5": (8, 1.8, 0.90, 1), "SUP6": (9, 2.5, 0.87, 2),
    "SUP7": (5, 2.0, 0.92, 1), "SUP8": (10, 3.0, 0.82, 2),
}
PAIR_PROB = 0.45      # chance the partner of a bundle SKU lands in the same basket
EXTRA_PROB = 0.12     # chance of adding one random extra line to a basket
FESTIVE_LIFT = 1.9


def generate(out_dir, days=100, seed=42, sale_days=15, start="2026-08-01"):
    rng = random.Random(seed)
    os.makedirs(out_dir, exist_ok=True)
    start_date = dt.date.fromisoformat(start)
    last_date = start_date + dt.timedelta(days=days - 1)
    sale_start = last_date - dt.timedelta(days=sale_days - 1)

    skus = []
    for cat, n in CATS.items():
        for i in range(n):
            code = f"{cat[:3].upper()}{i + 1:03d}"
            skus.append({"sku": code, "cat": cat, "base": rng.uniform(2, 14),
                         "price": rng.choice([150, 400, 999, 2500, 18000]),
                         "supplier": f"SUP{len(skus) % len(SUPPLIERS) + 1}"})
    partner = {}
    for a, b in AFFINITY:
        partner[a], partner[b] = b, a

    order_id, return_id = 0, 0
    with open(os.path.join(out_dir, "orders.csv"), "w", newline="") as fo, \
            open(os.path.join(out_dir, "returns.csv"), "w", newline="") as fr:
        wo, wr = csv.writer(fo), csv.writer(fr)
        wo.writerow(["order_id", "date", "sku", "category", "warehouse", "qty", "price"])
        wr.writerow(["return_id", "order_id", "sku", "category", "warehouse", "return_date", "qty", "reason"])
        for d in range(days):
            day = start_date + dt.timedelta(days=d)
            weekend = 1.25 if day.weekday() >= 5 else 1.0
            trend = 1 + 0.004 * d
            festive = FESTIVE_LIFT if day >= sale_start else 1.0
            for wh, share in WAREHOUSES:
                lines = []
                for s in skus:
                    lam = s["base"] * share * weekend * trend * festive
                    for _ in range(max(0, int(rng.gauss(lam, lam ** 0.5)))):
                        lines.append((s, rng.choice([1, 1, 1, 2, 3])))
                rng.shuffle(lines)
                used = [False] * len(lines)
                by_sku = defaultdict(list)
                for i, (s, _) in enumerate(lines):
                    by_sku[s["sku"]].append(i)

                def take(code):
                    while by_sku[code]:
                        j = by_sku[code].pop()
                        if not used[j]:
                            used[j] = True
                            return j
                    return None

                for i, (s, _) in enumerate(lines):
                    if used[i]:
                        continue
                    used[i] = True
                    basket = [i]
                    mate = partner.get(s["sku"])
                    if mate and rng.random() < PAIR_PROB:
                        j = take(mate)
                        if j is not None:
                            basket.append(j)
                    while rng.random() < EXTRA_PROB and len(basket) < 5:
                        j = rng.randrange(len(lines))
                        if used[j]:
                            break
                        used[j] = True
                        basket.append(j)
                    order_id += 1
                    for j in basket:
                        item, qty = lines[j]
                        wo.writerow([order_id, day.isoformat(), item["sku"], item["cat"], wh, qty, item["price"]])
                        if rng.random() < RETURN_RATE[item["cat"]]:
                            rq = qty if rng.random() < 0.8 else 1
                            back = day + dt.timedelta(days=rng.randint(3, 12))
                            if back <= last_date:           # returns after the data ends have not happened yet
                                return_id += 1
                                wr.writerow([f"R{return_id:07d}", order_id, item["sku"], item["cat"], wh,
                                             back.isoformat(), rq, rng.choice(RETURN_REASONS[item["cat"]])])

    with open(os.path.join(out_dir, "inventory.csv"), "w", newline="") as fi:
        w = csv.writer(fi)
        w.writerow(["sku", "warehouse", "on_hand", "on_order", "supplier_id", "nominal_lead_days"])
        for s in skus:
            mean_lead, _, _, optimism = SUPPLIERS[s["supplier"]]
            nominal = max(1, mean_lead - optimism)
            for wh, share in WAREHOUSES:
                daily = s["base"] * share * 2.4
                cover = rng.choices([3, 6, 10, 15, 22, 32, 50, 70], weights=[3, 4, 6, 8, 8, 7, 5, 3])[0]
                on_order = int(daily * rng.choice([0, 0, 0, 5, 8, 12]))
                w.writerow([s["sku"], wh, int(daily * cover), on_order, s["supplier"], nominal])

    with open(os.path.join(out_dir, "deliveries.csv"), "w", newline="") as fd:
        w = csv.writer(fd)
        w.writerow(["po_id", "supplier_id", "sku", "warehouse", "order_date", "promised_date",
                    "delivered_date", "qty_ordered", "qty_received"])
        po = 0
        for s in skus:
            mean_lead, lead_std, fill, optimism = SUPPLIERS[s["supplier"]]
            nominal = max(1, mean_lead - optimism)
            for wh, share in WAREHOUSES:
                for _ in range(rng.randint(4, 7)):
                    ordered = start_date + dt.timedelta(days=rng.randint(0, days - 30))
                    actual = ordered + dt.timedelta(days=max(1, round(rng.gauss(mean_lead, lead_std))))
                    if actual > last_date:
                        continue
                    qo = max(20, int(s["base"] * share * 2.4 * rng.uniform(10, 20)))
                    qr = int(round(qo * min(1.0, max(0.5, rng.gauss(fill, 0.04)))))
                    po += 1
                    w.writerow([f"PO{po:05d}", s["supplier"], s["sku"], wh, ordered.isoformat(),
                                (ordered + dt.timedelta(days=nominal)).isoformat(), actual.isoformat(), qo, qr])

    meta = {"as_of": last_date.isoformat(), "sale_start": sale_start.isoformat(), "days": days,
            "seed": seed, "orders": order_id, "affinity_pairs": AFFINITY}
    with open(os.path.join(out_dir, "meta.json"), "w") as fm:
        json.dump(meta, fm, indent=2)
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="data")
    ap.add_argument("--days", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sale-days", type=int, default=15)
    a = ap.parse_args()
    meta = generate(a.out, a.days, a.seed, a.sale_days)
    print(f"wrote {meta['orders']:,} orders to {a.out}/ (as_of {meta['as_of']}, sale from {meta['sale_start']})")


if __name__ == "__main__":
    main()
