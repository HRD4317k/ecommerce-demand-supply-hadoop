#!/usr/bin/env python3
"""Return rates, map step (idea 8).

Reads orders.csv and returns.csv (see daily_demand_map.py for the layouts).

Emits (for each line, once for the category and once for the SKU)
  CAT|<category> <TAB> ordered,returned
  SKU|<sku>      <TAB> ordered,returned
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
            _, _, sku, category, _, _, qty = p[:7]
            value = f"0,{int(qty)}"
        else:
            _, _, sku, category, _, qty = p[:6]
            value = f"{int(qty)},0"
        print(f"CAT|{category}\t{value}")
        print(f"SKU|{sku}\t{value}")


if __name__ == "__main__":
    main()
