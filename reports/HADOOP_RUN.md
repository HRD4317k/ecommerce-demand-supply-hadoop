# Hadoop Streaming run

Same pipeline as the local runner, executed by Apache Hadoop 3.3.4 (real MapReduce engine and real Hadoop Streaming, **standalone mode**: one JVM, local file system, no HDFS/YARN daemons). Counters below are Hadoop's own.

| job | map in | map out | combiner in → out | reduce groups | reduce out | shuffle KB | seconds |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 net daily demand | 97,449 | 97,447 | 97,447 → 45,019 | 44,597 | 44,597 | 1,596 | 3.8 |
| 2 supplier scorecard | 96,082 | 96,081 | no combiner | 2,925 | 2,872 | 1,983 | 3.9 |
| 3 gap engine | 44,691 | 44,690 | no combiner | 356 | 93 | 1,498 | 3.8 |
| 4 festive uplift | 97,015 | 194,028 | no combiner | 80 | 69 | 5,955 | 3.6 |
| 5a bundle pairs | 97,015 | 97,014 | no combiner | 96,285 | 194,043 | 2,060 | 3.8 |
| 5b pair counts | 194,043 | 194,043 | 194,043 → 689 | 315 | 315 | 22 | 3.7 |
| 5c bundle metrics | 315 | 315 | no combiner | 1 | 8 | 12 | 2.8 |
| 5a' pairs (products) | 99,913 | 99,912 | no combiner | 96,285 | 200,501 | 1,647 | 3.9 |
| 5b' counts (products) | 200,501 | 200,501 | 200,501 → 55,847 | 35,849 | 35,849 | 1,019 | 4.7 |
| 5c' metrics (products) | 35,849 | 35,849 | no combiner | 1 | 7 | 806 | 3.8 |
| 6 return rates | 97,449 | 194,894 | 194,894 → 135 | 80 | 80 | 4 | 3.7 |

Outputs identical to the local runner: **16 of 16** files.
