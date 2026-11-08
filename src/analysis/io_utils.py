"""Helpers to load the job outputs (key<TAB>v1,v2,... files and gap_report.csv) as DataFrames."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "jobs"))
import schema  # noqa: E402  (shared column names)


def _numeric(series):
    try:
        return pd.to_numeric(series)
    except (ValueError, TypeError):
        return series


def read_job_tsv(path, key_names, value_names):
    """Read a MapReduce output file into a DataFrame with one column per key/value part."""
    rows = []
    with open(path) as handle:
        for line in handle:
            key, _, value = line.rstrip("\n").partition("\t")
            rows.append(key.split("|") + value.split(","))
    frame = pd.DataFrame(rows, columns=key_names + value_names)
    for column in value_names:
        frame[column] = _numeric(frame[column])
    return frame


def read_daily(path):
    return read_job_tsv(path, schema.DAILY_KEY, schema.DAILY_FIELDS)


def read_suppliers(path):
    return read_job_tsv(path, schema.SUPPLIER_KEY, schema.SUPPLIER_FIELDS)


def read_uplift(path):
    return read_job_tsv(path, schema.UPLIFT_KEY, schema.UPLIFT_FIELDS)


def read_bundles(path):
    return read_job_tsv(path, schema.BUNDLE_KEY, schema.BUNDLE_FIELDS)


def read_returns(path):
    return read_job_tsv(path, schema.RETURN_KEY, schema.RETURN_FIELDS)


def read_gap(path):
    return pd.read_csv(path)
