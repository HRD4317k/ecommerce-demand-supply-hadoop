#!/usr/bin/env python3
"""Generic reducer / combiner: sum every comma-separated numeric field per key.

Input  : key<TAB>f1,f2,...   (sorted by key)
Output : key<TAB>sum(f1),sum(f2),...

Because addition is associative and commutative the very same script is the combiner
(it runs on each mapper's local output and shrinks the shuffle) and the reducer.
Used by: daily demand (idea 8), the pair counter (idea 7) and the return-rate job.
"""
import sys


def num(text):
    try:
        return int(text)
    except ValueError:
        return float(text)


def main():
    current, totals = None, None
    for line in sys.stdin:
        key, _, value = line.rstrip("\n").partition("\t")
        fields = [num(x) for x in value.split(",")]
        if key != current:
            if current is not None:
                print(current + "\t" + ",".join(str(x) for x in totals))
            current, totals = key, fields
        else:
            totals = [a + b for a, b in zip(totals, fields)]
    if current is not None:
        print(current + "\t" + ",".join(str(x) for x in totals))


if __name__ == "__main__":
    main()
