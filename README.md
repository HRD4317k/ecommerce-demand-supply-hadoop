# E-commerce demand-supply system on Apache Hadoop

Forecast what each product category will sell in each regional hub, warn before a stock-out, decide when and how much
to reorder, and move stock between hubs. The heavy lifting is written as **Hadoop Streaming MapReduce jobs** (Python 3,
standard library only), so it runs unchanged on a cluster; a local runner reproduces the exact data flow
`cat | mapper | sort | reducer` so everything runs on a laptop.

**It runs on real data**: the Olist Brazilian marketplace dataset (about 100,000 real orders, 2016-2018, 3,000 sellers),
including the real Black Friday 2017 spike. Results with charts are in [`reports/REPORT.md`](reports/REPORT.md).
A synthetic generator is kept for demos and tests. What is real and what is assumed is spelled out in
[`docs/DATA.md`](docs/DATA.md); sources are in [`REFERENCES.md`](REFERENCES.md).

> Honest limits: no public retail dataset contains warehouse stock levels or inter-warehouse freight, so those two inputs
> are assumed and labelled. Demand, regions, seller lead times, cancellations and the Black Friday uplift are real.

## Quick start

```bash
pip install -r requirements.txt
make real      # downloads Olist (~60 MB), prepares it, runs all 8 ideas, writes out/olist and reports/
make test      # 38 tests; the real-data end-to-end test skips itself if the raw data is absent
make demo      # optional: the same pipeline on synthetic data with planted patterns (no download)
```

## The 8 ideas, what they found on the real data, and where the code is

| # | Idea | Code | Real-data finding |
|---|------|------|-------------------|
| 1 | Demand forecasting | `daily_demand_map.py` + `sum_reduce.py`, `forecast.py`, `analysis/backtest.py` | Backtest of 6 methods over 110 dates x 356 series: the 28-day average wins (7-day WAPE 0.48); weekday-seasonal methods lose on small noisy series; every method under-forecasts by roughly 50-65% when the sale starts inside the window |
| 2 | Stock-out early warning | `gap_map.py`, `gap_reduce.py`, `policy.py`, `analysis/alerts.py` | Risk labels per category-hub (stock levels are assumed, so which pairs flag is illustrative) |
| 3 | Smart reorder points | `policy.py`, an (s,S) policy using each supplier's observed lead-time mean and spread | Observed lead time 12.8 days with a 8.9-day spread: lead-time variability, not demand noise, drives safety stock |
| 4 | Warehouse rebalancing | `analysis/rebalance.py`, per-SKU transportation integer LP | 27 transfers instead of purchase orders when a hub transfer beats the supplier lead time (lane costs assumed) |
| 5 | Sale uplift | `uplift_map.py`, `uplift_reduce.py` | Black Friday 2017: first day 7.0x a normal day; weekday-adjusted week-long uplift 2.2x to 3.5x by department |
| 6 | Supplier scorecard | `supplier_map.py`, `supplier_reduce.py` (also read by the gap job through the distributed cache) | 2,872 sellers scored; the delivery estimates sellers quote are padded by about 12 days on average |
| 7 | Bundle pre-positioning | `cooccur_map.py` -> `cooccur_pairs_reduce.py` -> `sum_reduce.py` -> `cooccur_metrics_*` (3 chained jobs) | Only 3.3% of orders hold 2+ products, so there is little to bundle: no category pair has lift above 1.2; a handful of product pairs show real lift (e.g. two computer accessories, lift 189) |
| 8 | Returns-adjusted demand | `daily_demand_map.py` (net = ordered - returned), `return_rate_*` | The dataset has no returns table; cancellations are the nearest real signal and cut demand by only 0.6% |

## Layout

```
src/datagen/      prepare_olist.py (real data -> pipeline files) and generate.py (synthetic demo data)
src/jobs/         Hadoop Streaming mappers/reducers + shared logic (forecast, policy, config, schema)
src/analysis/     backtest, rebalancing LP, alerts, report builder (pandas / scipy / matplotlib)
scripts/          fetch_olist.sh, run_local.sh (tested), run_hadoop.sh (cluster version, NOT tested here)
hive/             equivalent HiveQL, reference only (NOT executed here)
tests/            38 pytest tests: each job, forecast, policy, LP, the Olist adapter, end-to-end on synthetic and real data
docs/             DATA.md, ARCHITECTURE.md, the project-pack PDF, diagrams
reports/          REPORT.md and charts generated from the real data (committed so you can read the results directly)
REFERENCES.md     datasets, papers, books and software this work relies on
```

## How the planning model maps onto the marketplace

| Planning concept | In the Olist data |
|---|---|
| SKU | product category (the 20 to 30 biggest are planned) |
| Warehouse | one of 5 regional hubs (SP, RJ, MG, SUL, NE) chosen from the customer's state |
| Supplier | the seller that fulfils the order |
| Supplier lead time | the seller's real order-to-delivery time; the quote is the estimate shown to the customer |
| Return | cancelled or unavailable order (booked on the order date) |
| Festive sale | Black Friday 2017 (2017-11-24), a real event |

## Configuration

Environment variables, read in `src/jobs/config.py` (on a cluster pass them with `-cmdenv`):
`AS_OF`, `SALE_START`, `SALE_END`, `FORECAST_METHOD` (by default the winner of the backtest), `SERVICE_LEVEL` (0.95),
`REVIEW_DAYS`, `STD_DAYS`, `OVERSTOCK_DAYS`, `MIN_PAIR_COUNT`, `SUPPLIER_STATS_FILE`.

## What is and is not verified

- Verified: the local pipeline end to end on real and synthetic data (`make real`, `make demo`, `make test`).
- Not verified: `scripts/run_hadoop.sh` and `hive/*.hql` have never been run on a real cluster or Hive. They follow the
  same job order and options as the local runner; expect to adjust paths and the Python setup on your nodes.
- The Olist data is licensed CC BY-NC-SA 4.0 (non-commercial, share-alike); it is not redistributed in this repository.
