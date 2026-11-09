# HiveQL check (Spark SQL, not Apache Hive)

The scripts in `hive/` were executed by **Spark SQL with Hive support**, because Apache Hive itself could not be installed in the build environment. The tables they create are compared with the MapReduce outputs. Spark does not apply the `skip.header.line.count` table property that Hive honours, so the CSV header row is excluded in the comparison.

| script | statements run |
|---|---:|
| 00_ddl.hql | 6 |
| 10_net_demand.hql | 3 |
| 20_supplier_scorecard.hql | 2 |
| 30_festive_uplift.hql | 2 |
| 40_bundles.hql | 2 |

| comparison | MapReduce rows | Hive-SQL rows | rows that differ |
|---|---:|---:|---:|
| net daily demand (rows, ordered/returned/net) | 44,597 | 44,597 | 0 |
| supplier scorecard (n, score, tier) | 2,872 | 2,872 | 0 |
| festive uplift per department | 7 | 7 | 0 |
| bundles (pair orders, lift) | 8 | 8 | 0 |
| return rates per department (ordered, returned) | 7 | 7 | 0 |
