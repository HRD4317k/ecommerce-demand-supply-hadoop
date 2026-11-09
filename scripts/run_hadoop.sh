#!/usr/bin/env bash
# Runs the same pipeline as scripts/run_local.sh on a real Hadoop 3.x cluster (YARN + HDFS)
# with Hadoop Streaming.
#
# STATUS: executed end to end in Hadoop *standalone* mode (scripts/setup_hadoop_standalone.sh: real MapReduce
# engine and Streaming, one JVM, local file system) with outputs identical to run_local.sh.  NOT run on a
# multi-node HDFS/YARN cluster; expect to adjust paths, python3 on the worker nodes and queue settings there.
# For the standalone run use a local directory as HDFS_BASE, e.g.  HDFS_BASE=$PWD/out/hdfs
#
# Requirements: hadoop + hdfs on PATH, python3 on every worker node, data generated locally
# (make real) or your own files with the same columns.
#
# Usage: scripts/run_hadoop.sh [HDFS_BASE=/ecom] [REDUCERS=4]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${DATA_DIR:-$ROOT/data/olist}"
OUT="${OUT_DIR:-$ROOT/out}"
JOBS="$ROOT/src/jobs"
BASE="${HDFS_BASE:-/ecom}"
REDUCERS="${REDUCERS:-4}"
STREAMING_JAR="${STREAMING_JAR:-$(ls "$HADOOP_HOME"/share/hadoop/tools/lib/hadoop-streaming-*.jar | head -n1)}"
PY="${PYTHON:-python3}"
mkdir -p "$OUT"

AS_OF="$($PY -c "import json,sys; print(json.load(open(sys.argv[1]))['as_of'])" "$DATA/meta.json")"
SALE_START="$($PY -c "import json,sys; print(json.load(open(sys.argv[1]))['sale_start'])" "$DATA/meta.json")"
SALE_END="$($PY -c "import json,sys; print(json.load(open(sys.argv[1])).get('sale_end',''))" "$DATA/meta.json")"
ENV_FLAGS=(-cmdenv "AS_OF=$AS_OF" -cmdenv "SALE_START=$SALE_START" -cmdenv "SALE_END=$SALE_END")

# Shared modules every job script may import (shipped to each task's working directory).
SHARED="$JOBS/config.py,$JOBS/schema.py,$JOBS/forecast.py,$JOBS/policy.py"

# stream <extra generic opts...> -- <streaming opts...>   (generic options such as -D, -files must come first)
# PYTHONPATH=. matters: Hadoop symlinks every -files entry into the task directory (each one from its own
# localized folder), and Python resolves the symlink, so without it `import config` finds nothing.
# Every job is timed; wall-clock seconds per job go to $OUT/hadoop_job_times.tsv.
JOB_TIMES="$OUT/hadoop_job_times.tsv"; : > "$JOB_TIMES"
stream() {
  local out="" prev="" a t0 t1
  for a in "$@"; do [ "$prev" = "-output" ] && out="$a"; prev="$a"; done
  t0=$(date +%s.%N)
  hadoop jar "$STREAMING_JAR" "$@" -cmdenv PYTHONPATH=. 2> >(tee -a "$OUT/hadoop_counters.log" >&2)
  t1=$(date +%s.%N)
  printf '%s\t%.1f\n' "$(basename "$out")" "$(echo "$t1 - $t0" | bc -l)" >> "$JOB_TIMES"
}
: > "$OUT/hadoop_counters.log"
clean_out() { hdfs dfs -rm -r -f "$1" >/dev/null 2>&1 || true; }   # only this pipeline's own output dirs
job_files() { local list="$SHARED"; for f in "$@"; do list="$list,$JOBS/$f"; done; echo "$list"; }

echo "[0] upload raw data to HDFS under $BASE/raw"
hdfs dfs -mkdir -p "$BASE/raw/orders" "$BASE/raw/returns" "$BASE/raw/inventory" "$BASE/raw/deliveries" "$BASE/curated"
hdfs dfs -put -f "$DATA/orders.csv" "$BASE/raw/orders/"
hdfs dfs -put -f "$DATA/returns.csv" "$BASE/raw/returns/"
hdfs dfs -put -f "$DATA/inventory.csv" "$BASE/raw/inventory/"
hdfs dfs -put -f "$DATA/deliveries.csv" "$BASE/raw/deliveries/"

echo "[1] net daily demand (ideas 1, 8)"
clean_out "$BASE/curated/daily_demand"
stream -D mapreduce.job.reduces="$REDUCERS" -files "$(job_files daily_demand_map.py sum_reduce.py)" \
  -input "$BASE/raw/orders" -input "$BASE/raw/returns" -output "$BASE/curated/daily_demand" \
  -mapper "$PY daily_demand_map.py" -combiner "$PY sum_reduce.py" -reducer "$PY sum_reduce.py"

echo "[2] supplier scorecard (idea 6)"
clean_out "$BASE/curated/supplier_stats"
stream -D mapreduce.job.reduces=1 -files "$(job_files supplier_map.py supplier_reduce.py)" \
  -input "$BASE/raw/deliveries" -output "$BASE/curated/supplier_stats" \
  -mapper "$PY supplier_map.py" -reducer "$PY supplier_reduce.py"
hdfs dfs -getmerge "$BASE/curated/supplier_stats" "$OUT/supplier_stats.tsv"

echo "[2b] backtest on the (small) daily demand picks the forecast method"
hdfs dfs -getmerge "$BASE/curated/daily_demand" "$OUT/daily_demand.tsv"
BT_FLAGS=(); [ -n "$SALE_END" ] && BT_FLAGS=(--sale-end "$SALE_END" --spread)
"$PY" "$ROOT/src/analysis/backtest.py" --daily "$OUT/daily_demand.tsv" --out "$OUT" --sale-start "$SALE_START" "${BT_FLAGS[@]}"
FORECAST_METHOD="${FORECAST_METHOD:-$($PY -c "import json,sys; print(json.load(open(sys.argv[1]))['best_method_overall'])" "$OUT/backtest_summary.json")}"
echo "forecast method in use: $FORECAST_METHOD"

echo "[3] gap engine (ideas 1, 2, 3): supplier_stats.tsv goes through the distributed cache"
clean_out "$BASE/curated/gap_report"
stream -D mapreduce.job.reduces="$REDUCERS" -files "$(job_files gap_map.py gap_reduce.py),$OUT/supplier_stats.tsv" \
  -input "$BASE/curated/daily_demand" -input "$BASE/raw/inventory" -output "$BASE/curated/gap_report" \
  -mapper "$PY gap_map.py" -reducer "$PY gap_reduce.py" "${ENV_FLAGS[@]}" -cmdenv "FORECAST_METHOD=$FORECAST_METHOD"

echo "[4] festive-sale uplift (idea 5)"
clean_out "$BASE/curated/uplift"
stream -D mapreduce.job.reduces="$REDUCERS" -files "$(job_files uplift_map.py uplift_reduce.py)" \
  -input "$BASE/raw/orders" -output "$BASE/curated/uplift" \
  -mapper "$PY uplift_map.py" -reducer "$PY uplift_reduce.py" "${ENV_FLAGS[@]}"

echo "[5] bundle mining in three chained jobs (idea 7)"
clean_out "$BASE/curated/pairs_raw"; clean_out "$BASE/curated/pair_counts"; clean_out "$BASE/curated/bundles"
stream -D mapreduce.job.reduces="$REDUCERS" -files "$(job_files cooccur_map.py cooccur_pairs_reduce.py)" \
  -input "$BASE/raw/orders" -output "$BASE/curated/pairs_raw" \
  -mapper "$PY cooccur_map.py" -reducer "$PY cooccur_pairs_reduce.py"
stream -D mapreduce.job.reduces="$REDUCERS" -files "$(job_files sum_reduce.py)" \
  -input "$BASE/curated/pairs_raw" -output "$BASE/curated/pair_counts" \
  -mapper cat -combiner "$PY sum_reduce.py" -reducer "$PY sum_reduce.py"
stream -D mapreduce.job.reduces=1 -files "$(job_files cooccur_metrics_map.py cooccur_metrics_reduce.py)" \
  -input "$BASE/curated/pair_counts" -output "$BASE/curated/bundles" \
  -mapper "$PY cooccur_metrics_map.py" -reducer "$PY cooccur_metrics_reduce.py"

if [ -f "$DATA/baskets_products.csv" ]; then
  echo "[5b] the same three bundle jobs on individual products (real data only)"
  hdfs dfs -mkdir -p "$BASE/raw/baskets_products" && hdfs dfs -put -f "$DATA/baskets_products.csv" "$BASE/raw/baskets_products/"
  for d in pairs_raw_p pair_counts_p bundles_p; do clean_out "$BASE/curated/$d"; done
  stream -D mapreduce.job.reduces="$REDUCERS" -files "$(job_files cooccur_map.py cooccur_pairs_reduce.py)" \
    -input "$BASE/raw/baskets_products" -output "$BASE/curated/pairs_raw_p" \
    -mapper "$PY cooccur_map.py" -reducer "$PY cooccur_pairs_reduce.py"
  stream -D mapreduce.job.reduces="$REDUCERS" -files "$(job_files sum_reduce.py)" \
    -input "$BASE/curated/pairs_raw_p" -output "$BASE/curated/pair_counts_p" \
    -mapper cat -combiner "$PY sum_reduce.py" -reducer "$PY sum_reduce.py"
  stream -D mapreduce.job.reduces=1 -files "$(job_files cooccur_metrics_map.py cooccur_metrics_reduce.py)" \
    -input "$BASE/curated/pair_counts_p" -output "$BASE/curated/bundles_p" \
    -mapper "$PY cooccur_metrics_map.py" -reducer "$PY cooccur_metrics_reduce.py" -cmdenv "MIN_PAIR_COUNT=8"
  hdfs dfs -getmerge "$BASE/curated/bundles_p" "$OUT/bundles_products.tsv"
fi

echo "[6] return rates (idea 8)"
clean_out "$BASE/curated/return_rates"
stream -D mapreduce.job.reduces="$REDUCERS" -files "$(job_files return_rate_map.py return_rate_reduce.py sum_reduce.py)" \
  -input "$BASE/raw/orders" -input "$BASE/raw/returns" -output "$BASE/curated/return_rates" \
  -mapper "$PY return_rate_map.py" -combiner "$PY sum_reduce.py" -reducer "$PY return_rate_reduce.py"

echo "[7] bring the (small) results back and run the analysis layer locally"
hdfs dfs -getmerge "$BASE/curated/uplift" "$OUT/uplift.tsv"
hdfs dfs -getmerge "$BASE/curated/bundles" "$OUT/bundles.tsv"
hdfs dfs -getmerge "$BASE/curated/return_rates" "$OUT/return_rates.tsv"
hdfs dfs -getmerge "$BASE/curated/pair_counts" "$OUT/pair_counts.tsv"
if hdfs dfs -test -d "$BASE/curated/pair_counts_p"; then
  hdfs dfs -getmerge "$BASE/curated/pair_counts_p" "$OUT/pair_counts_products.tsv"
fi
hdfs dfs -getmerge "$BASE/curated/gap_report" "$OUT/gap_raw.csv"
{ $PY -c "import sys; sys.path.insert(0, '$JOBS'); import schema; print(','.join(schema.GAP_FIELDS))"
  # TextOutputFormat appends a tab to lines that contain none (the CSV rows), so strip it again
  sed 's/\t$//' "$OUT/gap_raw.csv" | LC_ALL=C sort; } > "$OUT/gap_report.csv"
rm -f "$OUT/gap_raw.csv"
export AS_OF SALE_START SALE_END
"$PY" "$ROOT/src/analysis/rebalance.py" --gap "$OUT/gap_report.csv" --out "$OUT" --meta "$DATA/meta.json"
"$PY" "$ROOT/src/analysis/alerts.py" --out "$OUT"
"$PY" "$ROOT/src/analysis/report.py" --data "$DATA" --out "$OUT" --reports "${REPORTS_DIR:-$ROOT/reports}"
echo "done. HDFS outputs under $BASE/curated, local copies in $OUT"
