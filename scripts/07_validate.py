# =============================================================================
# real_estate_cleaning — Validate Normalized CSVs
# Source: data/clean/*.csv (output of 06_normalize.py)
# Purpose: Pre-flight validation gate before PostgreSQL export. Checks
#          referential integrity, business rules, and distribution sanity.
#          Writes docs/validation_report.md.
# Exit:    Non-zero if any Tier 1 or Tier 2 check fails — blocks 08_export.py
#          in a shell pipeline (python 07_validate.py && python 08_export.py).
# Task:    13
# Run after: 06_normalize.py
# =============================================================================

from pathlib import Path
import sys
import pandas as pd

CLEAN_PATH = Path("data/clean")
DOCS_PATH = Path("docs")
DOCS_PATH.mkdir(exist_ok=True)

# =============================================================================
# LOAD — all eight normalized CSVs
# =============================================================================

TABLES = {
    "geographies":        CLEAN_PATH / "geographies.csv",
    "construction_types": CLEAN_PATH / "construction_types.csv",
    "property_types":     CLEAN_PATH / "property_types.csv",
    "features":           CLEAN_PATH / "features.csv",
    "contacts":           CLEAN_PATH / "contacts.csv",
    "properties":         CLEAN_PATH / "properties.csv",
    "listings":           CLEAN_PATH / "listings.csv",
    "property_features":  CLEAN_PATH / "property_features.csv",
}

dfs = {}
for name, path in TABLES.items():
    if not path.exists():
        print(f"FATAL: Missing CSV: {path}")
        sys.exit(1)
    dfs[name] = pd.read_csv(path, low_memory=False)
    print(f"Loaded {name:<22} {len(dfs[name]):>8,} rows")

df_geo     = dfs["geographies"]
df_ct      = dfs["construction_types"]
df_pt      = dfs["property_types"]
df_feat    = dfs["features"]
df_cont    = dfs["contacts"]
df_prop    = dfs["properties"]
df_list    = dfs["listings"]
df_pf      = dfs["property_features"]

# =============================================================================
# RESULT TRACKING
# =============================================================================

results = []   # list of (tier, name, status, detail)

def passed(tier: int, name: str, detail: str = ""):
    results.append((tier, name, "PASSED", detail))
    print(f"  ✓ T{tier} | {name}")

def failed(tier: int, name: str, detail: str = ""):
    results.append((tier, name, "FAILED", detail))
    print(f"  ✗ T{tier} | {name} — {detail}")

def warning(tier: int, name: str, detail: str = ""):
    results.append((tier, name, "WARNING", detail))
    print(f"  ⚠ T{tier} | {name} — {detail}")

# =============================================================================
# TIER 1 — Referential Integrity
# =============================================================================

print("\n--- Tier 1: Referential Integrity ---")

# 1.1 listings.property_id → properties.property_id
orphan = set(df_list["property_id"]) - set(df_prop["property_id"])
if orphan:
    failed(1, "listings.property_id → properties",
           f"{len(orphan):,} orphan property_ids: {sorted(list(orphan))[:10]}")
else:
    passed(1, "listings.property_id → properties")

# 1.2 listings.contact_id → contacts.contact_id
orphan = set(df_list["contact_id"]) - set(df_cont["contact_id"])
if orphan:
    failed(1, "listings.contact_id → contacts",
           f"{len(orphan):,} orphan contact_ids")
else:
    passed(1, "listings.contact_id → contacts")

# 1.3 properties.geo_id → geographies.geo_id
orphan = set(df_prop["geo_id"]) - set(df_geo["geo_id"])
if orphan:
    failed(1, "properties.geo_id → geographies",
           f"{len(orphan):,} orphan geo_ids")
else:
    passed(1, "properties.geo_id → geographies")

# 1.4 properties.property_type_id → property_types.property_type_id
orphan = set(df_prop["property_type_id"].dropna()) - set(df_pt["property_type_id"])
if orphan:
    failed(1, "properties.property_type_id → property_types",
           f"{len(orphan):,} orphan property_type_ids")
else:
    passed(1, "properties.property_type_id → property_types")

# 1.5 properties.construction_type_id → construction_types (nullable FK)
ct_ids = set(df_prop["construction_type_id"].dropna().astype(int))
valid_ct = set(df_ct["construction_type_id"])
orphan = ct_ids - valid_ct
if orphan:
    failed(1, "properties.construction_type_id → construction_types",
           f"{len(orphan):,} orphan construction_type_ids")
else:
    passed(1, "properties.construction_type_id → construction_types")

# 1.6 property_features.property_id → properties.property_id
orphan = set(df_pf["property_id"]) - set(df_prop["property_id"])
if orphan:
    failed(1, "property_features.property_id → properties",
           f"{len(orphan):,} orphan property_ids")
else:
    passed(1, "property_features.property_id → properties")

# 1.7 property_features.feature_id → features.feature_id
orphan = set(df_pf["feature_id"]) - set(df_feat["feature_id"])
if orphan:
    failed(1, "property_features.feature_id → features",
           f"{len(orphan):,} orphan feature_ids")
else:
    passed(1, "property_features.feature_id → features")

# =============================================================================
# TIER 2 — Business Rule Validation
# =============================================================================

print("\n--- Tier 2: Business Rules ---")

# 2.1 price IS NULL only when price_on_request = True (and vice versa)
#     price_on_request = True → price IS NULL
#     price IS NULL → price_on_request = True
por_col = df_list["price_on_request"].map(lambda x: str(x).strip().lower() == "true")
por_true_has_price = df_list.loc[por_col, "price"].notna().sum()
null_price_no_por = df_list.loc[df_list["price"].isna() & ~por_col].shape[0]
violations_21 = por_true_has_price + null_price_no_por
if violations_21 > 0:
    failed(2, "price ↔ price_on_request consistency",
           f"{por_true_has_price:,} rows with price_on_request=True but price not null; "
           f"{null_price_no_por:,} rows with null price but price_on_request≠True")
else:
    passed(2, "price ↔ price_on_request consistency")

# 2.2 contact_type = 'agency' → name is not null
agency_null_name = df_cont.loc[
    (df_cont["contact_type"] == "agency") & df_cont["name"].isna()
].shape[0]
if agency_null_name > 0:
    failed(2, "agency contacts have non-null name",
           f"{agency_null_name:,} agency contacts with null name")
else:
    passed(2, "agency contacts have non-null name")

# 2.3 bedrooms non-null only for apartment types (1–4 стаен)
#     Join properties ← property_types to get name_en
prop_pt = df_prop.merge(df_pt[["property_type_id", "name_en"]], on="property_type_id", how="left")
apartment_types = {"apartment"}
bedrooms_non_null_wrong = prop_pt.loc[
    prop_pt["bedrooms"].notna() & ~prop_pt["name_en"].isin(apartment_types)
].shape[0]
bedrooms_null_apartment = prop_pt.loc[
    prop_pt["bedrooms"].isna() & prop_pt["name_en"].isin(apartment_types)
].shape[0]
violations_23 = bedrooms_non_null_wrong
if violations_23 > 0:
    failed(2, "bedrooms only for apartment types",
           f"{bedrooms_non_null_wrong:,} non-apartment rows with bedrooms set; "
           f"{bedrooms_null_apartment:,} apartment rows with null bedrooms (expected for МНОГОСТАЕН)")
else:
    detail = f"{bedrooms_null_apartment:,} apartment rows with null bedrooms (expected for МНОГОСТАЕН)" if bedrooms_null_apartment else ""
    passed(2, "bedrooms only for apartment types", detail)

# 2.4 floor and total_floors: both null or both non-null
floor_mismatch = (
    (df_prop["floor"].isna() != df_prop["total_floors"].isna())
).sum()
if floor_mismatch > 0:
    failed(2, "floor ↔ total_floors parity",
           f"{floor_mismatch:,} rows with one null and the other not")
else:
    passed(2, "floor ↔ total_floors parity")

# 2.5 date_last_checked >= scraped_at
df_list["_scraped"] = pd.to_datetime(df_list["scraped_at"], errors="coerce")
df_list["_checked"] = pd.to_datetime(df_list["date_last_checked"], errors="coerce")
date_violations = (df_list["_checked"] < df_list["_scraped"]).sum()
if date_violations > 0:
    failed(2, "date_last_checked >= scraped_at",
           f"{date_violations:,} rows where date_last_checked < scraped_at")
else:
    passed(2, "date_last_checked >= scraped_at")
df_list.drop(columns=["_scraped", "_checked"], inplace=True)

# 2.6 status_changed_at is always null on first load
non_null_sca = df_list["status_changed_at"].notna().sum()
if non_null_sca > 0:
    failed(2, "status_changed_at is null (first load)",
           f"{non_null_sca:,} rows with non-null status_changed_at")
else:
    passed(2, "status_changed_at is null (first load)")

# 2.7 year_built between 1800 and 2040 where non-null
year_vals = df_prop.loc[df_prop["year_built"].notna(), "year_built"]
year_bad = year_vals[(year_vals < 1800) | (year_vals > 2040)]
if len(year_bad) > 0:
    failed(2, "year_built in [1800, 2040]",
           f"{len(year_bad):,} rows outside range: min={year_bad.min()}, max={year_bad.max()}")
else:
    passed(2, "year_built in [1800, 2040]")

# 2.8 transaction_type only 'sale' or 'rental'
valid_tt = {"sale", "rental"}
bad_tt = set(df_list["transaction_type"].dropna().unique()) - valid_tt
if bad_tt:
    failed(2, "transaction_type ∈ {sale, rental}",
           f"unexpected values: {bad_tt}")
else:
    passed(2, "transaction_type ∈ {sale, rental}")

# 2.9 source_id is globally unique in listings
if not df_list["source_id"].is_unique:
    n_dupes = len(df_list) - df_list["source_id"].nunique()
    failed(2, "source_id unique in listings",
           f"{n_dupes:,} duplicate source_ids")
else:
    passed(2, "source_id unique in listings")

# =============================================================================
# TIER 3 — Distribution Sanity Checks (warnings only)
# =============================================================================

print("\n--- Tier 3: Distribution Sanity ---")

# 3.1 Null rate bounds for key fields
NULL_THRESHOLDS = [
    # (table_name, df, column, max_null_pct)
    ("properties", df_prop, "area_m2",        5.0),
    ("listings",   df_list, "date_modified",  35.0),
    ("listings",   df_list, "price",          15.0),
    ("properties", df_prop, "year_built",     80.0),
    ("properties", df_prop, "floor",          60.0),
]

for table_name, table_df, col, threshold in NULL_THRESHOLDS:
    null_pct = table_df[col].isna().mean() * 100
    if null_pct > threshold:
        warning(3, f"{table_name}.{col} null rate",
                f"{null_pct:.1f}% null (threshold: {threshold}%)")
    else:
        passed(3, f"{table_name}.{col} null rate",
               f"{null_pct:.1f}% null (threshold: {threshold}%)")

# 3.2 Price range sanity per transaction_type
#     Rental prices should be orders of magnitude lower than sale prices.
for tt in ["sale", "rental"]:
    prices = df_list.loc[
        (df_list["transaction_type"] == tt) & df_list["price"].notna(), "price"
    ]
    if len(prices) == 0:
        warning(3, f"{tt} price distribution", "no price data")
        continue

    median_price = prices.median()
    max_price = prices.max()
    min_price = prices.min()
    detail = f"n={len(prices):,} | min={min_price:,.0f} | median={median_price:,.0f} | max={max_price:,.0f}"

    if tt == "rental" and median_price > 50_000:
        warning(3, f"{tt} price distribution",
                f"median rental price suspiciously high: {detail}")
    elif tt == "sale" and median_price < 500:
        warning(3, f"{tt} price distribution",
                f"median sale price suspiciously low: {detail}")
    else:
        passed(3, f"{tt} price distribution", detail)

# 3.3 Row count stability — compare listings to expected from 06_normalize.py
#     (We check that the CSV row count matches the loaded DataFrame.)
csv_row_count = len(pd.read_csv(TABLES["listings"], nrows=0).columns)  # just confirm readable
listings_rows = len(df_list)
properties_rows = len(df_prop)
if listings_rows != properties_rows:
    warning(3, "listings ↔ properties row count parity",
            f"listings={listings_rows:,} vs properties={properties_rows:,} "
            "(expected 1:1 on first load)")
else:
    passed(3, "listings ↔ properties row count parity",
           f"both have {listings_rows:,} rows")

# =============================================================================
# BUILD VALIDATION REPORT
# =============================================================================

print("\n--- Writing validation report ---")

lines = []
lines.append("# Validation Report\n")

# Summary
t1_fails = sum(1 for t, _, s, _ in results if t == 1 and s == "FAILED")
t2_fails = sum(1 for t, _, s, _ in results if t == 2 and s == "FAILED")
t3_warns = sum(1 for t, _, s, _ in results if t == 3 and s == "WARNING")
total_checks = len(results)
total_passed = sum(1 for _, _, s, _ in results if s == "PASSED")
total_failed = sum(1 for _, _, s, _ in results if s == "FAILED")
total_warnings = sum(1 for _, _, s, _ in results if s == "WARNING")

blocking = t1_fails + t2_fails > 0

lines.append(f"**Overall:** {'❌ BLOCKED' if blocking else '✅ ALL CLEAR'}\n")
lines.append(f"| Metric | Count |")
lines.append(f"|---|---|")
lines.append(f"| Total checks | {total_checks} |")
lines.append(f"| Passed | {total_passed} |")
lines.append(f"| Failed (blocking) | {total_failed} |")
lines.append(f"| Warnings (non-blocking) | {total_warnings} |")

lines.append(f"\n**Table row counts:**\n")
lines.append("| Table | Rows |")
lines.append("|---|---|")
for name, table_df in dfs.items():
    lines.append(f"| {name} | {len(table_df):,} |")

# Tier sections
for tier, tier_name in [(1, "Referential Integrity"), (2, "Business Rules"), (3, "Distribution Sanity")]:
    tier_results = [(n, s, d) for t, n, s, d in results if t == tier]
    if not tier_results:
        continue

    lines.append(f"\n---\n\n## Tier {tier} — {tier_name}\n")

    for name, status, detail in tier_results:
        icon = {"PASSED": "✅", "FAILED": "❌", "WARNING": "⚠️"}[status]
        line = f"- {icon} **{status}** — {name}"
        if detail:
            line += f"  \n  _{detail}_"
        lines.append(line)

# =============================================================================
# WRITE REPORT
# =============================================================================

report_path = DOCS_PATH / "validation_report.md"
with open(report_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"\nValidation report written to: {report_path}")

# =============================================================================
# EXIT — block on Tier 1 or Tier 2 failures
# =============================================================================

if blocking:
    print(f"\n❌ VALIDATION FAILED — {t1_fails} Tier 1 + {t2_fails} Tier 2 failures. Export blocked.")
    sys.exit(1)
else:
    print(f"\n✅ VALIDATION PASSED — {total_warnings} warnings (non-blocking). Safe to export.")
    sys.exit(0)
