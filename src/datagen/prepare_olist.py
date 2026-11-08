#!/usr/bin/env python3
"""Turn the REAL Olist Brazilian e-commerce dataset into the four files the pipeline reads.

Source (CC BY-NC-SA 4.0): "Brazilian E-Commerce Public Dataset by Olist", ~100k real marketplace orders
placed in Brazil between 2016 and 2018.  See docs/DATA.md and REFERENCES.md.

Input  --raw   folder with the original Olist CSVs (olist_orders_dataset.csv, olist_order_items_dataset.csv,
               olist_products_dataset.csv, olist_customers_dataset.csv, product_category_name_translation.csv)
Output --out   orders.csv, returns.csv, inventory.csv, deliveries.csv, meta.json   (same columns as the
               synthetic generator, so every job and analysis script runs unchanged)

How the planning model is mapped onto a marketplace
  sku        product category (71 categories; the 30 or so biggest are planned, see MIN_SKU_UNITS)
  category   department the category belongs to (Electronics, Home, ...), used for uplift and cancellation rates
  warehouse  one of five regional hubs, chosen from the customer's state (SP, RJ, MG, SUL, NE)
  supplier   the seller that fulfils the order (supplier_id = "S" + first 7 characters of seller_id)
  deliveries one row per (order, seller, category) with the seller's own timings:
             order_date = purchase, promised_date = estimated delivery date shown to the customer,
             delivered_date = real delivery to the customer (empty when the order was cancelled)
  returns    the dataset has NO returns table.  The nearest real signal is orders cancelled by the marketplace
             (status canceled / unavailable).  They have no cancel timestamp, so they are booked on the order date.

What is REAL: orders, categories, regions, sellers, estimated and actual delivery dates, cancellations, the
Black Friday 2017 spike.
What is NOT in the data and is therefore ASSUMED (and labelled in meta.json / REPORT.md):
  * warehouse stock levels (inventory.csv): a seeded snapshot of "days of cover" on top of the real recent demand
  * freight cost and transfer days between hubs (lanes in meta.json)
"""
import argparse
import csv
import datetime as dt
import json
import os
import random
from collections import Counter, defaultdict

import pandas as pd

START = "2017-01-01"              # 2016 is a handful of orders; the marketplace really starts in 2017
BLACK_FRIDAY = "2017-11-24"       # 4th Friday of November 2017
SALE_LAST_DAY = "2017-11-30"      # Black Friday week
MIN_SKU_UNITS = 700               # a category must sell at least this many units to be planned
MIN_PAIR_UNITS = 250              # ... and a category/hub pair at least this many
MIN_SELLER_LINES = 30             # a seller needs this many order lines to be a "primary supplier"
CANCEL_STATUS = ("canceled", "unavailable")
FINAL_STATUS = ("delivered",) + CANCEL_STATUS

HUB_OF_STATE = {"SP": "SP", "RJ": "RJ", "ES": "RJ", "MG": "MG", "GO": "MG", "DF": "MG", "MT": "MG", "MS": "MG",
                "TO": "MG", "RS": "SUL", "PR": "SUL", "SC": "SUL"}      # every other state -> NE (north / north-east)
DEFAULT_HUB = "NE"

# Assumed lanes: (from, to, cost per unit in BRL, transfer days).  The dataset has no freight between hubs.
LANES = [["SP", "RJ", 3.0, 1], ["SP", "MG", 4.0, 2], ["SP", "SUL", 5.0, 2], ["SP", "NE", 12.0, 5],
         ["RJ", "MG", 4.0, 2], ["RJ", "SUL", 6.0, 3], ["RJ", "NE", 10.0, 4],
         ["MG", "SUL", 6.0, 3], ["MG", "NE", 9.0, 4], ["SUL", "NE", 14.0, 6]]

DEPARTMENT = {
    "Electronics": ["audio", "cine_photo", "computers", "computers_accessories", "consoles_games", "electronics",
                    "fixed_telephony", "pc_gamer", "signaling_and_security", "security_and_services",
                    "tablets_printing_image", "telephony"],
    "Home": ["air_conditioning", "bed_bath_table", "furniture_bedroom", "furniture_decor", "furniture_living_room",
             "furniture_mattress_and_upholstery", "home_appliances", "home_appliances_2", "home_comfort_2",
             "home_confort", "home_construction", "housewares", "kitchen_dining_laundry_garden_furniture",
             "la_cuisine", "office_furniture", "small_appliances", "small_appliances_home_oven_and_coffee",
             "portateis_cozinha_e_preparadores_de_alimentos", "christmas_supplies", "flowers", "party_supplies"],
    "Fashion": ["fashio_female_clothing", "fashion_bags_accessories", "fashion_childrens_clothes",
                "fashion_male_clothing", "fashion_shoes", "fashion_sport", "fashion_underwear_beach",
                "luggage_accessories", "watches_gifts"],
    "Health & Beauty": ["diapers_and_hygiene", "health_beauty", "perfumery"],
    "Leisure & Kids": ["art", "arts_and_craftmanship", "baby", "books_general_interest", "books_imported",
                       "books_technical", "cds_dvds_musicals", "cool_stuff", "dvds_blu_ray", "music",
                       "musical_instruments", "sports_leisure", "stationery", "toys"],
    "Tools & Auto": ["agro_industry_and_commerce", "auto", "construction_tools_construction",
                     "construction_tools_lights", "construction_tools_safety", "costruction_tools_garden",
                     "costruction_tools_tools", "garden_tools", "industry_commerce_and_business", "pet_shop"],
    "Food & Drink": ["drinks", "food", "food_drink", "market_place"],
}
DEPT_OF = {sku: dept for dept, skus in DEPARTMENT.items() for sku in skus}


def read_csv(raw, name, **kw):
    return pd.read_csv(os.path.join(raw, name), **kw)


def detect_as_of(day_counts, start):
    """Last day whose volume is still normal: the dataset thins out at the very end (orders not yet complete)."""
    counts = day_counts[day_counts.index >= pd.Timestamp(start)]
    for day in reversed(counts.index):
        prev = counts[(counts.index < day) & (counts.index >= day - pd.Timedelta(days=28))]
        if len(prev) >= 14 and counts[day] >= 0.8 * prev.median():
            return day.date()
    return counts.index[-1].date()


def load(raw):
    orders = read_csv(raw, "olist_orders_dataset.csv",
                      parse_dates=["order_purchase_timestamp", "order_delivered_customer_date",
                                   "order_estimated_delivery_date"])
    items = read_csv(raw, "olist_order_items_dataset.csv")
    products = read_csv(raw, "olist_products_dataset.csv")[["product_id", "product_category_name"]]
    customers = read_csv(raw, "olist_customers_dataset.csv")[["customer_id", "customer_state"]]
    trans = read_csv(raw, "product_category_name_translation.csv", encoding="utf-8-sig")
    english = dict(zip(trans["product_category_name"], trans["product_category_name_english"]))
    products["sku"] = products["product_category_name"].map(lambda c: english.get(c, c) if isinstance(c, str) else None)
    lines = (items.merge(products[["product_id", "sku"]], on="product_id", how="left")
                  .merge(orders, on="order_id").merge(customers, on="customer_id"))
    lines = lines[lines["sku"].notna()].copy()
    lines["date"] = lines["order_purchase_timestamp"].dt.normalize()
    lines["warehouse"] = lines["customer_state"].map(lambda s: HUB_OF_STATE.get(s, DEFAULT_HUB))
    lines["category"] = lines["sku"].map(lambda s: DEPT_OF.get(s, "Other"))
    return orders, lines


def prepare(raw, out, as_of=None, seed=42):
    os.makedirs(out, exist_ok=True)
    orders, lines = load(raw)
    day_counts = orders["order_purchase_timestamp"].dt.normalize().value_counts().sort_index()
    as_of = dt.date.fromisoformat(as_of) if as_of else detect_as_of(day_counts, START)
    first, last = pd.Timestamp(START), pd.Timestamp(as_of)
    lines = lines[(lines["date"] >= first) & (lines["date"] <= last)].copy()
    lines["seller"] = "S" + lines["seller_id"].str[:7]

    # ---- orders.csv: one row per (order, category); qty = number of items of that category in the order
    ol = (lines.groupby(["order_id", "sku", "category", "warehouse", "date", "order_status"], as_index=False)
               .agg(qty=("order_item_id", "size"), price=("price", "sum")))
    ol = ol.sort_values(["date", "order_id", "sku"]).reset_index(drop=True)
    ids = {oid: n for n, oid in enumerate(ol["order_id"].drop_duplicates(), start=1)}
    ol["oid"] = ol["order_id"].map(ids)
    ol[["oid", "date", "sku", "category", "warehouse", "qty", "price"]].assign(
        date=ol["date"].dt.strftime("%Y-%m-%d"), price=ol["price"].round(2)).to_csv(
        os.path.join(out, "orders.csv"), index=False,
        header=["order_id", "date", "sku", "category", "warehouse", "qty", "price"])

    # ---- baskets_products.csv: the same baskets at product level (sku = "P" + 7 chars of product_id), for bundle mining
    pl = (lines.assign(product="P" + lines["product_id"].str[:7])
               .groupby(["order_id", "product", "sku", "warehouse", "date"], as_index=False)
               .agg(qty=("order_item_id", "size"), price=("price", "sum")))
    pl["oid"] = pl["order_id"].map(ids)
    pl.sort_values(["date", "oid"]).assign(date=lambda d: d["date"].dt.strftime("%Y-%m-%d"),
                                           price=lambda d: d["price"].round(2))[
        ["oid", "date", "product", "sku", "warehouse", "qty", "price"]].to_csv(
        os.path.join(out, "baskets_products.csv"), index=False,
        header=["order_id", "date", "sku", "category", "warehouse", "qty", "price"])   # category column = category of the product

    # ---- returns.csv: marketplace cancellations (no cancel timestamp -> booked on the order date)
    cancelled = ol[ol["order_status"].isin(CANCEL_STATUS)]
    with open(os.path.join(out, "returns.csv"), "w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["return_id", "order_id", "sku", "category", "warehouse", "return_date", "qty", "reason"])
        for n, r in enumerate(cancelled.itertuples(), start=1):
            w.writerow([f"C{n:07d}", r.oid, r.sku, r.category, r.warehouse, r.date.strftime("%Y-%m-%d"), r.qty,
                        r.order_status])

    # ---- deliveries.csv: the seller's real record, one row per (order, seller, category)
    fin = lines[lines["order_status"].isin(FINAL_STATUS)].copy()
    fin["delivered"] = fin["order_delivered_customer_date"].dt.normalize()
    fin = fin[~((fin["order_status"] == "delivered") & fin["delivered"].isna())]
    fin.loc[fin["order_status"].isin(CANCEL_STATUS), "delivered"] = pd.NaT
    fin["promised"] = fin["order_estimated_delivery_date"].dt.normalize()
    fin = fin[fin["delivered"].isna() | (fin["delivered"] >= fin["date"])]
    dl = (fin.groupby(["order_id", "seller", "sku", "warehouse", "date", "promised", "delivered"], as_index=False,
                      dropna=False).agg(qo=("order_item_id", "size")))
    dl["qr"] = dl["qo"].where(dl["delivered"].notna(), 0)
    with open(os.path.join(out, "deliveries.csv"), "w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["po_id", "supplier_id", "sku", "warehouse", "order_date", "promised_date", "delivered_date",
                    "qty_ordered", "qty_received"])
        for n, r in enumerate(dl.sort_values("date").itertuples(), start=1):
            w.writerow([f"OL{n:07d}", r.seller, r.sku, r.warehouse, r.date.strftime("%Y-%m-%d"),
                        r.promised.strftime("%Y-%m-%d"),
                        "" if pd.isna(r.delivered) else r.delivered.strftime("%Y-%m-%d"), r.qo, r.qr])

    # ---- inventory.csv: ASSUMED snapshot on top of real recent demand, for the planned category/hub pairs
    rng = random.Random(seed)
    units = ol.groupby("sku")["qty"].sum()
    planned = sorted(units[units >= MIN_SKU_UNITS].index)
    pair_units = ol.groupby(["sku", "warehouse"])["qty"].sum()
    net_recent = (ol[ol["date"] > last - pd.Timedelta(days=28)]
                  .assign(net=lambda d: d["qty"].where(~d["order_status"].isin(CANCEL_STATUS), 0))
                  .groupby(["sku", "warehouse"])["net"].sum() / 28.0)
    seller_lines = lines.groupby("seller").size()
    dl_lead = dl.assign(promised_days=(dl["promised"] - dl["date"]).dt.days).groupby("seller")["promised_days"].mean()
    by_pair = lines.groupby(["sku", "warehouse", "seller"]).size()
    inv_rows = []
    for sku in planned:
        for wh in sorted(set(HUB_OF_STATE.values()) | {DEFAULT_HUB}):
            if pair_units.get((sku, wh), 0) < MIN_PAIR_UNITS:
                continue
            cands = by_pair.loc[sku, wh].sort_values(ascending=False)
            eligible = [s for s in cands.index if seller_lines.get(s, 0) >= MIN_SELLER_LINES and s in dl_lead.index]
            seller = (eligible or [s for s in cands.index if s in dl_lead.index])[0]
            rate = float(net_recent.get((sku, wh), 0.0))
            cover = rng.choices([3, 6, 10, 15, 22, 32, 50, 70], weights=[3, 4, 6, 8, 8, 7, 5, 3])[0]
            on_order = int(rate * rng.choice([0, 0, 0, 5, 8, 12]))
            inv_rows.append([sku, wh, int(rate * cover), on_order, seller, max(1, round(float(dl_lead[seller])))])
    with open(os.path.join(out, "inventory.csv"), "w", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["sku", "warehouse", "on_hand", "on_order", "supplier_id", "nominal_lead_days"])
        w.writerows(inv_rows)

    meta = {
        "dataset": "Olist Brazilian E-Commerce Public Dataset (real marketplace orders, Brazil, 2017-2018)",
        "real_data": True, "currency": "BRL", "returns_label": "cancellations",
        "as_of": as_of.isoformat(), "sale_name": "Black Friday 2017",
        "sale_start": BLACK_FRIDAY, "sale_end": SALE_LAST_DAY, "first_day": START,
        "days": (as_of - dt.date.fromisoformat(START)).days + 1,
        "orders": int(len(ids)), "order_lines": int(len(ol)),
        "planned_skus": planned, "planned_pairs": len(inv_rows),
        "hubs": sorted(set(HUB_OF_STATE.values()) | {DEFAULT_HUB}), "lanes": LANES,
        "assumed": ["inventory.csv (stock snapshot: seeded days-of-cover on top of real recent demand)",
                    "lanes (cost per unit and days between hubs)",
                    "supplier lead time = the seller's real order-to-delivery time to the customer"],
        "uplift_note": "Black Friday 2017 is a real, one-day-dominated event, so the sale window is Black Friday week.",
    }
    with open(os.path.join(out, "meta.json"), "w") as handle:
        json.dump(meta, handle, indent=2)
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--raw", required=True, help="folder with the original Olist CSV files")
    ap.add_argument("--out", required=True)
    ap.add_argument("--as-of", help="last day of data (default: detected where order volume drops off)")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    meta = prepare(a.raw, a.out, a.as_of, a.seed)
    print(f"{meta['orders']:,} orders, {meta['order_lines']:,} lines, {meta['planned_pairs']} planned "
          f"category/hub pairs, as of {meta['as_of']}")


if __name__ == "__main__":
    main()
