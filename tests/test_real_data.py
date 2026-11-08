import datetime as dt
import json
import os
import subprocess

import pandas as pd
import pytest

import backtest
import prepare_olist
from conftest import ROOT, run_job, shuffle

RAW = ROOT / "data" / "raw" / "olist"


# ---------------------------------------------------------------- supplier lines that were never delivered
def test_supplier_scorecard_counts_cancelled_lines_against_fill_only():
    rows = ("P1,S1,X,SP,2026-09-01,2026-09-20,2026-09-11,1,1\n"       # delivered in 10 days, before the estimate
            "P2,S1,X,SP,2026-09-02,2026-09-22,2026-09-12,1,1\n"       # 10 days
            "P3,S1,X,SP,2026-09-03,2026-09-23,,1,0\n")                # cancelled: no delivery date
    m = run_job("supplier_map.py", rows)
    assert m[-1].endswith("NA,NA,1,0")
    out = run_job("supplier_reduce.py", shuffle(m))
    f = out[0].partition("\t")[2].split(",")
    assert int(f[0]) == 3                              # three lines
    assert float(f[1]) == pytest.approx(1.0)           # on-time rate over DELIVERED lines
    assert float(f[3]) == pytest.approx(10.0)          # lead time ignores the cancelled line
    assert float(f[5]) == pytest.approx(2 / 3, abs=1e-3)   # fill rate does not


def test_supplier_with_nothing_delivered_is_not_scored():
    out = run_job("supplier_reduce.py", "S9\tNA,NA,1,0\nS9\tNA,NA,1,0\n")
    assert out == []


# ---------------------------------------------------------------- sale window
def test_uplift_stops_at_sale_end():
    start = dt.date(2017, 11, 24)
    lines = []
    for i in range(-28, 30):
        d = start + dt.timedelta(days=i)
        lines.append(f"{i + 100},{d.isoformat()},S1,Home,SP,{30 if 0 <= i <= 6 else 10},1")   # 3x for a week only
    m = run_job("uplift_map.py", "\n".join(lines) + "\n",
                {"SALE_START": "2017-11-24", "SALE_END": "2017-11-30", "AS_OF": "2018-01-10"})
    out = dict(x.split("\t") for x in run_job("uplift_reduce.py", shuffle(m),
                                              {"SALE_START": "2017-11-24", "SALE_END": "2017-11-30", "AS_OF": "2018-01-10"}))
    f = out["CAT|Home"].split(",")
    assert float(f[4]) == 7                            # sale_days: only the week, not everything up to AS_OF
    assert float(f[3]) == pytest.approx(3.0, abs=0.01)


def test_backtest_buckets_and_origins():
    s, e = dt.date(2017, 11, 24), dt.date(2017, 11, 30)
    b = lambda o: backtest.bucket_of(o, 7, s, e)
    assert b(dt.date(2017, 10, 1)) == "normal"
    assert b(dt.date(2017, 11, 20)) == "sale-shock"
    assert b(dt.date(2017, 11, 26)) == "in-sale"
    assert b(dt.date(2017, 12, 5)) == "post-sale"
    assert b(dt.date(2018, 3, 1)) == "normal"
    origins = backtest.pick_origins(dt.date(2017, 1, 1), dt.date(2018, 8, 21), 7, 28, s, e, spread=True)
    assert {dt.date(2017, 11, 24), dt.date(2017, 11, 17)} <= set(origins)   # every day around the sale is tested
    assert max(origins) <= dt.date(2018, 8, 14) and min(origins) >= dt.date(2017, 1, 29)
    recent = backtest.pick_origins(dt.date(2017, 1, 1), dt.date(2018, 8, 21), 7, 28, s, e, spread=False)
    assert len(recent) == 28 and max(recent) == dt.date(2018, 8, 14)


# ---------------------------------------------------------------- the adapter, on a tiny Olist-format fixture
def make_raw(path):
    path.mkdir()
    day = lambda n: (dt.datetime(2017, 6, 1) + dt.timedelta(days=n)).strftime("%Y-%m-%d 10:00:00")
    orders, items, customers = [], [], []
    for n in range(60):
        oid = f"o{n:03d}"
        status = "canceled" if n % 20 == 7 else "delivered"
        deliver = "" if status == "canceled" else day(n + 8)
        orders.append([oid, f"c{n}", status, day(n // 2), day(n // 2), "", deliver, day(n // 2 + 20)])
        customers.append([f"c{n}", f"u{n}", "01000", "city", "SP" if n % 3 else "BA"])
        items.append([oid, 1, "pA" if n % 2 else "pB", "sellerAAAAAAAA" if n % 4 else "sellerBBBBBBBB", day(n), 10.0, 1.0])
        if n % 10 == 0:                                                   # a second product in the same order
            items.append([oid, 2, "pB" if n % 2 else "pA", "sellerAAAAAAAA", day(n), 5.0, 1.0])
    pd.DataFrame(orders, columns=["order_id", "customer_id", "order_status", "order_purchase_timestamp",
                                  "order_approved_at", "order_delivered_carrier_date",
                                  "order_delivered_customer_date", "order_estimated_delivery_date"]).to_csv(
        path / "olist_orders_dataset.csv", index=False)
    pd.DataFrame(items, columns=["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date",
                                 "price", "freight_value"]).to_csv(path / "olist_order_items_dataset.csv", index=False)
    pd.DataFrame(customers, columns=["customer_id", "customer_unique_id", "customer_zip_code_prefix",
                                     "customer_city", "customer_state"]).to_csv(
        path / "olist_customers_dataset.csv", index=False)
    pd.DataFrame({"product_id": ["pA", "pB"], "product_category_name": ["beleza_saude", "esporte_lazer"]}).to_csv(
        path / "olist_products_dataset.csv", index=False)
    pd.DataFrame({"product_category_name": ["beleza_saude", "esporte_lazer"],
                  "product_category_name_english": ["health_beauty", "sports_leisure"]}).to_csv(
        path / "product_category_name_translation.csv", index=False)


def test_adapter_maps_olist_onto_the_pipeline_schema(tmp_path, monkeypatch):
    raw, out = tmp_path / "raw", tmp_path / "out"
    make_raw(raw)
    monkeypatch.setattr(prepare_olist, "START", "2017-06-01")
    monkeypatch.setattr(prepare_olist, "MIN_SKU_UNITS", 5)
    monkeypatch.setattr(prepare_olist, "MIN_PAIR_UNITS", 3)
    monkeypatch.setattr(prepare_olist, "MIN_SELLER_LINES", 1)
    meta = prepare_olist.prepare(str(raw), str(out), as_of="2017-06-30")
    orders = pd.read_csv(out / "orders.csv")
    assert list(orders.columns) == ["order_id", "date", "sku", "category", "warehouse", "qty", "price"]
    assert set(orders.sku) == {"health_beauty", "sports_leisure"}
    assert set(orders.category) == {"Health & Beauty", "Leisure & Kids"}
    assert set(orders.warehouse) == {"SP", "NE"}                      # BA is mapped to the NE hub
    assert orders.date.max() <= "2017-06-30"
    ret = pd.read_csv(out / "returns.csv")
    assert len(ret) >= 1 and set(ret.reason) == {"canceled"}          # cancellations stand in for returns
    assert set(ret.order_id) <= set(orders.order_id)
    dl = pd.read_csv(out / "deliveries.csv")
    assert dl.delivered_date.isna().sum() == len(ret)                 # cancelled lines have no delivery date
    assert (dl[dl.delivered_date.isna()].qty_received == 0).all()
    inv = pd.read_csv(out / "inventory.csv")
    assert list(inv.columns) == ["sku", "warehouse", "on_hand", "on_order", "supplier_id", "nominal_lead_days"]
    assert set(inv.supplier_id) <= set(dl.supplier_id)                # every planned supplier has a scorecard row
    bp = pd.read_csv(out / "baskets_products.csv")
    assert bp.groupby("order_id").sku.nunique().max() == 2            # the two-product orders survive at product level
    m = json.load(open(out / "meta.json"))
    assert m["real_data"] is True and m["lanes"] and m["as_of"] == meta["as_of"] == "2017-06-30"


def test_every_olist_category_has_a_department():
    trans = ROOT / "data" / "raw" / "olist" / "product_category_name_translation.csv"
    if not trans.exists():
        pytest.skip("raw Olist data not downloaded")
    names = set(pd.read_csv(trans, encoding="utf-8-sig")["product_category_name_english"])
    assert names <= set(prepare_olist.DEPT_OF)


# ---------------------------------------------------------------- the whole pipeline on the real data
@pytest.mark.skipif(not (RAW / "olist_orders_dataset.csv").exists(), reason="raw Olist data not downloaded (make fetch)")
def test_pipeline_on_real_olist(tmp_path):
    data, out, reports = tmp_path / "data", tmp_path / "out", tmp_path / "reports"
    prepare_olist.prepare(str(RAW), str(data))
    env = {**os.environ, "DATA_DIR": str(data), "OUT_DIR": str(out), "REPORTS_DIR": str(reports)}
    r = subprocess.run([str(ROOT / "scripts/run_local.sh")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    gap = pd.read_csv(out / "gap_report.csv")
    assert len(gap) > 50 and set(gap.risk) >= {"CRITICAL", "OK"}
    assert (gap.lead_mean > 5).all()                                   # observed seller lead times, not defaults
    assert (gap.tier != "?").all()                                     # every planned supplier was scored
    upl = dict(l.split("\t") for l in open(out / "uplift.tsv") if l.startswith("CAT|"))
    assert all(float(v.split(",")[3]) > 1.5 for v in upl.values())    # Black Friday 2017 lifts every department
    assert (reports / "REPORT.md").read_text().startswith("# Results report: real data")
