"""Summarise a Hadoop run: per-job counters (from Hadoop's own log) + wall-clock times,
and check that the Hadoop outputs equal the local-runner outputs.

Usage: python src/analysis/hadoop_summary.py --hadoop out/olist_hadoop --local out/olist --reports reports
Writes reports/HADOOP_RUN.md, reports/figures/hadoop_jobs.png and out/.../hadoop_summary.json.
"""
import argparse
import json
import os
import re

JOB_LABELS = {
    "daily_demand": "1 net daily demand",
    "supplier_stats": "2 supplier scorecard",
    "gap_report": "3 gap engine",
    "uplift": "4 festive uplift",
    "pairs_raw": "5a bundle pairs",
    "pair_counts": "5b pair counts",
    "bundles": "5c bundle metrics",
    "pairs_raw_p": "5a' pairs (products)",
    "pair_counts_p": "5b' counts (products)",
    "bundles_p": "5c' metrics (products)",
    "return_rates": "6 return rates",
}
KEYS = {
    "map_in": "Map input records", "map_out": "Map output records",
    "comb_in": "Combine input records", "comb_out": "Combine output records",
    "red_groups": "Reduce input groups", "red_in": "Reduce input records",
    "red_out": "Reduce output records", "shuffle_bytes": "Reduce shuffle bytes",
}


def parse_counters(text):
    """One dict per 'Counters:' block, in the order the jobs ran."""
    blocks = re.split(r"INFO Job: Counters: \d+", text)[1:]
    out = []
    for b in blocks:
        d = {}
        for key, label in KEYS.items():
            m = re.search(re.escape(label) + r"=(\d+)", b)
            d[key] = int(m.group(1)) if m else 0
        out.append(d)
    return out


def read_times(path):
    rows = []
    with open(path) as f:
        for line in f:
            if line.strip():
                name, sec = line.rstrip("\n").split("\t")
                rows.append((name, float(sec)))
    return rows


def compare_dirs(local, hadoop):
    """Return (identical, differing, missing) file lists; rows are compared as sorted line sets."""
    same, diff, missing = [], [], []
    for fn in sorted(os.listdir(local)):
        a, b = os.path.join(local, fn), os.path.join(hadoop, fn)
        if not os.path.isfile(a) or fn.startswith("hadoop_"):
            continue
        if not os.path.exists(b):
            missing.append(fn)
            continue
        if fn.endswith(".json"):
            eq = json.load(open(a)) == json.load(open(b))
        else:
            eq = sorted(l.rstrip("\n") for l in open(a) if l.strip()) == sorted(l.rstrip("\n") for l in open(b) if l.strip())
        (same if eq else diff).append(fn)
    return same, diff, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hadoop", required=True)
    ap.add_argument("--local", required=True)
    ap.add_argument("--reports", default="reports")
    a = ap.parse_args()

    counters = parse_counters(open(os.path.join(a.hadoop, "hadoop_counters.log")).read())
    times = read_times(os.path.join(a.hadoop, "hadoop_job_times.tsv"))
    if len(counters) != len(times):
        raise SystemExit(f"{len(counters)} counter blocks vs {len(times)} timed jobs")
    jobs = []
    for (name, sec), c in zip(times, counters):
        jobs.append({"job": name, "label": JOB_LABELS.get(name, name), "seconds": sec, **c})
    same, diff, missing = compare_dirs(a.local, a.hadoop)
    summary = {"jobs": jobs, "identical_files": same, "differing_files": diff, "missing_files": missing,
               "total_job_seconds": round(sum(j["seconds"] for j in jobs), 1)}
    json.dump(summary, open(os.path.join(a.hadoop, "hadoop_summary.json"), "w"), indent=2)

    os.makedirs(os.path.join(a.reports, "figures"), exist_ok=True)
    lines = ["# Hadoop Streaming run\n",
             "Same pipeline as the local runner, executed by Apache Hadoop 3.3.4 (real MapReduce engine and real "
             "Hadoop Streaming, **standalone mode**: one JVM, local file system, no HDFS/YARN daemons). "
             "Counters below are Hadoop's own.\n",
             "| job | map in | map out | combiner in → out | reduce groups | reduce out | shuffle KB | seconds |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for j in jobs:
        comb = f"{j['comb_in']:,} → {j['comb_out']:,}" if j["comb_in"] else "no combiner"
        lines.append(f"| {j['label']} | {j['map_in']:,} | {j['map_out']:,} | {comb} | {j['red_groups']:,} | "
                     f"{j['red_out']:,} | {j['shuffle_bytes'] / 1024:,.0f} | {j['seconds']:.1f} |")
    lines += ["", f"Outputs identical to the local runner: **{len(same)} of {len(same) + len(diff) + len(missing)}** files"
              + (f" (differing: {', '.join(diff)}; missing: {', '.join(missing)})" if diff or missing else "."), ""]
    open(os.path.join(a.reports, "HADOOP_RUN.md"), "w").write("\n".join(lines))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    comb = [j for j in jobs if j["comb_in"]]
    fig, ax = plt.subplots(figsize=(9, 4.4), dpi=160)
    x = range(len(comb))
    ax.bar([i - 0.2 for i in x], [j["comb_in"] for j in comb], 0.4, label="records leaving the mappers", color="#8A94A3")
    ax.bar([i + 0.2 for i in x], [j["comb_out"] for j in comb], 0.4, label="records after the combiner (shuffled)", color="#E8622B")
    ax.set_xticks(list(x))
    ax.set_xticklabels([j["label"] for j in comb], rotation=18, ha="right", fontsize=8)
    ax.set_ylabel("records")
    ax.set_title("What the combiner saves the shuffle (Hadoop counters)", fontsize=11)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(a.reports, "figures", "hadoop_combiner.png"))
    print("wrote", os.path.join(a.reports, "HADOOP_RUN.md"), "| identical:", len(same), "differing:", diff, "missing:", missing)


if __name__ == "__main__":
    main()
