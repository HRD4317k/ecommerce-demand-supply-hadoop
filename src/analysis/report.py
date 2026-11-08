#!/usr/bin/env python3
"""Build reports/REPORT.md and its charts from the pipeline outputs (all 8 ideas)."""
import argparse
import json
import os

import matplotlib

matplotlib.use("Agg")
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
def chart_weekly(orders, sale_start, path):
    o = orders.copy()
    o["week"] = pd.to_datetime(o["date"]).dt.to_period("W-SUN").dt.start_time
    w = o.groupby(["week", "category"])["qty"].sum().unstack()
    w = w.iloc[1:]                                   # first week is partial
    fig, ax = plt.subplots(figsize=(8, 4))
    for cat, col in zip(["Fashion", "Electronics", "Home", "Grocery"], [ORANGE, BLUE, AQUA, YELLOW]):
        ax.plot(w.index, w[cat], color=col, lw=2.2, marker="o", ms=4, mec=SURF, label=cat)
    ax.axvline(pd.Timestamp(sale_start), color=INK2, ls=(0, (4, 3)), lw=1.2)
    ax.text(pd.Timestamp(sale_start), ax.get_ylim()[1] * 0.97, " sale starts", color=INK2, fontsize=9, va="top")
    ax.set_ylabel("units per week", color=INK2)
    ax.legend(frameon=False, ncol=4, loc="upper left", bbox_to_anchor=(0, 1.1), labelcolor=INK2)
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


def chart_backtest(bt, path):
    t = bt[bt.bucket != "all"].pivot(index="method", columns="bucket", values="wape_week")
    t = t.reindex(bt[bt.bucket == "all"].sort_values("wape_week")["method"])
    cols = [("pre-sale", BLUE), ("sale-shock", ORANGE), ("in-sale", AQUA)]
    fig, ax = plt.subplots(figsize=(8, 3.9))
    width = 0.26
    for k, (b, col) in enumerate(cols):
        xs = [i + (k - 1) * width for i in range(len(t))]
        ax.bar(xs, t[b], width=width * 0.92, color=col, label=b)
        for x, v in zip(xs, t[b]):
            ax.text(x, v + 0.008, f"{v:.2f}", ha="center", fontsize=7.5, color=INK2)
    ax.set_xticks(range(len(t)))
    ax.set_xticklabels(t.index, fontsize=9, color=INK2)
    ax.set_ylabel("7-day WAPE (lower is better)", color=INK2)
    ax.legend(frameon=False, ncol=3, loc="upper left", bbox_to_anchor=(0, 1.1), labelcolor=INK2)
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


def chart_suppliers(sup, path):
    s = sup.sort_values("score", ascending=False)
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    bars = ax.bar(s["supplier_id"], s["score"], color=[TIER[t] for t in s["tier"]], width=0.6)
    for b, (_, r) in zip(bars, s.iterrows()):
        ax.text(b.get_x() + b.get_width() / 2, r["score"] + 1.2, f"{r['score']:.0f}\n({r['tier']})", ha="center",
                fontsize=8.5, color=INK2)
    ax.set_ylim(0, 105)
    ax.set_ylabel("scorecard (0-100)", color=INK2)
    style(ax)
    save(fig, path)


def chart_bundles(bun, path):
    b = bun[bun.lift >= 1.5].head(8).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.barh(b["sku_a"] + " + " + b["sku_b"], b["lift"], color=AQUA, height=0.6)
    for y, v in enumerate(b["lift"]):
        ax.text(v + 0.3, y, f"lift {v:.1f}", va="center", color=INK2, fontsize=9)
    ax.axvline(1, color=INK2, ls=(0, (4, 3)), lw=1)
    ax.set_xlim(0, b["lift"].max() * 1.2)
    style(ax, "x")
    save(fig, path)


def chart_returns(ret, path):
    c = ret[ret.scope == "CAT"].sort_values("return_rate", ascending=False)
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.bar(c["name"], c["return_rate"] * 100, color=ORANGE, width=0.55)
    for x, v in enumerate(c["return_rate"] * 100):
        ax.text(x, v + 0.3, f"{v:.1f}%", ha="center", color=INK2, fontsize=9)
    ax.set_ylabel("share of units returned", color=INK2)
    style(ax)
    save(fig, path)


# ---------------------------------------------------------------- report
def build(data, out, reports):
    figs = os.path.join(reports, "figures")
    os.makedirs(figs, exist_ok=True)
    meta = json.load(open(os.path.join(data, "meta.json")))
    orders = pd.read_csv(os.path.join(data, "orders.csv"))
    inv = pd.read_csv(os.path.join(data, "inventory.csv"))
    gap = read_gap(os.path.join(out, "gap_report.csv"))
    daily = read_daily(os.path.join(out, "daily_demand.tsv"))
    sup = read_suppliers(os.path.join(out, "supplier_stats.tsv"))
    upl = read_uplift(os.path.join(out, "uplift.tsv"))
    bun = read_bundles(os.path.join(out, "bundles.tsv"))
    ret = read_returns(os.path.join(out, "return_rates.tsv"))
    bt = pd.read_csv(os.path.join(out, "backtest.csv"))
    tr = pd.read_csv(os.path.join(out, "transfers.csv"))
    alerts = pd.read_csv(os.path.join(out, "alerts.csv"))
    bal = pd.read_csv(os.path.join(out, "bundle_alerts.csv"))
    rsum = json.load(open(os.path.join(out, "rebalance_summary.json")))

    chart_weekly(orders, meta["sale_start"], os.path.join(figs, "weekly_demand.png"))
    chart_risk(gap, os.path.join(figs, "risk_by_warehouse.png"))
    chart_backtest(bt, os.path.join(figs, "backtest.png"))
    chart_uplift(upl, os.path.join(figs, "uplift.png"))
    chart_suppliers(sup, os.path.join(figs, "suppliers.png"))
    chart_bundles(bun, os.path.join(figs, "bundles.png"))
    chart_returns(ret, os.path.join(figs, "returns.png"))

    counts = gap["risk"].value_counts()
    method = gap["method"].iloc[0]
    overall = bt[bt.bucket == "all"].sort_values("wape_week")
    quoted = inv.groupby("supplier_id")["nominal_lead_days"].mean().rename("quoted_lead")
    sc = sup.set_index("supplier_id").join(quoted).reset_index()
    sc["lead_gap"] = sc["lead_mean"] - sc["quoted_lead"]
    last28 = daily[daily["date"] > (pd.to_datetime(meta["as_of"]) - pd.Timedelta(days=28)).strftime("%Y-%m-%d")]
    gross, net = int(last28["ordered"].sum()), int(last28["net"].sum())
    crit = gap[gap.risk == "CRITICAL"].sort_values(["days_late", "cover_days"], ascending=[False, True]).head(8)
    skus = upl[upl.scope == "SKU"].sort_values("uplift", ascending=False)

    lines = [f"# Results report (synthetic data, as of {meta['as_of']})", "",
             "Generated by `scripts/run_local.sh`. All data is synthetic, so these numbers show that the pipeline "
             "works, not how any real store behaves.", "",
             "| | |", "|---|---|",
             f"| Order lines / baskets | {len(orders):,} / {orders['order_id'].nunique():,} |",
             f"| SKU-warehouse pairs | {len(gap)} |",
             f"| Risk | {counts.get('CRITICAL', 0)} CRITICAL, {counts.get('WATCH', 0)} WATCH, "
             f"{counts.get('OK', 0)} OK, {counts.get('OVERSTOCK', 0)} OVERSTOCK |",
             f"| Forecast method in use | `{method}` |",
             f"| Transfers proposed | {rsum['transfers']} ({rsum['units_moved']} units, Rs {rsum['freight_cost']:,.0f} freight) |",
             f"| Festive-sale uplift | {upl[upl.scope == 'CAT']['uplift'].mean():.2f}x average across categories |", "",
             "## Idea 1. Demand forecasting", "",
             "Six methods are scored with a rolling-origin backtest (28 origins x 120 series, 7-day horizon). "
             "Lower WAPE is better.", "",
             "![backtest](figures/backtest.png)", "",
             md_table(overall[["method", "wape_week", "wape_daily", "bias"]].reset_index(drop=True), 3), "",
             f"`{overall.iloc[0]['method']}` has the lowest 7-day WAPE overall, so it is the default. Every method "
             "under-forecasts around the sale start because no history-based method can see a promotion coming; "
             "feed the planned promotion calendar in as a feature to fix that.", "",
             "## Idea 2. Stock-out early warning", "",
             "![risk](figures/risk_by_warehouse.png)", "",
             "Most urgent pairs (stock-out expected before a new order could arrive):", "",
             md_table(crit[["sku", "warehouse", "supplier_id", "tier", "on_hand", "cover_days", "lead_mean",
                            "days_late", "order_qty"]].reset_index(drop=True), 1), "",
             f"Full list with actions: `alerts.csv` ({len(alerts)} rows).", "",
             "## Idea 3. Smart reorder points", "",
             "An (s, S) policy: safety stock `z * sqrt(L*sd_d^2 + d^2*sd_L^2)` at a 95% service level, using the "
             "supplier's OBSERVED lead-time mean and spread, not the quoted lead time. `gap_report.csv` holds "
             "`safety_stock`, `reorder_point`, `order_up_to`, `order_qty` and the latest safe `order_by` date; "
             "`purchase_orders.csv` is the resulting order list after transfers.", "",
             "## Idea 4. Warehouse rebalancing", "",
             f"An integer linear program per SKU moves surplus stock to short warehouses when that beats the "
             f"supplier lead time: **{rsum['transfers']} transfers, {rsum['units_moved']} units, "
             f"Rs {rsum['freight_cost']:,.0f} freight** across {rsum['skus_helped']} SKUs. Lane costs are assumptions.", "",
             md_table(tr.head(8), 0), "",
             "## Idea 5. Festive-sale uplift", "",
             "![uplift](figures/uplift.png)", "",
             "Uplift is weekday-adjusted against the 28 days before the sale. It includes the organic upward trend "
             "(0.4% per day in the generator), so it reads slightly above the planted 1.9x.", "",
             md_table(upl[upl.scope == "CAT"][["name", "base_avg_day", "sale_avg_day", "plain_ratio", "uplift"]]
                      .rename(columns={"name": "category"}).reset_index(drop=True), 2), "",
             "Highest-uplift SKUs: " + ", ".join(f"{r.name} ({r.uplift:.2f}x)" for r in skus.head(5).itertuples()) + ". Low-volume SKUs are noisy, "
             "so read SKU-level uplift together with its sale-day count.", "",
             "![weekly](figures/weekly_demand.png)", "",
             "## Idea 6. Supplier scorecard", "",
             "![suppliers](figures/suppliers.png)", "",
             md_table(sc[["supplier_id", "n_pos", "on_time_rate", "quoted_lead", "lead_mean", "lead_gap", "lead_std",
                          "fill_rate", "score", "tier"]], 2), "",
             "`lead_gap` is observed minus quoted lead time. Planning with the quote would understate the risk for "
             "every supplier with a positive gap.", "",
             "## Idea 7. Bundle pre-positioning", "",
             "![bundles](figures/bundles.png)", "",
             md_table(bun[bun.lift >= 1.5].head(8).reset_index(drop=True), 3), "",
             f"{len(bal)} bundle alerts in `bundle_alerts.csv` (one item of a strong bundle is short). "
             f"Bundles with lift >= 3 should be stocked in the same warehouses.", "",
             "## Idea 8. Returns-adjusted demand", "",
             "![returns](figures/returns.png)", "",
             md_table(ret[ret.scope == "CAT"][["name", "ordered", "returned", "return_rate"]]
                      .rename(columns={"name": "category"}).reset_index(drop=True), 3), "",
             f"Over the last 28 days gross demand was {gross:,} units and net demand {net:,} "
             f"({(gross - net) / gross:.1%} lower). The forecast uses NET demand, with returns counted on the day the "
             "goods come back.", "",
             "## Caveats", "",
             "- Synthetic data: results validate the pipeline, not a business.",
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
