import datetime as dt

import pandas as pd
import pytest

import rebalance
import schema
from conftest import run_job, shuffle


def gap_run(on_hand, daily=10, lead_mean=5.0, days=40):
    end = dt.date(2026, 11, 8)
    demand = []
    for i in range(days):
        d = end - dt.timedelta(days=days - 1 - i)
        demand.append(f"X1|KOL|{d.isoformat()}\t{daily},0,{daily}")
    inv = f"X1,KOL,{on_hand},0,SUP9,5\n"
    stats = f"SUP9\t50,0.8,0.5,{lead_mean},1.0,0.95,80.0,B\n"
    return demand, inv, stats


def test_gap_engine_joins_demand_inventory_and_supplier(tmp_path):
    demand, inv, stats = gap_run(on_hand=20)
    sf = tmp_path / "supplier_stats.tsv"
    sf.write_text(stats)
    env = {"SUPPLIER_STATS_FILE": str(sf), "AS_OF": "2026-11-08"}
    m = run_job("gap_map.py", "\n".join(demand) + "\n", {**env, "mapreduce_map_input_file": "daily_demand/part-00000"})
    m += run_job("gap_map.py", inv, {**env, "mapreduce_map_input_file": "inventory.csv"})
    out = run_job("gap_reduce.py", shuffle(m), env)
    assert len(out) == 1
    row = dict(zip(schema.GAP_FIELDS, out[0].split(",")))
    assert row["sku"] == "X1" and row["warehouse"] == "KOL" and row["supplier_id"] == "SUP9"
    assert row["tier"] == "B"
    assert row["risk"] == "CRITICAL"            # 20 units on hand, ~50 needed over the lead time
    assert float(row["lead_mean"]) == pytest.approx(5.0)   # observed, not the nominal 5
    assert int(row["order_qty"]) > 0
    assert float(row["reorder_point"]) > 50


def test_gap_engine_healthy_stock_is_ok(tmp_path):
    demand, inv, stats = gap_run(on_hand=300)
    sf = tmp_path / "supplier_stats.tsv"
    sf.write_text(stats)
    env = {"SUPPLIER_STATS_FILE": str(sf), "AS_OF": "2026-11-08"}
    m = run_job("gap_map.py", "\n".join(demand) + "\n", {**env, "mapreduce_map_input_file": "daily_demand/part-00000"})
    m += run_job("gap_map.py", inv, {**env, "mapreduce_map_input_file": "inventory.csv"})
    row = dict(zip(schema.GAP_FIELDS, run_job("gap_reduce.py", shuffle(m), env)[0].split(",")))
    assert row["risk"] == "OK" and int(row["order_qty"]) == 0


def gap_df(rows):
    base = dict(sku="S1", reorder_point=100, order_up_to=200, lead_mean=7.0, on_order=0)
    return pd.DataFrame([{**base, **r} for r in rows])


def test_lp_moves_surplus_to_short_warehouse():
    gap = gap_df([
        dict(warehouse="KOL", on_hand=500, risk="OVERSTOCK"),
        dict(warehouse="DEL", on_hand=40, risk="CRITICAL"),
    ])
    t = rebalance.rebalance(gap)
    assert len(t) == 1
    r = t.iloc[0]
    assert (r["from"], r["to"]) == ("KOL", "DEL")
    assert r["units"] == 60                       # need = reorder point 100 - position 40
    assert r["freight_cost"] == 60 * 18


def test_lp_never_gives_more_than_the_surplus():
    gap = gap_df([
        dict(warehouse="KOL", on_hand=230, risk="OVERSTOCK"),     # surplus 30 above S=200
        dict(warehouse="DEL", on_hand=10, risk="CRITICAL"),       # needs 90
    ])
    t = rebalance.rebalance(gap)
    assert t["units"].sum() == 30


def test_lp_prefers_the_cheaper_donor():
    gap = gap_df([
        dict(warehouse="KOL", on_hand=500, risk="OVERSTOCK"),
        dict(warehouse="BLR", on_hand=500, risk="OVERSTOCK"),
        dict(warehouse="DEL", on_hand=40, risk="CRITICAL"),
    ])
    t = rebalance.rebalance(gap)
    assert set(t["from"]) == {"KOL"}               # KOL-DEL costs 18/unit, DEL-BLR 20


def test_lp_skips_lane_slower_than_supplier():
    # transfer takes 3 days but the supplier delivers in 2: a normal PO is as fast, so no transfer
    gap = gap_df([
        dict(warehouse="KOL", on_hand=500, risk="OVERSTOCK"),
        dict(warehouse="DEL", on_hand=40, risk="CRITICAL", lead_mean=2.0),
    ])
    assert rebalance.rebalance(gap).empty
