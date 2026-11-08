"""Reorder policy and stock-out risk (ideas 2 and 3).

An (s, S) policy with a statistically derived safety stock:

    lead-time demand   LTD = sum of the forecast over the supplier lead time L
    safety stock       SS  = z * sqrt(L * sigma_d^2 + d^2 * sigma_L^2)
    reorder point      s   = LTD + SS
    order-up-to level  S   = LTD + demand over the review period + SS

``z`` comes from the target service level, ``sigma_d`` is the std-dev of daily demand
and ``sigma_L`` the std-dev of the supplier lead time (from the supplier scorecard).
An order is triggered when the inventory position (on hand + on order) is at or below
``s``; it brings the position back to ``S``, grossed up by the supplier fill rate.
"""
import math
from statistics import NormalDist


def z_value(service_level):
    return NormalDist().inv_cdf(service_level)


def horizon_needed(lead_mean, review_days):
    """Number of forecast days ``plan`` needs."""
    return math.ceil(max(lead_mean, 1.0)) + review_days + 1


def plan(*, on_hand, on_order, forecast_by_day, sigma_d, lead_mean, lead_std, fill_rate,
         service_level=0.95, review_days=7, overstock_days=45):
    lead = max(float(lead_mean), 1.0)
    whole = int(lead)
    frac = lead - whole
    f = list(forecast_by_day)
    ltd = sum(f[:whole]) + frac * f[whole]
    d_bar = ltd / lead
    z = z_value(service_level)
    safety = z * math.sqrt(lead * sigma_d ** 2 + d_bar ** 2 * lead_std ** 2)
    rop = ltd + safety
    start = math.ceil(lead)
    review_demand = sum(f[start:start + review_days])
    order_up_to = ltd + review_demand + safety
    position = on_hand + on_order
    cover = min(on_hand / d_bar, 999.0) if d_bar > 0 else 999.0

    qty = 0
    if position <= rop:
        qty = math.ceil(max(0.0, order_up_to - position) / max(fill_rate, 0.5))

    if on_hand < ltd and position < rop:
        risk = "CRITICAL"            # empty before a new order could arrive, pipeline too thin
    elif position < rop:
        risk = "WATCH"               # below the reorder point: order now
    elif cover > overstock_days:
        risk = "OVERSTOCK"
    else:
        risk = "OK"

    if position > rop and d_bar > 0:
        order_in_days = int((position - rop) / d_bar)   # whole days until the position hits s
    else:
        order_in_days = 0
    days_late = max(0, math.ceil(lead - cover)) if on_hand < ltd else 0

    return {"forecast_day": d_bar, "safety_stock": safety, "reorder_point": rop,
            "order_up_to": order_up_to, "cover_days": cover, "risk": risk,
            "order_qty": qty, "order_in_days": order_in_days, "days_late": days_late}
