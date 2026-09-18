"""Export a consistent read-only snapshot of the normalized database tables."""

from __future__ import annotations

import csv
import os
from pathlib import Path
import shutil
import tempfile


TABLE_EXPORTS = (
    ("geographies", "geographies.csv", "geo_id"),
    ("construction_types", "construction_types.csv", "construction_type_id"),
    ("property_types", "property_types.csv", "property_type_id"),
    ("features", "features.csv", "feature_id"),
    ("contacts", "contacts.csv", "contact_id"),
    ("properties", "properties.csv", "property_id"),
    ("listings", "listings.csv", "listing_id"),
    ("property_features", "property_features.csv", "property_id, feature_id"),
    ("price_history", "price_history.csv", "history_id"),
)

TABLE_SELECTS = {
    "properties": """
        property_id, geo_id, property_type_id, construction_type_id,
        bedrooms, area_m2, floor, total_floors, construction_status,
        year_built,
        CASE WHEN gas IS TRUE THEN 'True'
             WHEN gas IS FALSE THEN 'False' END AS gas,
        tec
    """,
    "listings": """
        listing_id, source_id, property_id, contact_id, transaction_type,
        listing_tier, listing_url, price,
        CASE WHEN price_on_request IS TRUE THEN 'True'
             WHEN price_on_request IS FALSE THEN 'False' END AS price_on_request,
        date_posted, date_modified,
        CASE WHEN has_photos IS TRUE THEN 'True'
             WHEN has_photos IS FALSE THEN 'False' END AS has_photos,
        status, status_changed_at, scraped_at, date_last_checked
    """,
}


def export_database_snapshot(connection, output_dir: str | Path) -> dict[str, int]:
    """Export and validate every table before replacing existing CSV files."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=destination))
    counts: dict[str, int] = {}

    try:
        cursor = connection.cursor()
        try:
            for table, filename, order_by in TABLE_EXPORTS:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                expected = cursor.fetchone()[0]
                staged_path = staging / filename
                select_list = TABLE_SELECTS.get(table, "*")
                with staged_path.open("w", encoding="utf-8-sig", newline="") as file:
                    cursor.copy_expert(
                        f"COPY (SELECT {select_list} FROM {table} ORDER BY {order_by}) "
                        "TO STDOUT WITH (FORMAT CSV, HEADER TRUE)",
                        file,
                    )
                actual = count_csv_rows(staged_path)
                if actual != expected:
                    raise ValueError(
                        f"Snapshot row-count mismatch for {table}: "
                        f"database={expected}, csv={actual}"
                    )
                counts[table] = actual
        finally:
            cursor.close()

        for _table, filename, _order_by in TABLE_EXPORTS:
            os.replace(staging / filename, destination / filename)
        return counts
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def count_csv_rows(path: str | Path) -> int:
    """Count data records without being confused by quoted line breaks."""
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)
        return sum(1 for _row in reader)


def require_database(cursor, expected_database: str) -> None:
    """Stop if the connection does not point to the explicitly requested DB."""
    cursor.execute("SELECT current_database()")
    actual = cursor.fetchone()[0]
    if actual != expected_database:
        raise ValueError(
            f"Connected to {actual!r}, expected {expected_database!r}"
        )
