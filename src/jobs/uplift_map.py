#!/usr/bin/env python3
"""Festive-sale uplift, map step (idea 5).

orders.csv: order_id,date,sku,category,warehouse,qty,price

Every order line is emitted twice so ONE job answers both questions:
  CAT|<category> <TAB> date,qty      uplift of a whole category
  SKU|<sku>      <TAB> date,qty      uplift of a single product
"""
import sys


def main():
    for line in sys.stdin:
        p = line.rstrip("\n").split(",")
        if len(p) < 7 or p[0] == "order_id":
            continue
        _, date, sku, category, _, qty, _ = p[:7]
        print(f"CAT|{category}\t{date},{qty}")
        print(f"SKU|{sku}\t{date},{qty}")


if __name__ == "__main__":
    main()
