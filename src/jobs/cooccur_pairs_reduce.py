#!/usr/bin/env python3
"""Bundle mining, stage 1 reduce (idea 7): the classic "pairs" approach.

One call = one basket.  Emits a count of 1 for
  TOTAL           the basket itself
  ITEM|a          each distinct SKU in the basket
  PAIR|a|b        each unordered pair of distinct SKUs (a < b)

Stage 2 (sum_reduce.py) adds the ones up across all baskets.
"""
import itertools
import sys


def emit(skus):
    items = sorted(set(skus))
    print("TOTAL\t1")
    for a in items:
        print(f"ITEM|{a}\t1")
    for a, b in itertools.combinations(items, 2):
        print(f"PAIR|{a}|{b}\t1")


def main():
    current, skus = None, []
    for line in sys.stdin:
        key, _, sku = line.rstrip("\n").partition("\t")
        if key != current:
            if current is not None:
                emit(skus)
            current, skus = key, []
        skus.append(sku)
    if current is not None:
        emit(skus)


if __name__ == "__main__":
    main()
