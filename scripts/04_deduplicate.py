# =============================================================================
# real_estate_cleaning — Deduplicate
# Source: df_clean.pkl (output of 03_clean_fields.py)
# Purpose: Deduplicate listings by source_id, keeping the row with the latest
#          scraped_at. Populates date_last_checked. Sets status_changed_at to
#          NULL (first load — no status flip has occurred yet).
# Task:    10
# Run after: 03_clean_fields.py
# =============================================================================

from pathlib import Path
import pandas as pd

CLEAN_PATH = Path("data/clean")

# =============================================================================
# LOAD
# =============================================================================

df = pd.read_pickle(CLEAN_PATH / "df_clean.pkl")

print(f"Loaded: {len(df):,} rows | {df['source_id'].nunique():,} unique source_ids")

# =============================================================================
# AUDIT — duplicates before dedup
# =============================================================================

n_dupes = len(df) - df["source_id"].nunique()
dupe_mask = df.duplicated(subset=["source_id"], keep=False)
dupe_groups = df[dupe_mask].groupby("source_id")

print(f"\nDuplicate source_ids: {n_dupes:,} extra rows across {dupe_groups.ngroups:,} groups")

# Classify groups: identical-except-scraped_at vs meaningful differences
check_cols = [c for c in df.columns if c != "scraped_at"]

identical_count = 0
meaningful_count = 0
meaningful_ids = []

for sid, group in dupe_groups:
    if group[check_cols].nunique().max() == 1:
        identical_count += 1
    else:
        meaningful_count += 1
        meaningful_ids.append(sid)

print(f"  Identical except scraped_at: {identical_count:,}")
print(f"  Meaningful differences:      {meaningful_count:,}")

if meaningful_ids:
    print("\n  Meaningful duplicate groups (fields that differ):")
    for sid in meaningful_ids:
        group = df[df["source_id"] == sid]
        diff_cols = [c for c in check_cols if group[c].nunique() > 1]
        print(f"    source_id={sid} | diff cols: {diff_cols}")

# =============================================================================
# DEDUPLICATE — keep row with latest scraped_at per source_id
# =============================================================================

# date_last_checked = scraped_at of the latest row in the group (same as the
# row we keep, since we sort descending and take first)
df = df.sort_values("scraped_at", ascending=False)
df_dedup = df.drop_duplicates(subset=["source_id"], keep="first").copy()

# Rename scraped_at → date_last_checked to reflect its role in the schema
# The original scraped_at is preserved as-is (it is the scraped_at of the
# kept row, which is also the latest scraped_at in the group)
df_dedup["date_last_checked"] = df_dedup["scraped_at"]

# status_changed_at — NULL on first load.
# Populated only when a listing transitions active ↔ inactive in future runs.
df_dedup["status_changed_at"] = pd.NaT

print(f"\nAfter dedup: {len(df_dedup):,} rows")
print(f"Rows removed: {len(df) - len(df_dedup):,}")

# Sanity check — should be zero
remaining_dupes = df_dedup["source_id"].duplicated().sum()
if remaining_dupes > 0:
    raise ValueError(f"Dedup failed — {remaining_dupes} duplicate source_ids remain")
print("Dedup sanity check passed — zero duplicate source_ids remain")

# =============================================================================
# AUDIT — post-dedup shape
# =============================================================================

print(f"\n=== POST-DEDUP SUMMARY ===")
print(f"Shape: {df_dedup.shape}")
print(f"\ntransaction_type:\n{df_dedup['transaction_type'].value_counts()}")
print(f"\nstatus:\n{df_dedup['status'].value_counts(dropna=False)}")
print(f"\nscraped_at range: {df_dedup['scraped_at'].min()} → {df_dedup['scraped_at'].max()}")
print(f"date_last_checked range: {df_dedup['date_last_checked'].min()} → {df_dedup['date_last_checked'].max()}")
print(f"status_changed_at nulls: {df_dedup['status_changed_at'].isna().sum():,} (expected: {len(df_dedup):,})")

# =============================================================================
# SAVE
# =============================================================================

output_path = CLEAN_PATH / "df_dedup.pkl"
df_dedup.to_pickle(output_path)

print(f"\ndf_dedup saved to: {output_path}")
print(f"Columns: {list(df_dedup.columns)}")
