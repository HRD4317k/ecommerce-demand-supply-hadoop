import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "analysis"))
import hadoop_summary  # noqa: E402

SAMPLE = """07:30:53 INFO Job: Counters: 30
\tMap-Reduce Framework
\t\tMap input records=10
\t\tMap output records=9
\t\tCombine input records=9
\t\tCombine output records=4
\t\tReduce input groups=4
\t\tReduce shuffle bytes=2048
\t\tReduce input records=4
\t\tReduce output records=4
07:30:58 INFO Job: Counters: 30
\tMap-Reduce Framework
\t\tMap input records=4
\t\tMap output records=4
\t\tReduce input groups=2
\t\tReduce input records=4
\t\tReduce output records=2
"""


def test_parse_counters_one_block_per_job_in_order():
    c = hadoop_summary.parse_counters(SAMPLE)
    assert len(c) == 2
    assert c[0]["map_in"] == 10 and c[0]["comb_in"] == 9 and c[0]["comb_out"] == 4
    assert c[0]["shuffle_bytes"] == 2048
    assert c[1]["comb_in"] == 0                      # job without a combiner reports no combine counters
    assert c[1]["red_out"] == 2


def test_compare_dirs_ignores_line_order_and_flags_differences(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "x.tsv").write_text("1\n2\n")
    (b / "x.tsv").write_text("2\n1\n")
    (a / "y.tsv").write_text("1\n")
    (b / "y.tsv").write_text("9\n")
    (a / "z.tsv").write_text("1\n")
    same, diff, missing = hadoop_summary.compare_dirs(str(a), str(b))
    assert same == ["x.tsv"] and diff == ["y.tsv"] and missing == ["z.tsv"]
