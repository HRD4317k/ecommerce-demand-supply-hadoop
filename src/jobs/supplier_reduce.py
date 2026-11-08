#!/usr/bin/env python3
"""Supplier scorecard, reduce step (idea 6).

Output: supplier_id <TAB> n_pos,on_time_rate,avg_delay_days,lead_mean,lead_std,fill_rate,score,tier

  on_time_rate   share of POs delivered on or before the promised date
  avg_delay_days mean of (delivered - promised); negative = early
  lead_mean/std  observed order-to-delivery days (the planner uses these, not the quote)
  fill_rate      units received / units ordered
  score          0-100:  100 * (0.4 * on_time + 0.4 * fill + 0.2 * (1 - min(1, std / mean)))
  tier           A >= 85, B >= 70, otherwise C
"""
import sys
from statistics import mean, pstdev


def score_of(on_time, fill, lead_mean, lead_std):
    consistency = 1.0 - min(1.0, lead_std / lead_mean) if lead_mean > 0 else 0.0
    return 100.0 * (0.4 * on_time + 0.4 * min(1.0, fill) + 0.2 * consistency)


def tier_of(score):
    return "A" if score >= 85 else ("B" if score >= 70 else "C")


def summarise(rows):
    """rows: (lead, delay, qty_ordered, qty_received); lead/delay are None for unfulfilled lines."""
    done = [r for r in rows if r[0] is not None]
    if not done:
        return None                                   # nothing delivered: no lead-time statistics to report
    leads = [r[0] for r in done]
    delays = [r[1] for r in done]
    ordered = sum(r[2] for r in rows)
    received = sum(r[3] for r in rows)
    on_time = sum(1 for d in delays if d <= 0) / len(done)
    fill = received / ordered if ordered else 0.0
    lead_mean, lead_std = mean(leads), pstdev(leads)
    score = score_of(on_time, fill, lead_mean, lead_std)
    return (f"{len(rows)},{on_time:.3f},{mean(delays):.2f},{lead_mean:.2f},{lead_std:.2f},"
            f"{fill:.3f},{score:.1f},{tier_of(score)}")


def emit(key, rows):
    if key is None:
        return
    line = summarise(rows)
    if line:
        print(f"{key}\t{line}")


def main():
    current, rows = None, []
    for line in sys.stdin:
        key, _, value = line.rstrip("\n").partition("\t")
        if key != current:
            emit(current, rows)
            current, rows = key, []
        lead, delay, qo, qr = value.split(",")
        rows.append((None if lead == "NA" else int(lead), None if delay == "NA" else int(delay),
                     int(qo), int(qr)))
    emit(current, rows)


if __name__ == "__main__":
    main()
