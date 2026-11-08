#!/usr/bin/env python3
"""Net daily demand, map step (ideas 1 and 8).

Reads BOTH orders.csv and returns.csv (two ``-input`` paths).  Hadoop tells a mapper
which file its split came from through the ``mapreduce_map_input_file`` environment
variable; if that is missing we fall back to the id prefix (return ids start with "R").

orders.csv : order_id,date,sku,category,warehouse,qty,price
returns.csv: return_id,order_id,sku,category,warehouse,return_date,qty,reason

Emits  sku|warehouse|date <TAB> ordered,returned,net
  an order line    -> qty,0,qty         (counted on the order date)
  a returned line  -> 0,qty,-qty        (counted on the day the goods come back)
"""
import os
import sys

HEADERS = {"order_id", "return_id"}


def main():
    source = os.environ.get("mapreduce_map_input_file") or os.environ.get("map_input_file") or ""
    from_returns_file = "return" in os.path.basename(source).lower()
    for line in sys.stdin:
        p = line.rstrip("\n").split(",")
        if len(p) < 7 or p[0] in HEADERS:
            continue
        if from_returns_file or p[0].startswith("R"):
            _, _, sku, _, wh, date, qty = p[:7]
            qty = int(qty)
            print(f"{sku}|{wh}|{date}\t0,{qty},{-qty}")
        else:
            _, date, sku, _, wh, qty = p[:6]
            qty = int(qty)
            print(f"{sku}|{wh}|{date}\t{qty},0,{qty}")


if __name__ == "__main__":
    main()
