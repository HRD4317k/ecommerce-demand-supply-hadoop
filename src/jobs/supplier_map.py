#!/usr/bin/env python3
"""Supplier scorecard, map step (idea 6).

deliveries.csv: po_id,supplier_id,sku,warehouse,order_date,promised_date,delivered_date,
                qty_ordered,qty_received

Emits  supplier_id <TAB> lead_days,delay_days,qty_ordered,qty_received
  lead_days  = delivered - ordered          (what the supplier really takes)
  delay_days = delivered - promised         (> 0 means late)
"""
import datetime as dt
import sys


def day(text):
    return dt.date.fromisoformat(text)


def main():
    for line in sys.stdin:
        p = line.rstrip("\n").split(",")
        if len(p) < 9 or p[0] == "po_id":
            continue
        _, supplier, _, _, ordered, promised, delivered, qo, qr = p[:9]
        lead = (day(delivered) - day(ordered)).days
        delay = (day(delivered) - day(promised)).days
        print(f"{supplier}\t{lead},{delay},{qo},{qr}")


if __name__ == "__main__":
    main()
