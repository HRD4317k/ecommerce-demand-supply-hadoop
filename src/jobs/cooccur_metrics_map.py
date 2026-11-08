#!/usr/bin/env python3
"""Bundle mining, stage 3 map (idea 7).

Input : KEY<TAB>count            (output of stage 2; KEY is TOTAL, ITEM|a or PAIR|a|b)
Emits : ALL<TAB>KEY,count        (a single key, so ONE reducer sees every count; the data is
                                  tiny - one row per SKU and per SKU pair - so that is fine)
"""
import sys


def main():
    for line in sys.stdin:
        key, _, count = line.rstrip("\n").partition("\t")
        if key:
            print(f"ALL\t{key},{count}")


if __name__ == "__main__":
    main()
