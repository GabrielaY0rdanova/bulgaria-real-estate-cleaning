"""Datetime parsing shared by cleaning pipeline steps."""

import pandas as pd


def parse_mixed_utc(values):
    """Parse supported ISO-like timestamp variants and normalise them to UTC."""
    return pd.to_datetime(values, format="mixed", utc=True, errors="raise")
