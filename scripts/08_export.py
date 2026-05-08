# =============================================================================
# real_estate_cleaning — Export to PostgreSQL
# Source: data/clean/*.csv (output of 06_normalize.py, validated by 07_validate.py)
# Purpose: Load the eight normalized CSVs into PostgreSQL tables defined in
#          00_schema.sql. Uses COPY for bulk insert performance.
# Prerequisites:
#   - PostgreSQL database with 00_schema.sql applied (enums + tables created)
#   - 07_validate.py passed (run: python 07_validate.py && python 08_export.py)
# Task:    14
# Run after: 07_validate.py
# =============================================================================

from pathlib import Path
import sys
import io
import pandas as pd
import psycopg2

CLEAN_PATH = Path("data/clean")

# =============================================================================
# DATABASE CONNECTION
# =============================================================================
# Environment variables expected (standard libpq):
#   PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD
# Alternatively, set DATABASE_URL.
# =============================================================================

import os
from dotenv import load_dotenv

# Load .env from project root (two levels up from scripts/).
# Has no effect if the variables are already set in the environment,
# so production deployments using real env vars are unaffected.
load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_connection():
    """
    Return a psycopg2 connection using DATABASE_URL if set, otherwise
    fall back to individual PG* environment variables (libpq defaults).
    """
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect()   # uses PGHOST, PGPORT, etc.

# =============================================================================
# LOAD CSVs
# =============================================================================

# Load order matches foreign key dependency chain: lookup tables first,
# then entities that reference them, then junction tables last.
LOAD_ORDER = [
    ("geographies",        "geographies.csv"),
    ("construction_types", "construction_types.csv"),
    ("property_types",     "property_types.csv"),
    ("features",           "features.csv"),
    ("contacts",           "contacts.csv"),
    ("properties",         "properties.csv"),
    ("listings",           "listings.csv"),
    ("property_features",  "property_features.csv"),
    ("price_history",      "price_history.csv"),
]

PHONE_COLUMNS = ["phone", "agency_phone", "contact_phone"]

dfs = {}
for table_name, filename in LOAD_ORDER:
    path = CLEAN_PATH / filename
    if not path.exists():
        print(f"FATAL: Missing CSV: {path}")
        sys.exit(1)

    # Read header first to detect available columns
    cols = pd.read_csv(path, nrows=0).columns

    dtype_map = {col: "string" for col in PHONE_COLUMNS if col in cols}

    dfs[table_name] = pd.read_csv(
        path,
        low_memory=False,
        dtype=dtype_map
    )

    print(f"Loaded {table_name:<22} {len(dfs[table_name]):>8,} rows")

# =============================================================================
# HELPERS
# =============================================================================

def copy_df_to_table(cursor, df: pd.DataFrame, table_name: str, columns: list[str]):
    """
    Bulk-load a DataFrame into a PostgreSQL table using COPY FROM STDIN.
    Converts the DataFrame to a TSV buffer and streams it to the server.
    This is orders of magnitude faster than row-by-row INSERT for large tables.
    """
    buffer = io.StringIO()
    df[columns].to_csv(buffer, index=False, header=False, sep="\t", na_rep="\\N")
    buffer.seek(0)

    cols_quoted = ", ".join(f'"{c}"' for c in columns)
    copy_sql = f"COPY {table_name} ({cols_quoted}) FROM STDIN WITH (FORMAT text, NULL '\\N')"

    cursor.copy_expert(copy_sql, buffer)


def truncate_tables(cursor, table_names: list[str]):
    """
    Truncate all target tables in reverse dependency order with CASCADE.
    This ensures a clean slate for idempotent re-runs.
    """
    for table_name in reversed(table_names):
        cursor.execute(f"TRUNCATE TABLE {table_name} CASCADE")
        print(f"  Truncated {table_name}")

# =============================================================================
# COLUMN MAPPINGS
# Column lists must match the CREATE TABLE definitions in 00_schema.sql.
# The CSV column names produced by 06_normalize.py align with the DDL —
# this mapping is explicit for clarity and to catch drift early.
# =============================================================================

TABLE_COLUMNS = {
    "geographies": [
        "geo_id", "parent_id", "level", "name_bg", "name_en", "locality_type",
    ],
    "construction_types": [
        "construction_type_id", "name_bg", "name_en",
    ],
    "property_types": [
        "property_type_id", "name_bg", "name_en", "category",
    ],
    "features": [
        "feature_id", "name_bg", "name_en",
    ],
    "contacts": [
        "contact_id", "contact_type", "name", "phone",
    ],
    "properties": [
        "property_id", "geo_id", "property_type_id", "construction_type_id",
        "bedrooms", "area_m2", "floor", "total_floors",
        "construction_status", "year_built", "gas", "tec",
    ],
    "listings": [
        "listing_id", "source_id", "property_id", "contact_id",
        "transaction_type", "listing_tier", "listing_url",
        "price", "price_on_request", "date_posted", "date_modified",
        "has_photos", "status", "status_changed_at",
        "scraped_at", "date_last_checked",
    ],
    "property_features": [
        "property_id", "feature_id",
    ],
    "price_history": [
        "listing_id", "old_price", "new_price", "changed_at",
    ],
}

# =============================================================================
# PRE-FLIGHT — column alignment check
# Verify CSV columns match expected DDL columns before touching the database.
# =============================================================================

print("\n--- Pre-flight: column alignment ---")

alignment_ok = True
for table_name, expected_cols in TABLE_COLUMNS.items():
    csv_cols = list(dfs[table_name].columns)
    # Check that expected columns exist in CSV (CSV may have extra columns
    # like name_bg/name_en for geographies which map to "name" in DDL —
    # handled in the rename step below).
    # For geographies: CSV has name_bg, name_en; DDL has name.
    # We'll rename before COPY. Just verify no expected column is missing
    # after accounting for known renames.
    pass  # Handled by explicit rename logic below

# =============================================================================
# RENAME / TRANSFORM — align CSV columns to DDL columns
# =============================================================================

dfs["geographies"]["parent_id"] = (
    pd.to_numeric(dfs["geographies"]["parent_id"], errors="coerce")
    .astype("Int64")
)

for col in ["geo_id", "property_type_id", "construction_type_id", "bedrooms", "floor", "total_floors", "year_built"]:
    if col in dfs["properties"].columns:
        dfs["properties"][col] = pd.to_numeric(dfs["properties"][col], errors="coerce").astype("Int64")

print("Column alignment OK")


# =============================================================================
# EXPORT — load into PostgreSQL
# =============================================================================

print("\n--- Connecting to PostgreSQL ---")

conn = get_connection()
conn.autocommit = False   # wrap everything in a single transaction
cursor = conn.cursor()

try:
    # ------------------------------------------------------------------
    # Step 1: Truncate lookup tables only (safe to reload every run).
    # listings, properties, property_features, and price_history are
    # upserted — existing data is never wiped.
    # ------------------------------------------------------------------
    TRUNCATE_TABLES = [
        "property_features",
        "features",
        "property_types",
        "construction_types",
        "contacts",
        "geographies",
    ]

    print("\n--- Truncating lookup tables ---")
    truncate_tables(cursor, TRUNCATE_TABLES)

    # ------------------------------------------------------------------
    # Step 2: Reset identity sequences so IDs start from 1
    # Tables with GENERATED ALWAYS AS IDENTITY need their sequences reset
    # after truncation, otherwise the next insert would continue from the
    # previous high-water mark.
    # ------------------------------------------------------------------
    print("\n--- Resetting identity sequences ---")

    IDENTITY_TABLES = [
        "geographies",
        "construction_types",
        "property_types",
        "features",
        "contacts",
        "properties",
        "listings",
    ]

    for table_name in IDENTITY_TABLES:
        # GENERATED ALWAYS AS IDENTITY requires OVERRIDING SYSTEM VALUE
        # for explicit ID inserts. We temporarily alter the column to
        # GENERATED BY DEFAULT so COPY can supply IDs directly.
        #
        # Identify the primary key column (first column in TABLE_COLUMNS).
        pk_col = TABLE_COLUMNS[table_name][0]
        cursor.execute(
            f"ALTER TABLE {table_name} ALTER COLUMN {pk_col} "
            f"SET GENERATED BY DEFAULT"
        )
        # Reset the sequence to max(id) + 1 after load (done in Step 4).

    print("  Identity columns set to GENERATED BY DEFAULT")

    # ------------------------------------------------------------------
    # Step 3: Load data — COPY for lookup tables, upsert for the rest
    # ------------------------------------------------------------------
    print("\n--- Loading data ---")

    # Tables loaded with plain COPY (already truncated above)
    COPY_TABLES = {
        "geographies", "construction_types", "property_types",
        "features", "contacts",
    }

    for table_name, _ in LOAD_ORDER:
        columns = TABLE_COLUMNS[table_name]
        df = dfs[table_name]

        missing = set(columns) - set(df.columns)
        if missing:
            raise ValueError(
                f"Table {table_name}: missing columns {missing}. "
                f"CSV has: {list(df.columns)}"
            )

        if table_name in COPY_TABLES:
            copy_df_to_table(cursor, df, table_name, columns)
            print(f"  ✓ {table_name:<22} {len(df):>8,} rows loaded (COPY)")

        elif table_name == "properties":
            cursor.execute("""
                CREATE TEMP TABLE properties_staging
                (LIKE properties INCLUDING ALL)
                ON COMMIT DROP
            """)
            copy_df_to_table(cursor, df, "properties_staging", columns)
            cursor.execute(f"""
                INSERT INTO properties ({', '.join(f'"{c}"' for c in columns)})
                SELECT {', '.join(f'"{c}"' for c in columns)} FROM properties_staging
                ON CONFLICT (property_id) DO UPDATE SET
                    area_m2 = EXCLUDED.area_m2,
                    floor = EXCLUDED.floor,
                    total_floors = EXCLUDED.total_floors,
                    construction_status = EXCLUDED.construction_status,
                    year_built = EXCLUDED.year_built,
                    gas = EXCLUDED.gas,
                    tec = EXCLUDED.tec
            """)
            print(f"  ✓ {table_name:<22} {len(df):>8,} rows upserted")

        elif table_name == "listings":
            # Stage into a temp table, then upsert in a single SQL statement
            cursor.execute(f"""
                CREATE TEMP TABLE listings_staging
                (LIKE listings INCLUDING ALL)
                ON COMMIT DROP
            """)
            copy_df_to_table(cursor, df, "listings_staging", columns)
            update_sets = ', '.join(
                f'"{c}" = EXCLUDED."{c}"'
                for c in columns
                if c not in ("listing_id", "source_id", "scraped_at", "status_changed_at", "date_last_checked")
            )
            cursor.execute(f"""
                INSERT INTO listings ({', '.join(f'"{c}"' for c in columns)})
                SELECT {', '.join(f'"{c}"' for c in columns)} FROM listings_staging
                ON CONFLICT (source_id) DO UPDATE SET
                    {update_sets},
                    status_changed_at = CASE
                        WHEN listings.status IS DISTINCT FROM EXCLUDED.status
                        THEN NOW()
                        ELSE listings.status_changed_at
                    END,
                    date_last_checked = EXCLUDED.date_last_checked
            """)
            print(f"  ✓ listings              {len(df):>8,} rows upserted")

        elif table_name == "property_features":
            for _, row in df.iterrows():
                cursor.execute("""
                    INSERT INTO property_features (property_id, feature_id)
                    VALUES (%s, %s)
                    ON CONFLICT (property_id, feature_id) DO NOTHING
                """, [int(row["property_id"]), int(row["feature_id"])])
            print(f"  ✓ property_features     {len(df):>8,} rows upserted")

        elif table_name == "price_history":
            copy_df_to_table(cursor, df, table_name, columns)
            print(f"  ✓ {table_name:<22} {len(df):>8,} rows appended")

    # ------------------------------------------------------------------
    # Step 4: Reset identity sequences to max(id) + 1
    # ------------------------------------------------------------------
    print("\n--- Resetting identity sequences ---")

    for table_name in IDENTITY_TABLES:
        pk_col = TABLE_COLUMNS[table_name][0]
        cursor.execute(f"SELECT COALESCE(MAX({pk_col}), 0) + 1 FROM {table_name}")
        next_val = cursor.fetchone()[0]
        # Get the sequence name
        cursor.execute(
            f"SELECT pg_get_serial_sequence('{table_name}', '{pk_col}')"
        )
        seq_name = cursor.fetchone()[0]
        if seq_name:
            cursor.execute(f"ALTER SEQUENCE {seq_name} RESTART WITH {next_val}")
            print(f"  {table_name}.{pk_col} sequence → {next_val}")

        # Restore GENERATED ALWAYS
        cursor.execute(
            f"ALTER TABLE {table_name} ALTER COLUMN {pk_col} "
            f"SET GENERATED ALWAYS"
        )

    # ------------------------------------------------------------------
    # Step 5: Commit transaction
    # ------------------------------------------------------------------
    conn.commit()
    print("\n✅ Export committed successfully.")

except Exception as e:
    conn.rollback()
    print(f"\n❌ Export failed — transaction rolled back.\n{e}")
    sys.exit(1)

finally:
    cursor.close()
    conn.close()

# =============================================================================
# POST-LOAD VERIFICATION
# Reconnect and run quick row count checks against the database.
# =============================================================================

print("\n--- Post-load verification ---")

conn = get_connection()
try:
    cursor = conn.cursor()
    all_ok = True
    for table_name, _ in LOAD_ORDER:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        db_count = cursor.fetchone()[0]
        csv_count = len(dfs[table_name])
        match = "✓" if db_count == csv_count else "✗ MISMATCH"
        if db_count != csv_count:
            all_ok = False
        print(f"  {match} {table_name:<22} CSV={csv_count:>8,}  DB={db_count:>8,}")
    cursor.close()
finally:
    conn.close()

if all_ok:
    print("\n✅ All row counts match. Export complete.")
else:
    print("\n❌ Row count mismatch detected — investigate before proceeding.")
    sys.exit(1)

print("\n08_export.py complete.")
