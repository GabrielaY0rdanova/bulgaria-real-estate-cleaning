"""Apply different listing-change rules for rebuild and incremental inputs."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class PreparedChanges:
    listings: pd.DataFrame
    price_history: pd.DataFrame
    missing_actions: pd.DataFrame


PRICE_HISTORY_COLUMNS = ("source_id", "old_price", "new_price", "changed_at")


def prepare_full_rebuild(cleaned: pd.DataFrame) -> PreparedChanges:
    """Keep the latest row per listing and capture every observed price transition."""
    _require_columns(cleaned, {"source_id", "scraped_at", "price"})
    ordered = cleaned.sort_values(["source_id", "scraped_at"], kind="stable")
    price_rows = []
    for source_id, group in ordered.groupby("source_id", sort=False):
        previous = None
        has_previous = False
        for row in group.itertuples(index=False):
            current = getattr(row, "price")
            if has_previous and not _same_value(previous, current):
                price_rows.append({
                    "source_id": source_id,
                    "old_price": previous,
                    "new_price": current,
                    "changed_at": getattr(row, "scraped_at"),
                })
            previous = current
            has_previous = True

    latest = (
        ordered.sort_values("scraped_at", ascending=False, kind="stable")
        .drop_duplicates(subset=["source_id"], keep="first")
        .copy()
    )
    latest["date_last_checked"] = latest["scraped_at"]
    latest["status_changed_at"] = pd.NaT
    history = pd.DataFrame(price_rows, columns=PRICE_HISTORY_COLUMNS)
    missing = pd.DataFrame(columns=["source_id", "listing_id", "observed_at"])
    return PreparedChanges(latest, history, missing)


def prepare_incremental(cleaned: pd.DataFrame, actions: pd.DataFrame) -> PreparedChanges:
    """Preserve scraper actions instead of inferring monthly changes from row order."""
    _require_columns(cleaned, {"source_id", "scraped_at", "status"})
    _require_columns(
        actions,
        {"source_id", "listing_id", "action", "old_price", "new_price", "observed_at"},
    )
    if cleaned["source_id"].duplicated().any():
        raise ValueError("Incremental rows must contain one row per source_id")
    if actions["source_id"].duplicated().any():
        raise ValueError("Incremental actions must contain one action per source_id")

    action_ids = set(actions["source_id"].astype(str))
    missing = actions.loc[
        actions["action"].eq("missing"),
        ["source_id", "listing_id", "observed_at"],
    ].copy()
    output_action_ids = action_ids - set(missing["source_id"].astype(str))
    row_ids = set(cleaned["source_id"].astype(str))
    if not output_action_ids.issubset(row_ids):
        raise ValueError("Incremental output actions are missing cleaned listing rows")
    unexpected_row_ids = row_ids - action_ids
    if unexpected_row_ids:
        raise ValueError("Incremental cleaned rows have no matching action")

    listings = cleaned.loc[
        cleaned["source_id"].astype(str).isin(output_action_ids)
    ].copy()
    listings["date_last_checked"] = listings["scraped_at"]
    listings["status_changed_at"] = pd.NaT

    changed = actions.loc[actions["action"].eq("changed")].copy()
    history = changed.rename(
        columns={"observed_at": "changed_at"}
    )[["source_id", "old_price", "new_price", "changed_at"]]
    return PreparedChanges(listings, history, missing)


def _require_columns(frame: pd.DataFrame, required: set[str]) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")


def _same_value(left, right) -> bool:
    if pd.isna(left) and pd.isna(right):
        return True
    if pd.isna(left) or pd.isna(right):
        return False
    return left == right
