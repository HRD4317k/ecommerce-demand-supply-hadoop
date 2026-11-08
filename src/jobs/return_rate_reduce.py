#!/usr/bin/env python3
"""Return rates, reduce step (idea 8).

Output: SCOPE|name <TAB> ordered,returned,return_rate
sum_reduce.py is used as the combiner (it keeps the "ordered,returned" format).
"""
import sys


def main():
    current, ordered, returned = None, 0, 0
    for line in sys.stdin:
        key, _, value = line.rstrip("\n").partition("\t")
        if key != current:
            if current is not None:
                print(f"{current}\t{ordered},{returned},{returned / ordered if ordered else 0:.4f}")
            current, ordered, returned = key, 0, 0
        o, r = value.split(",")
        ordered += int(o)
        returned += int(r)
    if current is not None:
        print(f"{current}\t{ordered},{returned},{returned / ordered if ordered else 0:.4f}")


if __name__ == "__main__":
    main()
