# E-commerce demand-supply system on Apache Hadoop

Forecast what each SKU will sell in each warehouse, warn before a stock-out, decide when and how much to reorder,
and move stock between warehouses. The heavy lifting is written as **Hadoop Streaming MapReduce jobs** (Python 3,
standard library only), so it runs unchanged on a cluster; a local runner reproduces the exact data flow
`cat | mapper | sort | reducer` so you can run everything on a laptop.

> All data is **synthetic** (`src/datagen`). The results show that the pipeline works, not how a real store behaves.
> A walkthrough of the ideas and design is in [`docs/Hadoop_Demand_Supply_Project_Pack.pdf`](docs/Hadoop_Demand_Supply_Project_Pack.pdf);
> generated results with charts are in [`reports/REPORT.md`](reports/REPORT.md).

## Quick start

```bash
pip install -r requirements.txt
make run          # generates data, runs all jobs, writes out/ and reports/REPORT.md
make test
```

## The 8 ideas and where they live

| # | Idea | MapReduce job(s) / code | Output |
|---|------|--------------------------|--------|
| 1 | Demand forecasting | `daily_demand_map.py` + `sum_reduce.py`, `forecast.py`, `gap_*`, `analysis/backtest.py` | `out/daily_demand.tsv`, `out/backtest.csv` |
| 2 | Stock-out early warning | `gap_map.py`, `gap_reduce.py`, `policy.py`, `analysis/alerts.py` | `out/gap_report.csv`, `out/alerts.csv` |
| 3 | Smart reorder points | `policy.py` ((s,S) policy with observed lead-time variability) | `out/gap_report.csv`, `out/purchase_orders.csv` |
| 4 | Warehouse rebalancing | `analysis/rebalance.py` (per-SKU transportation integer LP) | `out/transfers.csv` |
| 5 | Festive-sale uplift | `uplift_map.py`, `uplift_reduce.py` | `out/uplift.tsv` |
| 6 | Supplier scorecard | `supplier_map.py`, `supplier_reduce.py` (also read by the gap job through the distributed cache) | `out/supplier_stats.tsv` |
| 7 | Bundle pre-positioning | `cooccur_map.py` -> `cooccur_pairs_reduce.py` -> `sum_reduce.py` -> `cooccur_metrics_*` (3 chained stages) | `out/bundles.tsv`, `out/bundle_alerts.csv` |
| 8 | Returns-adjusted demand | `daily_demand_map.py` (net = ordered - returned), `return_rate_*` | `out/return_rates.tsv` |

## Layout

```
src/datagen/      synthetic data generator (orders, returns, inventory, deliveries; plants known patterns)
src/jobs/         Hadoop Streaming mappers/reducers + shared logic (forecast, policy, config, schema)
src/analysis/     backtest, rebalancing LP, alerts, report builder (pandas / scipy / matplotlib)
scripts/          run_local.sh (tested) and run_hadoop.sh (cluster version, NOT tested here)
hive/             equivalent HiveQL, reference only (NOT executed here)
tests/            pytest: unit tests for each job, forecast, policy, LP, plus an end-to-end test
docs/             project pack PDF, architecture diagrams, design notes
reports/          generated REPORT.md and charts (committed so you can read the results without running anything)
```

## Configuration

Environment variables, read in `src/jobs/config.py` (on a cluster pass them with `-cmdenv`):
`AS_OF`, `SALE_START`, `FORECAST_METHOD` (default `naive7`, chosen by backtest), `SERVICE_LEVEL` (0.95),
`REVIEW_DAYS`, `STD_DAYS`, `OVERSTOCK_DAYS`, `MIN_PAIR_COUNT`, `SUPPLIER_STATS_FILE`.

## What is and is not verified

- Verified: the local pipeline end to end (`make run`, `make test`).
- Not verified: `scripts/run_hadoop.sh` and `hive/*.hql` have never been run on a real cluster or Hive.
  They follow the same job order and options as the local runner; expect to adjust paths and the Python setup on your nodes.
- Caveats on the numbers (synthetic data, trend inside the uplift, returns counted on the return date, assumed freight costs)
  are listed at the end of `reports/REPORT.md`.
