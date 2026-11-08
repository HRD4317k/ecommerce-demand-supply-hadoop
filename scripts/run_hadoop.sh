#!/usr/bin/env bash
# Runs the same pipeline as scripts/run_local.sh on a real Hadoop 3.x cluster (YARN + HDFS)
# with Hadoop Streaming.
#
# NOTE: written against the Hadoop Streaming interface and mirrors run_local.sh job by job, but it
# has NOT been executed on a cluster in this repository (only the local runner has).  Expect to adjust
# paths, python3 availability on the worker nodes and queue settings for your cluster.
#
# Requirements: hadoop + hdfs on PATH, python3 on every worker node, data generated locally
# (python3 src/datagen/generate.py --out data) or your own files with the same columns.
#
# Usage: scripts/run_hadoop.sh [HDFS_BASE=/ecom] [REDUCERS=4]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${DATA_DIR:-$ROOT/data}"
OUT="${OUT_DIR:-$ROOT/out}"
JOBS="$ROOT/src/jobs"
BASE="${HDFS_BASE:-/ecom}"
REDUCERS="${REDUCERS:-4}"
STREAMING_JAR="${STREAMING_JAR:-$(ls "$HADOOP_HOME"/share/hadoop/tools/lib/hadoop-streaming-*.jar | head -n1)}"
PY="${PYTHON:-python3}"
mkdir -p "$OUT"

AS_OF="$($PY -c "import json,sys; print(json.load(open(sys.argv[1]))['as_of'])" "$DATA/meta.json")"
SALE_START="$($PY -c "import json,sys; print(json.load(open(sys.argv[1]))['sale_start'])" "$DATA/meta.json")"
ENV_FLAGS=(-cmdenv "AS_OF=$AS_OF" -cmdenv "SALE_START=$SALE_START")

# Shared modules every job script may import (shipped to each task's working directory).
SHARED="$JOBS/config.py,$JOBS/schema.py,$JOBS/forecast.py,$JOBS/policy.py"

# stream <extra generic opts...> -- <streaming opts...>   (generic options such as -D, -files must come first)
stream() { hadoop jar "$STREAMING_JAR" "$@"; }
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

echo "[3] gap engine (ideas 1, 2, 3): supplier_stats.tsv goes through the distributed cache"
clean_out "$BASE/curated/gap_report"
stream -D mapreduce.job.reduces="$REDUCERS" -files "$(job_files gap_map.py gap_reduce.py),$OUT/supplier_stats.tsv" \
  -input "$BASE/curated/daily_demand" -input "$BASE/raw/inventory" -output "$BASE/curated/gap_report" \
  -mapper "$PY gap_map.py" -reducer "$PY gap_reduce.py" "${ENV_FLAGS[@]}"

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

echo "[6] return rates (idea 8)"
clean_out "$BASE/curated/return_rates"
stream -D mapreduce.job.reduces="$REDUCERS" -files "$(job_files return_rate_map.py return_rate_reduce.py sum_reduce.py)" \
  -input "$BASE/raw/orders" -input "$BASE/raw/returns" -output "$BASE/curated/return_rates" \
  -mapper "$PY return_rate_map.py" -combiner "$PY sum_reduce.py" -reducer "$PY return_rate_reduce.py"

echo "[7] bring the (small) results back and run the analysis layer locally"
hdfs dfs -getmerge "$BASE/curated/daily_demand" "$OUT/daily_demand.tsv"
hdfs dfs -getmerge "$BASE/curated/uplift" "$OUT/uplift.tsv"
hdfs dfs -getmerge "$BASE/curated/bundles" "$OUT/bundles.tsv"
hdfs dfs -getmerge "$BASE/curated/return_rates" "$OUT/return_rates.tsv"
hdfs dfs -getmerge "$BASE/curated/gap_report" "$OUT/gap_raw.csv"
{ $PY -c "import sys; sys.path.insert(0, '$JOBS'); import schema; print(','.join(schema.GAP_FIELDS))"
  LC_ALL=C sort "$OUT/gap_raw.csv"; } > "$OUT/gap_report.csv"
rm -f "$OUT/gap_raw.csv"
export AS_OF
"$PY" "$ROOT/src/analysis/backtest.py" --daily "$OUT/daily_demand.tsv" --out "$OUT" --sale-start "$SALE_START"
"$PY" "$ROOT/src/analysis/rebalance.py" --gap "$OUT/gap_report.csv" --out "$OUT"
"$PY" "$ROOT/src/analysis/alerts.py" --out "$OUT"
"$PY" "$ROOT/src/analysis/report.py" --data "$DATA" --out "$OUT" --reports "${REPORTS_DIR:-$ROOT/reports}"
echo "done. HDFS outputs under $BASE/curated, local copies in $OUT"
