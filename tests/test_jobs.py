import datetime as dt

import pytest

from conftest import run_job, shuffle


def test_daily_demand_orders_and_returns_net():
    orders = "order_id,date,sku,category,warehouse,qty,price\n1,2026-08-01,A1,Home,KOL,3,10\n2,2026-08-01,A1,Home,KOL,2,10\n"
    returns = "return_id,order_id,sku,category,warehouse,return_date,qty,reason\nR1,1,A1,Home,KOL,2026-08-01,1,x\n"
    m = run_job("daily_demand_map.py", orders, {"mapreduce_map_input_file": "/data/orders.csv"})
    m += run_job("daily_demand_map.py", returns, {"mapreduce_map_input_file": "/data/returns.csv"})
    out = run_job("sum_reduce.py", shuffle(m))
    assert out == ["A1|KOL|2026-08-01\t5,1,4"]


def test_daily_demand_detects_returns_without_file_name():
    returns = "R1,1,A1,Home,KOL,2026-08-02,2,x\n"
    out = run_job("daily_demand_map.py", returns)
    assert out == ["A1|KOL|2026-08-02\t0,2,-2"]


def test_sum_reduce_keeps_keys_separate():
    out = run_job("sum_reduce.py", "a\t1,2\na\t3,4\nb\t5,6\n")
    assert out == ["a\t4,6", "b\t5,6"]


def test_supplier_scorecard():
    rows = "po_id,supplier_id,sku,warehouse,order_date,promised_date,delivered_date,qty_ordered,qty_received\n"
    rows += "P1,S1,X,KOL,2026-09-01,2026-09-05,2026-09-05,100,100\n"      # on time, lead 4
    rows += "P2,S1,X,KOL,2026-09-10,2026-09-14,2026-09-16,100,80\n"       # 2 days late, lead 6, 80% fill
    m = run_job("supplier_map.py", rows)
    out = run_job("supplier_reduce.py", shuffle(m))
    assert len(out) == 1
    key, _, val = out[0].partition("\t")
    f = val.split(",")
    assert key == "S1"
    assert float(f[1]) == pytest.approx(0.5)            # on-time rate
    assert float(f[3]) == pytest.approx(5.0)            # observed lead mean
    assert float(f[5]) == pytest.approx(0.9)            # fill rate = 180/200


def test_uplift_two_x_after_weekday_adjustment(tmp_path):
    start = dt.date(2026, 10, 25)
    lines = []
    oid = 1
    for i in range(-28, 7):
        d = start + dt.timedelta(days=i)
        qty = 10 * (2 if i >= 0 else 1) * (3 if d.weekday() >= 5 else 1)   # weekend peak, sale doubles it
        lines.append(f"{oid},{d.isoformat()},S1,Home,KOL,{qty},1")
        oid += 1
    m = run_job("uplift_map.py", "\n".join(lines) + "\n", {"SALE_START": start.isoformat(), "AS_OF": "2026-11-01"})
    out = dict(x.split("\t") for x in run_job("uplift_reduce.py", shuffle(m)))
    f = out["CAT|Home"].split(",")
    assert float(f[3]) == pytest.approx(2.0, abs=0.01)   # weekday-adjusted uplift


def test_bundles_lift_on_known_baskets():
    # 100 baskets: A+B together in 20, A alone 10, B alone 10, 60 baskets of C
    rows = []
    n = 1
    for items, times in ((("A", "B"), 20), (("A",), 10), (("B",), 10), (("C",), 60)):
        for _ in range(times):
            rows += [f"{n},2026-09-01,{s},Home,KOL,1,1" for s in items]
            n += 1
    text = "\n".join(rows) + "\n"
    pairs = run_job("cooccur_map.py", text)
    counted = run_job("sum_reduce.py", shuffle(run_job("cooccur_pairs_reduce.py", shuffle(pairs))))
    out = run_job("cooccur_metrics_reduce.py", shuffle(run_job("cooccur_metrics_map.py", "\n".join(counted) + "\n")),
                  {"MIN_PAIR_COUNT": "5"})
    assert len(out) == 1
    key, _, val = out[0].partition("\t")
    f = [float(x) for x in val.split(",")]
    assert key == "A|B"
    assert f[0] == 20
    pair_orders, support, conf_ab, conf_ba, lift = f
    assert support == pytest.approx(0.20, abs=0.001)
    assert conf_ab == pytest.approx(20 / 30, abs=0.001)
    assert conf_ba == pytest.approx(20 / 30, abs=0.001)
    assert lift == pytest.approx(20 * 100 / (30 * 30), abs=0.01)     # P(AB) / (P(A) P(B)) = 2.22


def test_return_rates():
    orders = "1,2026-09-01,S1,Home,KOL,10,1\n"
    returns = "R1,1,S1,Home,KOL,2026-09-05,2,x\n"
    m = run_job("return_rate_map.py", orders, {"mapreduce_map_input_file": "orders.csv"})
    m += run_job("return_rate_map.py", returns, {"mapreduce_map_input_file": "returns.csv"})
    out = dict(x.split("\t") for x in run_job("return_rate_reduce.py", shuffle(m)))
    assert out["CAT|Home"] == "10,2,0.2000"
    assert out["SKU|S1"] == "10,2,0.2000"
