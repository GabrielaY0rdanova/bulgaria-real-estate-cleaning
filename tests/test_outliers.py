import pandas as pd

from pipeline.outliers import add_outlier_flags


def listing(price, transaction="sale", property_type="apartment", area=70, year=2020):
    return {
        "price": price,
        "price_on_request": False,
        "transaction_type": transaction,
        "property_type_en": property_type,
        "area_m2": area,
        "year_built": year,
    }


def test_sale_prices_are_not_compared_with_rents():
    rows = [listing(100_000 + i * 1_000) for i in range(10)]
    rows += [listing(500 + i * 10, transaction="rental") for i in range(10)]

    flagged = add_outlier_flags(pd.DataFrame(rows))

    assert not flagged["price_outlier"].any()


def test_extreme_price_is_flagged_inside_its_own_market_group():
    rows = [listing(100_000) for _ in range(10)] + [listing(9_000_000)]

    flagged = add_outlier_flags(pd.DataFrame(rows))

    assert flagged.iloc[-1]["price_outlier"]


def test_area_is_compared_with_same_property_type():
    apartments = [listing(100_000, area=70) for _ in range(10)]
    land = [listing(100_000, property_type="plot", area=10_000) for _ in range(10)]

    flagged = add_outlier_flags(pd.DataFrame(apartments + land))

    assert not flagged["area_outlier"].any()


def test_zero_area_and_future_year_are_flagged():
    frame = pd.DataFrame([listing(100_000, area=0, year=2030)])

    flagged = add_outlier_flags(frame, minimum_group_size=1, current_year=2026)

    assert flagged.iloc[0]["area_outlier"]
    assert flagged.iloc[0]["is_future_property"]
    assert not flagged.iloc[0]["year_built_outlier"]
