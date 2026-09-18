import pandas as pd
import pytest

from pipeline.datetime_parsing import parse_mixed_utc


def test_parse_mixed_utc_accepts_scraper_and_database_formats():
    parsed = parse_mixed_utc(pd.Series([
        "2026-09-18T07:11:15.123456+00:00",
        "2026-04-06 19:11:01.183359",
    ]))

    assert str(parsed.dtype) == "datetime64[ns, UTC]"
    assert parsed.iloc[0] == pd.Timestamp("2026-09-18T07:11:15.123456Z")
    assert parsed.iloc[1] == pd.Timestamp("2026-04-06T19:11:01.183359Z")


def test_parse_mixed_utc_rejects_invalid_values():
    with pytest.raises(ValueError):
        parse_mixed_utc(pd.Series(["not-a-timestamp"]))
