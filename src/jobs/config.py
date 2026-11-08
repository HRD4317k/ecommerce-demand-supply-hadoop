"""Shared, environment-driven configuration for every Hadoop Streaming job.

Hadoop Streaming has no "config file" channel for mappers and reducers, so every
tunable is read from an environment variable with a safe default.  On a cluster pass
them with ``-cmdenv NAME=value``; locally ``scripts/run_local.sh`` exports them.
This file is shipped to the cluster with ``-files`` next to the job scripts.
"""
import os


def _get(name, default, cast=str):
    return cast(os.environ.get(name, default))


# Last day of data ("today" for the planner).  Empty = use the newest date a job sees.
AS_OF = _get("AS_OF", "")
# First day of the festive sale (idea 5).
SALE_START = _get("SALE_START", "2026-10-25")
# Days before the sale used as the uplift baseline (4 full weeks = 4 samples per weekday).
BASELINE_DAYS = _get("BASELINE_DAYS", 28, int)

# Forecast / inventory policy (ideas 1-3).
# Default chosen from the rolling backtest (analysis/backtest.py): the plain last-7-day
# average had the lowest 7-day WAPE overall.  Options: see forecast.METHODS.
FORECAST_METHOD = _get("FORECAST_METHOD", "naive7")
SERVICE_LEVEL = _get("SERVICE_LEVEL", 0.95, float)   # target cycle service level
REVIEW_DAYS = _get("REVIEW_DAYS", 7, int)            # days of demand ordered beyond the reorder point
STD_DAYS = _get("STD_DAYS", 14, int)                 # window for daily demand std-dev
OVERSTOCK_DAYS = _get("OVERSTOCK_DAYS", 45, int)     # cover above this = overstock

# Bundles (idea 7): ignore pairs seen in fewer orders than this.
MIN_PAIR_COUNT = _get("MIN_PAIR_COUNT", 15, int)

# Distributed-cache file with supplier scorecard rows (map-side join in gap_map.py).
SUPPLIER_STATS_FILE = _get("SUPPLIER_STATS_FILE", "supplier_stats.tsv")

# Used when a SKU's supplier has no history.
DEFAULT_LEAD_STD = 1.0
DEFAULT_FILL_RATE = 0.9
