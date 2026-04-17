# =============================================================================
# real_estate_cleaning — Ingest
# Source: imot.bg scraper output (prodazhbi + naemi CSVs)
# Purpose: Load, validate, and combine raw CSVs into a single staging DataFrame
# Task:    1
# Run after: (none — this is the pipeline entry point)
# Output:  none — downstream scripts reload from raw CSVs directly
# =============================================================================

from pathlib import Path
import pandas as pd

DATA_PATH = Path("data/raw")

# Glob for files — date suffix varies per scraper run
prodazhbi_files = list(DATA_PATH.glob("prodazhbi_*.csv"))
naemi_files = list(DATA_PATH.glob("naemi_*.csv"))

# Validate exactly one file exists for each type
if len(prodazhbi_files) == 0:
    raise FileNotFoundError("No prodazhbi CSV found in data/raw/")
if len(prodazhbi_files) > 1:
    raise ValueError(f"Multiple prodazhbi CSVs found: {prodazhbi_files}")

if len(naemi_files) == 0:
    raise FileNotFoundError("No naemi CSV found in data/raw/")
if len(naemi_files) > 1:
    raise ValueError(f"Multiple naemi CSVs found: {naemi_files}")

# Only agency_phone is present in the raw CSVs — the others are listed here
# defensively in case future scraper versions add them. pandas silently
# ignores dtype overrides for columns that don't exist.
PHONE_COLUMNS = ["agency_phone", "phone", "contact_phone"]

df_prod = pd.read_csv(
    prodazhbi_files[0],
    low_memory=False,
    dtype={col: "string" for col in PHONE_COLUMNS}
)

df_naem = pd.read_csv(
    naemi_files[0],
    low_memory=False,
    dtype={col: "string" for col in PHONE_COLUMNS}
)

print(f"Prodazhbi rows (sales): {len(df_prod)}")
print(f"Naemi rows (rentals): {len(df_naem)}")

if len(df_prod) == 0:
    raise ValueError("Prodazhbi dataset is empty")

if len(df_naem) == 0:
    raise ValueError("Naemi dataset is empty")

# Tag transaction type before combining
df_prod["transaction_type"] = "sale"
df_naem["transaction_type"] = "rental"

df_staging = pd.concat([df_prod, df_naem], ignore_index=True)

df_staging["agency_phone"] = df_staging["agency_phone"].astype("string")


# Sanity check — concat should never drop or duplicate rows
expected_rows = len(df_prod) + len(df_naem)
actual_rows = len(df_staging)

print(f"Total rows after merge: {actual_rows}")

if actual_rows != expected_rows:
    raise ValueError("Row count mismatch after concatenation")

print(df_staging.info())
print(df_staging.head())