#!/usr/bin/env python3
"""Bundle mining, stage 1 map (idea 7).

orders.csv: order_id,date,sku,category,warehouse,qty,price
An order is a basket: all lines sharing an order_id.

Emits  order_id <TAB> sku    (so every basket reaches one reducer)
"""
import sys


def main():
    for line in sys.stdin:
        p = line.rstrip("\n").split(",")
        if len(p) < 7 or p[0] == "order_id":
            continue
        print(f"{p[0]}\t{p[2]}")


if __name__ == "__main__":
    main()
