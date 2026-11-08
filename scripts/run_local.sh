#!/usr/bin/env bash
# Runs every MapReduce job on this machine with the exact Hadoop Streaming data flow:
#
#     cat input | mapper | sort | reducer          (sort = the shuffle)
#
# For jobs with two inputs the mapper runs once per file with the same
# `mapreduce_map_input_file` environment variable Hadoop sets on a cluster.
#
# Usage:  DATA_DIR=data/olist scripts/run_local.sh     (DATA_DIR / OUT_DIR / REPORTS_DIR can be overridden)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${DATA_DIR:-$ROOT/data/olist}"
OUT="${OUT_DIR:-$ROOT/out}"
JOBS="$ROOT/src/jobs"
PY="${PYTHON:-python3}"

export LC_ALL=C            # byte-wise sort, like Hadoop's Text comparator
export PYTHONPATH="$JOBS"
mkdir -p "$OUT"

if [ ! -f "$DATA/orders.csv" ]; then
  echo "no data in $DATA - run 'make real' (real Olist data) or 'make demo' (synthetic) first" >&2; exit 1
fi
AS_OF="$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['as_of'])" "$DATA/meta.json")"
SALE_START="$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['sale_start'])" "$DATA/meta.json")"
SALE_END="$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1])).get('sale_end',''))" "$DATA/meta.json")"
export AS_OF SALE_START SALE_END

# run_map <mapper.py> <input file>...  : the mapper once per input file
run_map() {
  local mapper="$1"; shift
  local f
  for f in "$@"; do
    mapreduce_map_input_file="$f" "$PY" "$JOBS/$mapper" < "$f"
  done
}
reduce_with() { "$PY" "$JOBS/$1"; }

echo "[1/8] net daily demand (ideas 1, 8): orders + returns -> sku|warehouse|date"
run_map daily_demand_map.py "$DATA/orders.csv" "$DATA/returns.csv" \
  | sort | reduce_with sum_reduce.py > "$OUT/daily_demand.tsv"

echo "[2/8] supplier scorecard (idea 6)"
run_map supplier_map.py "$DATA/deliveries.csv" \
  | sort | reduce_with supplier_reduce.py > "$OUT/supplier_stats.tsv"

echo "[3/8] backtest picks the forecast method (idea 1), then the gap engine (ideas 1, 2, 3)"
# real data: weekly origins over the whole history + every day around the sale (synthetic: the last 28 days)
BT_FLAGS=(); [ -n "$SALE_END" ] && BT_FLAGS=(--sale-end "$SALE_END" --spread)
"$PY" "$ROOT/src/analysis/backtest.py" --daily "$OUT/daily_demand.tsv" --out "$OUT" --sale-start "$SALE_START" "${BT_FLAGS[@]}"
# the winner of the backtest drives the gap engine (set FORECAST_METHOD yourself to override)
export FORECAST_METHOD="${FORECAST_METHOD:-$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['best_method_overall'])" "$OUT/backtest_summary.json")}"
echo "forecast method in use: $FORECAST_METHOD"
export SUPPLIER_STATS_FILE="$OUT/supplier_stats.tsv"   # on a cluster: -files supplier_stats.tsv
run_map gap_map.py "$OUT/daily_demand.tsv" "$DATA/inventory.csv" \
  | sort | reduce_with gap_reduce.py > "$OUT/gap_raw.csv"
GAP_HEADER="$("$PY" -c "import schema; print(','.join(schema.GAP_FIELDS))")"
{ echo "$GAP_HEADER"; sort "$OUT/gap_raw.csv"; } > "$OUT/gap_report.csv"
rm -f "$OUT/gap_raw.csv"

echo "[4/8] festive-sale uplift (idea 5)"
run_map uplift_map.py "$DATA/orders.csv" | sort | reduce_with uplift_reduce.py > "$OUT/uplift.tsv"

echo "[5/8] bundle mining, stages 1-3 (idea 7): baskets -> pairs -> counts -> lift"
run_map cooccur_map.py "$DATA/orders.csv" | sort | reduce_with cooccur_pairs_reduce.py \
  | sort | reduce_with sum_reduce.py > "$OUT/pair_counts.tsv"
run_map cooccur_metrics_map.py "$OUT/pair_counts.tsv" | sort \
  | reduce_with cooccur_metrics_reduce.py > "$OUT/bundles.tsv"
if [ -f "$DATA/baskets_products.csv" ]; then      # same three stages on individual products (real data only)
  run_map cooccur_map.py "$DATA/baskets_products.csv" | sort | reduce_with cooccur_pairs_reduce.py \
    | sort | reduce_with sum_reduce.py > "$OUT/pair_counts_products.tsv"
  MIN_PAIR_COUNT="${MIN_PAIR_COUNT_PRODUCTS:-8}" run_map cooccur_metrics_map.py "$OUT/pair_counts_products.tsv" | sort \
    | MIN_PAIR_COUNT="${MIN_PAIR_COUNT_PRODUCTS:-8}" reduce_with cooccur_metrics_reduce.py > "$OUT/bundles_products.tsv"
fi

echo "[6/8] return rates (idea 8)"
run_map return_rate_map.py "$DATA/orders.csv" "$DATA/returns.csv" \
  | sort | reduce_with return_rate_reduce.py > "$OUT/return_rates.tsv"

echo "[7/8] analysis: rebalancing LP (4), alerts"
"$PY" "$ROOT/src/analysis/rebalance.py" --gap "$OUT/gap_report.csv" --out "$OUT" --meta "$DATA/meta.json"
"$PY" "$ROOT/src/analysis/alerts.py" --out "$OUT"

echo "[8/8] report"
"$PY" "$ROOT/src/analysis/report.py" --data "$DATA" --out "$OUT" --reports "${REPORTS_DIR:-$ROOT/reports}"

echo "done. outputs in $OUT"
