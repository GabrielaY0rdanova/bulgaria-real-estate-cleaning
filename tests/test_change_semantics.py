import pandas as pd
import pytest

from pipeline.change_semantics import prepare_full_rebuild, prepare_incremental


def test_full_rebuild_keeps_latest_listing_and_every_price_transition():
    rows = pd.DataFrame([
        {"source_id": "a", "scraped_at": pd.Timestamp("2026-04-01", tz="UTC"), "price": 100},
        {"source_id": "a", "scraped_at": pd.Timestamp("2026-05-01", tz="UTC"), "price": 120},
        {"source_id": "a", "scraped_at": pd.Timestamp("2026-07-01", tz="UTC"), "price": 110},
        {"source_id": "b", "scraped_at": pd.Timestamp("2026-04-02", tz="UTC"), "price": 50},
    ])

    prepared = prepare_full_rebuild(rows)

    assert len(prepared.listings) == 2
    assert prepared.listings.set_index("source_id").loc["a", "price"] == 110
    assert prepared.price_history[["source_id", "old_price", "new_price"]].to_dict("records") == [
        {"source_id": "a", "old_price": 100, "new_price": 120},
        {"source_id": "a", "old_price": 120, "new_price": 110},
    ]
    assert prepared.missing_actions.empty


def test_full_rebuild_treats_null_to_value_as_a_price_transition():
    rows = pd.DataFrame([
        {"source_id": "a", "scraped_at": pd.Timestamp("2026-04-01", tz="UTC"), "price": None},
        {"source_id": "a", "scraped_at": pd.Timestamp("2026-05-01", tz="UTC"), "price": 100},
    ])

    prepared = prepare_full_rebuild(rows)

    assert len(prepared.price_history) == 1
    assert pd.isna(prepared.price_history.iloc[0]["old_price"])
    assert prepared.price_history.iloc[0]["new_price"] == 100


def test_incremental_uses_actions_for_price_history_and_missing_rows():
    listings = pd.DataFrame([
        {
            "source_id": "changed", "scraped_at": pd.Timestamp("2026-09-17", tz="UTC"),
            "status": "active", "price": 120,
        },
        {
            "source_id": "new", "scraped_at": pd.Timestamp("2026-09-17", tz="UTC"),
            "status": "active", "price": 50,
        },
        {
            "source_id": "gone", "scraped_at": pd.Timestamp("2026-04-01", tz="UTC"),
            "status": "active", "price": 75,
        },
    ])
    actions = pd.DataFrame([
        {
            "source_id": "changed", "listing_id": 1, "action": "changed",
            "old_price": 100, "new_price": 120, "observed_at": "2026-09-17T08:00:00Z",
        },
        {
            "source_id": "new", "listing_id": None, "action": "new",
            "old_price": None, "new_price": 50, "observed_at": "2026-09-17T08:00:00Z",
        },
        {
            "source_id": "gone", "listing_id": 2, "action": "missing",
            "old_price": None, "new_price": None, "observed_at": "2026-09-17T08:00:00Z",
        },
    ])

    prepared = prepare_incremental(listings, actions)

    assert list(prepared.price_history["source_id"]) == ["changed"]
    assert prepared.price_history.iloc[0]["old_price"] == 100
    assert prepared.price_history.iloc[0]["new_price"] == 120
    assert prepared.missing_actions.to_dict("records") == [{
        "source_id": "gone", "listing_id": 2.0,
        "observed_at": "2026-09-17T08:00:00Z",
    }]
    assert set(prepared.listings["source_id"]) == {"changed", "new"}
    assert prepared.listings["date_last_checked"].equals(prepared.listings["scraped_at"])


def test_incremental_rejects_duplicate_rows():
    listings = pd.DataFrame([
        {"source_id": "a", "scraped_at": "now", "status": "active"},
        {"source_id": "a", "scraped_at": "later", "status": "active"},
    ])
    actions = pd.DataFrame(columns=[
        "source_id", "listing_id", "action", "old_price", "new_price", "observed_at",
    ])

    with pytest.raises(ValueError, match="one row per source_id"):
        prepare_incremental(listings, actions)


def test_incremental_rejects_action_without_cleaned_output_row():
    listings = pd.DataFrame([
        {"source_id": "a", "scraped_at": "now", "status": "active"},
    ])
    actions = pd.DataFrame([{
        "source_id": "b", "listing_id": 1, "action": "changed",
        "old_price": 1, "new_price": 2, "observed_at": "now",
    }])

    with pytest.raises(ValueError, match="missing cleaned listing rows"):
        prepare_incremental(listings, actions)
