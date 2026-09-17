"""Reusable outlier rules for cleaned real-estate listings."""

from __future__ import annotations

import pandas as pd


def iqr_outliers(series: pd.Series, *, k: float = 3.0) -> pd.Series:
    """Return a boolean mask aligned to ``series`` using the k×IQR rule."""
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    return (series < q1 - k * iqr) | (series > q3 + k * iqr)


def add_outlier_flags(
    frame: pd.DataFrame,
    *,
    minimum_group_size: int = 10,
    current_year: int | None = None,
) -> pd.DataFrame:
    """Add comparable price, area and construction-year quality flags.

    Prices are compared within transaction type and property type. Areas are
    compared within property type. This avoids treating normal sale prices as
    anomalous beside rents, or comparing land and hotels with apartments.
    """
    required = {
        "price", "price_on_request", "transaction_type", "property_type_en",
        "area_m2", "year_built",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns for outlier flags: {sorted(missing)}")

    result = frame.copy()
    result["price_outlier"] = False
    price_rows = result.loc[
        result["price"].notna() & ~result["price_on_request"].fillna(False)
    ]
    for _, group in price_rows.groupby(
        ["transaction_type", "property_type_en"], dropna=False
    ):
        if len(group) >= minimum_group_size:
            flags = iqr_outliers(group["price"])
            result.loc[flags[flags].index, "price_outlier"] = True

    result["area_outlier"] = False
    area_rows = result.loc[result["area_m2"].notna()]
    for _, group in area_rows.groupby("property_type_en", dropna=False):
        if len(group) >= minimum_group_size:
            flags = iqr_outliers(group["area_m2"])
            result.loc[flags[flags].index, "area_outlier"] = True
    result.loc[result["area_m2"].eq(0), "area_outlier"] = True

    year = current_year if current_year is not None else pd.Timestamp.now().year
    result["year_built_outlier"] = (
        result["year_built"].notna()
        & ((result["year_built"] < 1800) | (result["year_built"] > 2040))
    )
    result["is_future_property"] = (
        result["year_built"].notna() & (result["year_built"] > year)
    )
    return result
