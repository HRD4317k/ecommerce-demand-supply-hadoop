#!/usr/bin/env python3
"""Build reports/REPORT.md and its charts from the pipeline outputs (all 8 ideas)."""
import argparse
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from io_utils import (read_bundles, read_daily, read_gap, read_returns, read_suppliers,  # noqa: E402
                      read_uplift, schema)

SURF, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
STATUS = {"CRITICAL": "#d03b3b", "WATCH": "#fab219", "OK": "#0ca30c", "OVERSTOCK": BLUE}
TIER = {"A": "#0ca30c", "B": "#fab219", "C": "#d03b3b"}
plt.rcParams.update({"font.family": "DejaVu Sans", "figure.facecolor": SURF, "axes.facecolor": SURF,
                     "savefig.facecolor": SURF})


def style(ax, grid="y"):
    for s in ("top", "right", "left" if grid == "y" else "bottom"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom" if grid == "y" else "left"].set_color("#c3c2b7")
    ax.grid(axis=grid, color=GRID, lw=1)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, length=0)


def save(fig, path):
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def md_table(df, floats=2):
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        cells = [f"{v:.{floats}f}" if isinstance(v, float) else str(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------- charts
DEPT_COLORS = [ORANGE, BLUE, AQUA, YELLOW, "#8a63d2", "#d6498f", "#6b7280"]


def chart_weekly(orders, meta, path):
    o = orders.copy()
    o["week"] = pd.to_datetime(o["date"]).dt.to_period("W-SUN").dt.start_time
    w = o.groupby(["week", "category"])["qty"].sum().unstack()
    w = w.iloc[1:-1]                                  # first and last weeks are partial
    top = w.sum().sort_values(ascending=False).index[:5]
    fig, ax = plt.subplots(figsize=(8, 4))
    for cat, col in zip(top, DEPT_COLORS):
        ax.plot(w.index, w[cat], color=col, lw=2.0, marker="o" if len(w) < 40 else None, ms=4, mec=SURF, label=cat)
    start = pd.Timestamp(meta["sale_start"])
    end = pd.Timestamp(meta.get("sale_end") or meta["as_of"])
    if (end - start).days < 60:
        ax.axvspan(start, end + pd.Timedelta(days=1), color=INK2, alpha=0.15, lw=0)
    else:
        ax.axvline(start, color=INK2, ls=(0, (4, 3)), lw=1.2)
    ax.text(start, ax.get_ylim()[1] * 0.97, " " + meta.get("sale_name", "sale"), color=INK2, fontsize=9, va="top")
    ax.set_ylabel("units per week", color=INK2)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2 if len(w) > 30 else 1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax.legend(frameon=False, ncol=5, loc="upper left", bbox_to_anchor=(0, 1.1), labelcolor=INK2, fontsize=8.5)
    style(ax)
    save(fig, path)


def chart_risk(gap, path):
    t = gap.groupby(["warehouse", "risk"]).size().unstack(fill_value=0).reindex(columns=schema.RISK_ORDER, fill_value=0)
    fig, ax = plt.subplots(figsize=(7, 3.8))
    bottom = pd.Series(0, index=t.index)
    for risk in schema.RISK_ORDER:
        ax.bar(t.index, t[risk], bottom=bottom, color=STATUS[risk], width=0.55, label=risk, edgecolor=SURF, lw=2)
        for x, (v, b) in enumerate(zip(t[risk], bottom)):
            if v >= 3:
                ax.text(x, b + v / 2, str(v), ha="center", va="center", fontsize=9,
                        color=INK if risk in ("WATCH",) else "#ffffff", fontweight="bold")
        bottom = bottom + t[risk]
    ax.set_ylabel("SKUs", color=INK2)
    ax.legend(frameon=False, ncol=4, loc="upper left", bbox_to_anchor=(0, 1.1), labelcolor=INK2)
    style(ax)
    save(fig, path)


BUCKET_COLORS = {"normal": BLUE, "pre-sale": BLUE, "sale-shock": ORANGE, "in-sale": AQUA, "post-sale": YELLOW}


def chart_backtest(bt, path):
    t = bt[bt.bucket != "all"].pivot(index="method", columns="bucket", values="wape_week")
    t = t.reindex(bt[bt.bucket == "all"].sort_values("wape_week")["method"])
    cols = [(b, BUCKET_COLORS[b]) for b in ["normal", "pre-sale", "sale-shock", "in-sale", "post-sale"] if b in t]
    fig, ax = plt.subplots(figsize=(8.5, 3.9))
    width = 0.8 / len(cols)
    for k, (b, col) in enumerate(cols):
        xs = [i + (k - (len(cols) - 1) / 2) * width for i in range(len(t))]
        ax.bar(xs, t[b], width=width * 0.92, color=col, label=b)
        for x, v in zip(xs, t[b]):
            ax.text(x, v + 0.01, f"{v:.2f}", ha="center", fontsize=7, color=INK2)
    ax.set_xticks(range(len(t)))
    ax.set_xticklabels(t.index, fontsize=9, color=INK2)
    ax.set_ylabel("7-day WAPE (lower is better)", color=INK2)
    ax.legend(frameon=False, ncol=len(cols), loc="upper left", bbox_to_anchor=(0, 1.1), labelcolor=INK2)
    style(ax)
    save(fig, path)


def chart_uplift(upl, path):
    c = upl[upl.scope == "CAT"].sort_values("uplift")
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.barh(c["name"], c["uplift"], color=BLUE, height=0.55)
    for y, v in enumerate(c["uplift"]):
        ax.text(v + 0.03, y, f"{v:.2f}x", va="center", color=INK2, fontsize=9)
    ax.set_xlim(0, c["uplift"].max() * 1.2)
    ax.set_xlabel("weekday-adjusted uplift vs the 28 days before the sale", color=INK2)
    style(ax, "x")
    save(fig, path)


def chart_suppliers(sup, path, top=12):
    s = sup.sort_values("n_pos", ascending=False).head(top).sort_values("score", ascending=False)
    fig, ax = plt.subplots(figsize=(8, 3.8))
    bars = ax.bar(s["supplier_id"], s["score"], color=[TIER[t] for t in s["tier"]], width=0.6)
    for b, (_, r) in zip(bars, s.iterrows()):
        ax.text(b.get_x() + b.get_width() / 2, r["score"] + 1.2, f"{r['score']:.0f}\n({r['tier']})", ha="center",
                fontsize=8, color=INK2)
    ax.set_ylim(0, 108)
    ax.set_ylabel("scorecard (0-100)", color=INK2)
    ax.set_title(f"the {len(s)} suppliers with the most order lines", color=INK2, fontsize=9, loc="left")
    plt.setp(ax.get_xticklabels(), rotation=35, ha="right", fontsize=8)
    style(ax)
    save(fig, path)


def chart_bundles(bun, path, labels=None):
    b = bun.head(8).iloc[::-1]
    name = lambda x: (labels or {}).get(x, x)
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    ax.barh([name(a) + " + " + name(c) for a, c in zip(b["sku_a"], b["sku_b"])], b["lift"], color=AQUA, height=0.6)
    for y, v in enumerate(b["lift"]):
        ax.text(v * 1.01 + 0.02, y, f"lift {v:.1f}", va="center", color=INK2, fontsize=9)
    ax.axvline(1, color=INK2, ls=(0, (4, 3)), lw=1)
    ax.set_xlim(0, b["lift"].max() * 1.2)
    ax.tick_params(axis="y", labelsize=8)
    style(ax, "x")
    save(fig, path)


def chart_returns(ret, path, label="returned"):
    c = ret[ret.scope == "CAT"].sort_values("return_rate", ascending=False)
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    ax.bar(c["name"], c["return_rate"] * 100, color=ORANGE, width=0.55)
    for x, v in enumerate(c["return_rate"] * 100):
        ax.text(x, v + max(c["return_rate"] * 100) * 0.02, f"{v:.1f}%", ha="center", color=INK2, fontsize=9)
    ax.set_ylabel(f"share of units {label}", color=INK2)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right", fontsize=8.5)
    style(ax)
    save(fig, path)


# ---------------------------------------------------------------- report
def read_if(path, reader):
    return reader(path) if os.path.exists(path) else None


def build(data, out, reports):
    figs = os.path.join(reports, "figures")
    os.makedirs(figs, exist_ok=True)
    meta = json.load(open(os.path.join(data, "meta.json")))
    real = bool(meta.get("real_data"))
    money = meta.get("currency", "Rs")
    rlabel = meta.get("returns_label", "returns")
    orders = pd.read_csv(os.path.join(data, "orders.csv"))
    deliveries = pd.read_csv(os.path.join(data, "deliveries.csv"))
    gap = read_gap(os.path.join(out, "gap_report.csv"))
    daily = read_daily(os.path.join(out, "daily_demand.tsv"))
    sup = read_suppliers(os.path.join(out, "supplier_stats.tsv"))
    upl = read_uplift(os.path.join(out, "uplift.tsv"))
    bun = read_bundles(os.path.join(out, "bundles.tsv"))
    bun_p = read_if(os.path.join(out, "bundles_products.tsv"), read_bundles)
    ret = read_returns(os.path.join(out, "return_rates.tsv"))
    bt = pd.read_csv(os.path.join(out, "backtest.csv"))
    btsum = json.load(open(os.path.join(out, "backtest_summary.json")))
    tr = pd.read_csv(os.path.join(out, "transfers.csv"))
    alerts = pd.read_csv(os.path.join(out, "alerts.csv"))
    bal = pd.read_csv(os.path.join(out, "bundle_alerts.csv"))
    rsum = json.load(open(os.path.join(out, "rebalance_summary.json")))

    # product -> category labels for the product-level bundle view
    labels = {}
    pb_path = os.path.join(data, "baskets_products.csv")
    if bun_p is not None and os.path.exists(pb_path):
        pb = pd.read_csv(pb_path, usecols=["sku", "category"]).drop_duplicates("sku")
        labels = {p: f"{p} ({c})" for p, c in zip(pb["sku"], pb["category"])}

    chart_weekly(orders, meta, os.path.join(figs, "weekly_demand.png"))
    chart_risk(gap, os.path.join(figs, "risk_by_warehouse.png"))
    chart_backtest(bt, os.path.join(figs, "backtest.png"))
    chart_uplift(upl, os.path.join(figs, "uplift.png"))
    chart_suppliers(sup, os.path.join(figs, "suppliers.png"))
    chart_bundles(bun_p if bun_p is not None and len(bun_p) else bun, os.path.join(figs, "bundles.png"), labels)
    chart_returns(ret, os.path.join(figs, "returns.png"), rlabel)

    counts = gap["risk"].value_counts()
    method = gap["method"].iloc[0]
    overall = bt[bt.bucket == "all"].sort_values("wape_week")
    best = overall.iloc[0]["method"]
    by_bucket = bt[(bt.method == best) & (bt.bucket != "all")].set_index("bucket")
    shock = by_bucket.loc["sale-shock"] if "sale-shock" in by_bucket.index else None

    # supplier quote vs observed (the quote is the promised date minus the order date)
    d = deliveries.assign(quoted=(pd.to_datetime(deliveries["promised_date"]) -
                                  pd.to_datetime(deliveries["order_date"])).dt.days)
    quoted = d.groupby("supplier_id")["quoted"].mean().rename("quoted_lead")
    sc = sup.set_index("supplier_id").join(quoted).reset_index()
    sc["lead_gap"] = sc["lead_mean"] - sc["quoted_lead"]
    tiers = sc["tier"].value_counts().reindex(["A", "B", "C"], fill_value=0)
    big = sc[sc["n_pos"] >= 30]
    tiers_big = big["tier"].value_counts().reindex(["A", "B", "C"], fill_value=0)
    weights = sc["n_pos"]
    avg_gap = float((sc["lead_gap"] * weights).sum() / weights.sum())
    top_sc = sc.sort_values("n_pos", ascending=False).head(10)

    last28 = daily[daily["date"] > (pd.to_datetime(meta["as_of"]) - pd.Timedelta(days=28)).strftime("%Y-%m-%d")]
    gross, net = int(last28["ordered"].sum()), int(last28["net"].sum())
    crit = gap[gap.risk == "CRITICAL"].sort_values(["days_late", "cover_days"], ascending=[False, True]).head(8)
    cat_upl = upl[upl.scope == "CAT"]
    skus = upl[(upl.scope == "SKU") & (upl.base_avg_day >= 3)].sort_values("uplift", ascending=False)

    # the sale day itself (the weekday-adjusted uplift averages a whole sale window)
    per_day = orders.groupby("date")["qty"].sum()
    base = per_day[(per_day.index >= (pd.Timestamp(meta["sale_start"]) - pd.Timedelta(days=28)).strftime("%Y-%m-%d"))
                   & (per_day.index < meta["sale_start"])].mean()
    day_one = per_day.get(meta["sale_start"], float("nan"))

    baskets = orders.groupby("order_id")["sku"].nunique()
    multi = float((baskets > 1).mean())
    multi_p = None
    if os.path.exists(pb_path):
        multi_p = float((pd.read_csv(pb_path, usecols=["order_id", "sku"]).groupby("order_id")["sku"].nunique() > 1).mean())

    if real:
        title = f"# Results report: real data, as of {meta['as_of']}"
        intro = (f"Generated by `scripts/run_local.sh` on **real data**: {meta['dataset']}. Orders, regions, sellers, "
                 "promised and actual delivery dates and cancellations are real. Stock levels and inter-hub freight are "
                 "not in any public retail dataset and are ASSUMED (see Caveats). Read the stock-out counts as an "
                 "illustration of the method, and the demand, lead-time and uplift numbers as findings.")
    else:
        title = f"# Results report (synthetic data, as of {meta['as_of']})"
        intro = ("Generated by `scripts/run_local.sh`. All data is synthetic, so these numbers show that the pipeline "
                 "works, not how any real store behaves.")

    lines = [title, "", intro, "",
             "| | |", "|---|---|",
             f"| Order lines / orders | {len(orders):,} / {orders['order_id'].nunique():,} |",
             f"| Planned SKU-warehouse pairs | {len(gap)} |",
             f"| Risk | {counts.get('CRITICAL', 0)} CRITICAL, {counts.get('WATCH', 0)} WATCH, "
             f"{counts.get('OK', 0)} OK, {counts.get('OVERSTOCK', 0)} OVERSTOCK |",
             f"| Forecast method in use | `{method}` (chosen by the backtest) |",
             f"| Transfers proposed | {rsum['transfers']} ({rsum['units_moved']} units, {money} {rsum['freight_cost']:,.0f} freight) |",
             f"| Sale uplift ({meta.get('sale_name', 'sale')}) | {cat_upl['uplift'].mean():.2f}x average across categories |", "",
             "## Idea 1. Demand forecasting", "",
             f"Six methods are scored with a rolling-origin backtest ({btsum.get('origins', '?')} origin dates x "
             f"{btsum.get('series', '?')} series, 7-day horizon). Lower WAPE is better.", "",
             "![backtest](figures/backtest.png)", "",
             md_table(overall[["method", "wape_week", "wape_daily", "bias"]].reset_index(drop=True), 3), "",
             f"`{best}` has the lowest 7-day WAPE overall, so the gap engine uses it. "
             + (f"When the sale starts inside the forecast window every method is far off (the best one is "
                f"{shock['bias']:+.0%} biased, WAPE {shock['wape_week']:.2f}): no history-based method sees a promotion "
                "coming, so the planned promotion calendar has to be fed in as a feature. " if shock is not None else "")
             + ("Seasonal and day-of-week methods did NOT beat the simple averages here because most category/hub "
                "series are small and noisy." if real else ""), "",
             "## Idea 2. Stock-out early warning", "",
             "![risk](figures/risk_by_warehouse.png)", "",
             ("Stock levels are an assumed snapshot, so WHICH pairs are critical is illustrative; the lead times, "
              "demand forecasts and safety stocks behind the thresholds come from the real data." if real else ""), "",
             "Most urgent pairs (stock-out expected before a new order could arrive):", "",
             md_table(crit[["sku", "warehouse", "supplier_id", "tier", "on_hand", "cover_days", "lead_mean",
                            "days_late", "order_qty"]].reset_index(drop=True), 1), "",
             f"Full list with actions: `alerts.csv` ({len(alerts)} rows).", "",
             "## Idea 3. Smart reorder points", "",
             "An (s, S) policy: safety stock `z * sqrt(L*sd_d^2 + d^2*sd_L^2)` at a 95% service level, using the "
             "supplier's OBSERVED lead-time mean and spread, not the quoted lead time. `gap_report.csv` holds "
             "`safety_stock`, `reorder_point`, `order_up_to`, `order_qty` and the latest safe `order_by` date; "
             "`purchase_orders.csv` is the resulting order list after transfers.", "",
             (f"On this data the observed lead time averages {gap['lead_mean'].mean():.1f} days with a spread of "
              f"{gap['lead_std'].mean():.1f} days, so the lead-time term dominates safety stock "
              f"(median reorder point {gap['reorder_point'].median():.0f} units against a median daily demand of "
              f"{gap['forecast_day'].median():.1f})." if real else ""), "",
             "## Idea 4. Warehouse rebalancing", "",
             f"An integer linear program per SKU moves surplus stock to short warehouses when that beats the "
             f"supplier lead time: **{rsum['transfers']} transfers, {rsum['units_moved']} units, "
             f"{money} {rsum['freight_cost']:,.0f} freight** across {rsum['skus_helped']} SKUs. "
             "Lane costs and transfer days are assumptions.", "",
             md_table(tr.head(8), 0), "",
             "## Idea 5. Sale uplift", "",
             "![uplift](figures/uplift.png)", "",
             (f"{meta.get('sale_name', 'The sale')} ({meta['sale_start']} to {meta.get('sale_end', meta['as_of'])}) "
              f"is a real event. Units on the first day were {day_one / base:.1f}x the average day of the previous 28 days; "
              "the uplift below is weekday-adjusted and averaged over the whole sale window, so it is lower than the "
              "peak day. " if real else
              "Uplift is weekday-adjusted against the 28 days before the sale. It includes the organic upward trend "
              "(0.4% per day in the generator), so it reads slightly above the planted 1.9x. "),
             "", md_table(cat_upl[["name", "base_avg_day", "sale_avg_day", "plain_ratio", "uplift"]]
                          .rename(columns={"name": "category"}).reset_index(drop=True), 2), "",
             "Highest-uplift SKUs (at least 3 units/day before the sale): "
             + ", ".join(f"{r.name} ({r.uplift:.2f}x)" for r in skus.head(5).itertuples())
             + ". Low-volume SKUs are noisy.", "",
             "![weekly](figures/weekly_demand.png)", "",
             "## Idea 6. Supplier scorecard", "",
             "![suppliers](figures/suppliers.png)", "",
             f"{len(sc):,} suppliers scored: {tiers['A']} tier A, {tiers['B']} tier B, {tiers['C']} tier C "
             f"({len(big)} have at least 30 order lines: {tiers_big['A']} A, {tiers_big['B']} B, {tiers_big['C']} C; "
             "scores of tiny sellers are noisy). "
             f"Volume-weighted, observed lead time minus the quoted one is {avg_gap:+.1f} days "
             + ("(negative = the quotes are padded; planning on them would overstock)." if avg_gap < 0 else
                "(positive = the quotes are optimistic; planning on them would understock)."), "",
             md_table(top_sc[["supplier_id", "n_pos", "on_time_rate", "quoted_lead", "lead_mean", "lead_gap",
                              "lead_std", "fill_rate", "score", "tier"]].reset_index(drop=True), 2), "",
             "The ten suppliers with the most order lines are shown; the full list is `supplier_stats.tsv`.", "",
             "## Idea 7. Bundle pre-positioning", "",
             "![bundles](figures/bundles.png)", "",
             f"{multi:.1%} of orders contain more than one {'category' if real else 'SKU'}"
             + (f" and {multi_p:.1%} contain more than one product" if multi_p is not None else "") + ". "
             + ("Pairs, best lift first (lift near 1 or below = no association):" if len(bun)
                else "No pair is frequent enough."), "",
             md_table(bun.head(6).reset_index(drop=True), 3) if len(bun) else "", ""]
    if bun_p is not None and len(bun_p):
        shown = bun_p.head(8).copy()
        shown["sku_a"] = shown["sku_a"].map(lambda x: labels.get(x, x))
        shown["sku_b"] = shown["sku_b"].map(lambda x: labels.get(x, x))
        lines += ["Product-level pairs (ids are the dataset's anonymised product ids):", "",
                  md_table(shown.reset_index(drop=True), 3), "",
                  "Lift far above 1 means the two products are bought together much more than chance. "
                  "With so few multi-product orders only a handful of pairs have enough baskets to trust."
                  if real else "", ""]
    lines += [f"{len(bal)} bundle alerts in `bundle_alerts.csv` (one item of a strong bundle is short; lift >= 3).", "",
              f"## Idea 8. Returns-adjusted demand ({rlabel})", "",
              "![returns](figures/returns.png)", "",
              md_table(ret[ret.scope == "CAT"][["name", "ordered", "returned", "return_rate"]]
                       .rename(columns={"name": "category"}).reset_index(drop=True), 4), "",
              f"Over the last 28 days gross demand was {gross:,} units and net demand {net:,} "
              f"({(gross - net) / gross:.1%} lower). The forecast uses NET demand"
              + (", where net = ordered minus cancelled. The dataset has no returns table, so cancelled orders are "
                 "the nearest real signal; they carry no cancel date and are booked on the order day. The effect is "
                 "tiny here; with a retailer's real returns feed (typically 5-20% in fashion) this idea matters far more."
                 if real else ", with returns counted on the day the goods come back."), "",
              "## Caveats", ""]
    if real:
        lines += ["- Real data from one Brazilian marketplace (2017-2018); results describe that market, not yours.",
                  "- Warehouse stock is NOT in the data. `inventory.csv` is a seeded snapshot (days of cover on top of "
                  "real recent demand), so stock-out counts and transfers are illustrative.",
                  "- Freight cost and transfer days between hubs are assumptions (`meta.json`, `lanes`).",
                  "- Supplier lead time is the seller's observed order-to-delivery time to the customer, used as a proxy "
                  "for replenishment lead time. Quoted lead time is the delivery estimate shown to the customer.",
                  "- Cancellations stand in for returns; they have no timestamp.",
                  "- Categories are the planning unit (SKU) because individual products sell too rarely; the five "
                  "regional hubs are groups of customer states, not real warehouses.",
                  "- Orders after the last stable day are dropped (the dataset thins out at the end).",
                  "- Bundle lift for rare pairs is noisy; `MIN_PAIR_COUNT` drops pairs seen in too few baskets.", ""]
    else:
        lines += ["- Synthetic data: results validate the pipeline, not a business.",
                  "- The rolling backtest runs on the generator's own patterns; re-run it on real data before trusting a method.",
                  "- Returns are counted on the return date, so recent order days look better than they will once their returns arrive.",
                  "- Freight cost and transfer time per lane are assumptions (`rebalance.DEFAULT_LANES`).",
                  "- Bundle lift for rare pairs is noisy; `MIN_PAIR_COUNT` drops pairs seen in fewer than 15 baskets.", ""]
    with open(os.path.join(reports, "REPORT.md"), "w") as handle:
        handle.write("\n".join(lines))
    return os.path.join(reports, "REPORT.md")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--reports", required=True)
    a = ap.parse_args()
    print("wrote", build(a.data, a.out, a.reports))


if __name__ == "__main__":
    main()
