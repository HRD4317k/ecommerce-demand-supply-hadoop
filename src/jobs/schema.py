"""Column names of every job output, kept in one place.

MapReduce outputs are ``key<TAB>v1,v2,...`` lines without a header; the analysis layer
uses these lists to label them.  ``gap_report.csv`` is the exception: the gap reducer
prints plain CSV rows and ``run_local.sh`` / ``run_hadoop.sh`` prepend this header.
"""

# daily_demand.tsv   key: sku|warehouse|date
DAILY_KEY = ["sku", "warehouse", "date"]
DAILY_FIELDS = ["ordered", "returned", "net"]

# supplier_stats.tsv   key: supplier_id
SUPPLIER_KEY = ["supplier_id"]
SUPPLIER_FIELDS = ["n_pos", "on_time_rate", "avg_delay_days", "lead_mean", "lead_std",
                   "fill_rate", "score", "tier"]

# gap_report.csv (plain CSV)
GAP_FIELDS = ["sku", "warehouse", "supplier_id", "tier", "on_hand", "on_order", "lead_mean",
              "lead_std", "fill_rate", "forecast_day", "sigma_d", "safety_stock",
              "reorder_point", "order_up_to", "cover_days", "risk", "order_qty",
              "order_by", "days_late", "method"]

# uplift.tsv   key: SCOPE|name   (SCOPE is CAT or SKU)
UPLIFT_KEY = ["scope", "name"]
UPLIFT_FIELDS = ["base_avg_day", "sale_avg_day", "plain_ratio", "uplift", "sale_days"]

# bundles.tsv   key: sku_a|sku_b
BUNDLE_KEY = ["sku_a", "sku_b"]
BUNDLE_FIELDS = ["pair_orders", "support", "conf_a_to_b", "conf_b_to_a", "lift"]

# return_rates.tsv   key: SCOPE|name
RETURN_KEY = ["scope", "name"]
RETURN_FIELDS = ["ordered", "returned", "return_rate"]

RISK_ORDER = ["CRITICAL", "WATCH", "OK", "OVERSTOCK"]
