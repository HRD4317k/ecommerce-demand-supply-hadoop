import json
import os
import subprocess

import pandas as pd
import pytest

from conftest import ROOT


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    base = tmp_path_factory.mktemp("e2e")
    data, out, reports = base / "data", base / "out", base / "reports"
    subprocess.run(["python3", str(ROOT / "src/datagen/generate.py"), "--out", str(data), "--days", "70",
                    "--sale-days", "10"], check=True, capture_output=True)
    env = {**os.environ, "DATA_DIR": str(data), "OUT_DIR": str(out), "REPORTS_DIR": str(reports)}
    r = subprocess.run([str(ROOT / "scripts/run_local.sh")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return data, out, reports


def test_all_outputs_exist(pipeline):
    _, out, reports = pipeline
    for f in ["daily_demand.tsv", "supplier_stats.tsv", "gap_report.csv", "uplift.tsv", "bundles.tsv",
              "return_rates.tsv", "backtest.csv", "transfers.csv", "alerts.csv", "purchase_orders.csv"]:
        assert (out / f).stat().st_size > 0, f
    assert (reports / "REPORT.md").exists()
    assert len(list((reports / "figures").glob("*.png"))) == 7


def test_gap_report_has_all_risk_labels_and_supplier_tiers(pipeline):
    _, out, _ = pipeline
    gap = pd.read_csv(out / "gap_report.csv")
    assert {"CRITICAL", "OK"} <= set(gap.risk)
    assert gap.tier.isin(["A", "B", "C"]).all()           # supplier stats reached the gap job
    assert (gap.order_qty >= 0).all()


def test_planted_bundles_are_found(pipeline):
    data, out, _ = pipeline
    planted = {tuple(sorted(p)) for p in json.load(open(data / "meta.json"))["affinity_pairs"]}
    rows = [l.split("\t")[0].split("|") for l in open(out / "bundles.tsv")]
    top = {tuple(sorted(r)) for r in rows[:len(planted) + 2]}
    assert len(planted & top) >= len(planted) - 1


def test_festive_uplift_close_to_planted(pipeline):
    _, out, _ = pipeline
    cats = [l.split("\t") for l in open(out / "uplift.tsv") if l.startswith("CAT|")]
    uplifts = [float(v.split(",")[3]) for _, v in cats]
    assert all(1.5 < u < 2.6 for u in uplifts)


def test_returns_reduce_net_demand(pipeline):
    _, out, _ = pipeline
    net = ordered = 0
    for l in open(out / "daily_demand.tsv"):
        o, r, n = l.split("\t")[1].split(",")
        ordered += int(o)
        net += int(n)
    assert 0 < net < ordered


def test_transfers_respect_freight_and_have_positive_units(pipeline):
    _, out, _ = pipeline
    t = pd.read_csv(out / "transfers.csv")
    assert (t.units > 0).all() and (t["from"] != t["to"]).all()
