#!/usr/bin/env python3
"""Gap engine, map step (ideas 1, 2 and 3): a reduce-side join plus a map-side join.

Inputs (two ``-input`` paths, told apart by their shape):
  daily demand lines  sku|warehouse|date <TAB> ordered,returned,net      (output of the daily-demand job)
  inventory.csv rows  sku,warehouse,on_hand,on_order,supplier_id,nominal_lead_days

Reduce-side join : both record types are emitted under the key  sku|warehouse  tagged D or I.
Map-side join    : the small supplier scorecard is loaded from the distributed cache
                   (``-files supplier_stats.tsv``) and attached to each inventory row here,
                   so no third shuffle is needed.

Emits
  sku|wh <TAB> D,date,net
  sku|wh <TAB> I,on_hand,on_order,supplier_id,nominal_lead,lead_mean,lead_std,fill_rate,tier
"""
import os
import sys

from config import DEFAULT_FILL_RATE, DEFAULT_LEAD_STD, SUPPLIER_STATS_FILE


def load_suppliers(path):
    stats = {}
    if not os.path.exists(path):
        return stats
    with open(path) as handle:
        for line in handle:
            key, _, value = line.rstrip("\n").partition("\t")
            n, on_time, delay, lead_mean, lead_std, fill, score, tier = value.split(",")
            stats[key] = (float(lead_mean), float(lead_std), float(fill), tier)
    return stats


def main():
    suppliers = load_suppliers(SUPPLIER_STATS_FILE)
    for line in sys.stdin:
        line = line.rstrip("\n")
        if not line or line.startswith("sku,"):
            continue
        if "\t" in line:                                   # daily demand record
            key, _, value = line.partition("\t")
            sku, wh, date = key.split("|")
            net = value.split(",")[2]
            print(f"{sku}|{wh}\tD,{date},{net}")
        else:                                              # inventory record
            sku, wh, on_hand, on_order, supplier, nominal = line.split(",")[:6]
            lead_mean, lead_std, fill, tier = suppliers.get(
                supplier, (float(nominal), DEFAULT_LEAD_STD, DEFAULT_FILL_RATE, "?"))
            print(f"{sku}|{wh}\tI,{on_hand},{on_order},{supplier},{nominal},"
                  f"{lead_mean},{lead_std},{fill},{tier}")


if __name__ == "__main__":
    main()
