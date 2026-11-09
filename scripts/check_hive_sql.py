"""Run the HiveQL scripts in hive/ and check them against the MapReduce outputs.

IMPORTANT: this does NOT use Apache Hive.  Hive's distribution is not reachable from the environment this
repository was built in, so the same .hql files are executed by Spark SQL with Hive support (Spark understands
the Hive DDL used here: external text tables, CTAS ... STORED AS ORC, ${hivevar:...}).  It proves the SQL is
valid and gives the same numbers as the MapReduce jobs; it does not prove Hive itself accepts every statement.

Usage: python3 scripts/check_hive_sql.py --raw out/hdfs/raw --mr out/olist_hadoop --meta data/olist/meta.json \
                                         [--out reports/HIVE_CHECK.md]
Needs: pip install pyspark py4j  (and Java).
"""
import argparse
import json
import os
import pathlib
import re
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent


def statements(path, subs):
    text = pathlib.Path(path).read_text()
    text = re.sub(r"--[^\n]*", "", text)                      # drop comments
    for k, v in subs.items():
        text = text.replace(k, v)
    return [s.strip() for s in text.split(";") if s.strip()]


def read_mr(path):
    rows = {}
    with open(path) as f:
        for line in f:
            if line.strip():
                k, v = line.rstrip("\n").split("\t", 1)
                rows[k] = v.split(",")
    return rows


def close(a, b, tol):
    return abs(float(a) - float(b)) <= tol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="directory holding orders/ returns/ inventory/ deliveries/")
    ap.add_argument("--mr", required=True, help="directory with the MapReduce outputs to compare with")
    ap.add_argument("--meta", required=True)
    ap.add_argument("--out", default=str(ROOT / "reports" / "HIVE_CHECK.md"))
    a = ap.parse_args()

    from pyspark.sql import SparkSession
    meta = json.load(open(a.meta))
    raw = pathlib.Path(a.raw).resolve()
    tmp = tempfile.mkdtemp(prefix="hivecheck_")
    spark = (SparkSession.builder.master("local[2]").appName("hive-sql-check")
             .config("spark.sql.warehouse.dir", f"{tmp}/warehouse")
             .config("spark.driver.extraJavaOptions", f"-Dderby.system.home={tmp}/derby")
             .config("spark.ui.enabled", "false").enableHiveSupport().getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")

    subs = {"'/ecom/raw": f"'file://{raw}"}
    hv = {"sale_start": meta["sale_start"], "sale_end": meta.get("sale_end") or meta["sale_start"], "min_pairs": "15"}
    for k, v in hv.items():
        subs["${hivevar:%s}" % k] = v

    last_select = None
    ran = []
    for f in ["00_ddl", "10_net_demand", "20_supplier_scorecard", "30_festive_uplift", "40_bundles"]:
        n = 0
        for st in statements(ROOT / "hive" / f"{f}.hql", subs):
            df = spark.sql(st)
            if st.lstrip().upper().startswith("SELECT"):
                last_select = df
            n += 1
        ran.append((f"{f}.hql", n))

    checks = []

    # 1 net daily demand
    mr = read_mr(f"{a.mr}/daily_demand.tsv")
    # Spark ignores the table property skip.header.line.count (Hive honours it), so each text table also yields
    # one junk "header row" group; those are dropped here.
    hive = {f"{r.sku}|{r.warehouse}|{r.demand_date}": [str(int(r.ordered)), str(int(r.returned)), str(int(r.net))]
            for r in spark.sql("select * from ecom.daily_demand where sku <> 'sku'").collect()}
    checks.append(("net daily demand (rows, ordered/returned/net)", len(mr), len(hive),
                   sum(1 for k, v in mr.items() if hive.get(k) != v)))

    # 2 supplier scorecard: score within 0.06 (MR prints one decimal), tier equal.  The MapReduce job leaves out
    # sellers with nothing delivered (no lead-time statistics); Hive gives them NULL statistics, so they are excluded.
    mr = read_mr(f"{a.mr}/supplier_stats.tsv")
    hive = {r.supplier_id: r for r in spark.sql("select * from ecom.supplier_stats where supplier_id <> 'supplier_id' and lead_mean is not null").collect()}
    bad = 0
    for k, v in mr.items():
        h = hive.get(k)
        if h is None or not close(v[6], h.score, 0.06) or v[7] != h.tier or int(v[0]) != h.n_pos:
            bad += 1
    checks.append(("supplier scorecard (n, score, tier)", len(mr), len(hive), bad))

    # 3 festive uplift: the Hive script groups by the `category` column = department = the CAT| rows of the MR output
    mr = {k[4:]: v for k, v in read_mr(f"{a.mr}/uplift.tsv").items() if k.startswith("CAT|")}
    hive = {r.category: r for r in spark.sql("select * from ecom.festive_uplift where category <> 'category'").collect()}
    bad = 0
    for k, v in mr.items():
        h = hive.get(k)
        if h is None or not (close(v[0], h.base_avg_day, 0.006) and close(v[1], h.sale_avg_day, 0.006)
                             and close(v[2], h.plain_ratio, 0.002) and close(v[3], h.uplift, 0.002)
                             and int(v[4]) == h.sale_days):
            bad += 1
    checks.append(("festive uplift per department", len(mr), len(hive), bad))

    # 4 bundles (category level, min 15 orders)
    mr = read_mr(f"{a.mr}/bundles.tsv")
    hive = {f"{r.sku_a}|{r.sku_b}": r for r in spark.sql("select * from ecom.bundles").collect()}
    bad = 0
    for k, v in mr.items():
        h = hive.get(k)
        if h is None or int(v[0]) != h.pair_orders or not close(v[4], h.lift, 0.006):
            bad += 1
    checks.append(("bundles (pair orders, lift)", len(mr), len(hive), bad))

    # 5 return rates per category (last SELECT in 10_net_demand.hql is the one we kept before the later files;
    #   recompute it explicitly so the check does not depend on statement order)
    mr = {k[4:]: v for k, v in read_mr(f"{a.mr}/return_rates.tsv").items() if k.startswith("CAT|")}
    rr = {r.category: r for r in spark.sql(
        "select o.category, o.units ordered, coalesce(r.units,0) returned from "
        "(select category, sum(qty) units from ecom.orders where qty is not null group by category) o left join "
        "(select category, sum(qty) units from ecom.returns where qty is not null group by category) r "
        "on o.category=r.category where o.category <> 'category'").collect()}
    bad = sum(1 for k, v in mr.items() if k not in rr or int(v[0]) != rr[k].ordered or int(v[1]) != rr[k].returned)
    checks.append(("return rates per department (ordered, returned)", len(mr), len(rr), bad))

    lines = ["# HiveQL check (Spark SQL, not Apache Hive)\n",
             "The scripts in `hive/` were executed by **Spark SQL with Hive support**, because Apache Hive itself could not "
             "be installed in the build environment. The tables they create are compared with the MapReduce outputs. "
             "Spark does not apply the `skip.header.line.count` table property that Hive honours, so the CSV header row "
             "is excluded in the comparison.\n",
             "| script | statements run |", "|---|---:|"]
    lines += [f"| {n} | {c} |" for n, c in ran]
    lines += ["", "| comparison | MapReduce rows | Hive-SQL rows | rows that differ |", "|---|---:|---:|---:|"]
    lines += [f"| {n} | {m:,} | {h:,} | {b} |" for n, m, h, b in checks]
    lines += [""]
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    pathlib.Path(a.out).write_text("\n".join(lines))
    print("\n".join(lines))
    spark.stop()


if __name__ == "__main__":
    main()
