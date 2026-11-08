import datetime as dt

import pytest

import forecast
import policy


def series(values, start="2026-01-01"):
    d0 = dt.date.fromisoformat(start)
    return {(d0 + dt.timedelta(days=i)).isoformat(): v for i, v in enumerate(values)}


def test_flat_series_is_forecast_flat_by_every_method():
    s = series([10] * 40)
    for m in forecast.METHODS:
        f = forecast.forecast(s, 5, m)
        assert len(f) == 5
        assert all(x == pytest.approx(10, rel=0.05) for x in f), m


def test_naive7_is_last_week_average():
    s = series([0] * 33 + [7] * 7)
    assert forecast.forecast(s, 3, "naive7") == [7, 7, 7]


def test_unknown_method_rejected():
    with pytest.raises(ValueError):
        forecast.forecast(series([1] * 30), 3, "magic")


def test_missing_days_count_as_zero_demand():
    s = {"2026-01-10": 14}
    dates, vals = forecast.dense(s, 7, end="2026-01-14")
    assert len(vals) == 7 and sum(vals) == 14


def test_demand_std_of_constant_is_zero():
    assert forecast.demand_std(series([5] * 20), 14) == 0


def test_z_value_95():
    assert policy.z_value(0.95) == pytest.approx(1.645, abs=1e-3)


def base_args(**kw):
    a = dict(on_hand=100, on_order=0, forecast_by_day=[10.0] * 30, sigma_d=2.0, lead_mean=5.0,
             lead_std=1.0, fill_rate=1.0)
    a.update(kw)
    return a


def test_safety_stock_formula():
    r = policy.plan(**base_args())
    expected = 1.645 * (5 * 4 + 100 * 1) ** 0.5
    assert r["safety_stock"] == pytest.approx(expected, rel=1e-3)
    assert r["reorder_point"] == pytest.approx(50 + expected, rel=1e-3)


def test_lead_time_uncertainty_raises_safety_stock():
    low = policy.plan(**base_args(lead_std=0.0))["safety_stock"]
    high = policy.plan(**base_args(lead_std=3.0))["safety_stock"]
    assert high > low


def test_risk_labels():
    assert policy.plan(**base_args(on_hand=20))["risk"] == "CRITICAL"
    assert policy.plan(**base_args(on_hand=60))["risk"] == "WATCH"
    assert policy.plan(**base_args(on_hand=200))["risk"] == "OK"
    assert policy.plan(**base_args(on_hand=2000))["risk"] == "OVERSTOCK"


def test_order_quantity_and_fill_rate_gross_up():
    full = policy.plan(**base_args(on_hand=20, fill_rate=1.0))
    short = policy.plan(**base_args(on_hand=20, fill_rate=0.8))
    assert full["order_qty"] > 0
    assert short["order_qty"] > full["order_qty"]
    assert policy.plan(**base_args(on_hand=500))["order_qty"] == 0


def test_stock_on_order_counts_towards_position():
    no_po = policy.plan(**base_args(on_hand=20))
    with_po = policy.plan(**base_args(on_hand=20, on_order=200))
    assert with_po["order_qty"] == 0 < no_po["order_qty"]


def test_horizon_needed_covers_plan():
    n = policy.horizon_needed(5.3, 7)
    policy.plan(**base_args(forecast_by_day=[1.0] * n, lead_mean=5.3))
