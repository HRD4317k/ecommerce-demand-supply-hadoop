#!/usr/bin/env python3
"""Bundle mining, stage 3 reduce (idea 7): support, confidence and lift.

Output: sku_a|sku_b <TAB> pair_orders,support,conf_a_to_b,conf_b_to_a,lift   (best lift first)

  support     share of all baskets that contain both
  conf a->b   P(b in basket | a in basket)
  lift        P(a and b) / (P(a) * P(b)); 1 = independent, > 1 = bought together more than chance

Pairs seen in fewer than MIN_PAIR_COUNT baskets are dropped: a lift from three baskets is noise.
"""
import sys

from config import MIN_PAIR_COUNT


def metrics(total, items, pairs, min_count):
    rows = []
    for (a, b), n in pairs.items():
        if n < min_count:
            continue
        ca, cb = items[a], items[b]
        rows.append((a, b, n, n / total, n / ca, n / cb, n * total / (ca * cb)))
    rows.sort(key=lambda r: (-r[6], -r[2], r[0], r[1]))
    return rows


def main():
    total, items, pairs = 0, {}, {}
    for line in sys.stdin:
        _, _, value = line.rstrip("\n").partition("\t")
        key, count = value.rsplit(",", 1)
        count = int(count)
        kind, _, rest = key.partition("|")
        if kind == "TOTAL":
            total = count
        elif kind == "ITEM":
            items[rest] = count
        elif kind == "PAIR":
            a, b = rest.split("|")
            pairs[(a, b)] = count
    for a, b, n, support, c_ab, c_ba, lift in metrics(total, items, pairs, MIN_PAIR_COUNT):
        print(f"{a}|{b}\t{n},{support:.4f},{c_ab:.3f},{c_ba:.3f},{lift:.2f}")


if __name__ == "__main__":
    main()
