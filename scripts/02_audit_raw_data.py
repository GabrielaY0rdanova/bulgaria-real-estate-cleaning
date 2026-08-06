# =============================================================================
# real_estate_cleaning — Audit Raw Data
# Source: imot.bg scraper output (prodazhbi + naemi CSVs)
# Purpose: Audit combined staging DataFrame — null rates, value distributions,
#          dtype check. Output saved to docs/audit_report.md.
# Task:    2
# Run after: 01_ingest.py
# =============================================================================

from pathlib import Path
import pandas as pd

# =============================================================================
# LOAD — replicate ingest to produce df_staging
# =============================================================================

DATA_PATH = Path("data/raw")
DOCS_PATH = Path("docs")
DOCS_PATH.mkdir(exist_ok=True)

prodazhbi_files = list(DATA_PATH.glob("prodazhbi_*.csv"))
naemi_files = list(DATA_PATH.glob("naemi_*.csv"))

if len(prodazhbi_files) == 0:
    raise FileNotFoundError("No prodazhbi CSV found in data/raw/")
if len(naemi_files) == 0:
    raise FileNotFoundError("No naemi CSV found in data/raw/")
prodazhbi_files = [max(prodazhbi_files, key=lambda p: p.stat().st_mtime)]
naemi_files = [max(naemi_files, key=lambda p: p.stat().st_mtime)]

df_prod = pd.read_csv(prodazhbi_files[0], low_memory=False)
df_naem = pd.read_csv(naemi_files[0], low_memory=False)

# transaction_type already exists in the CSVs — normalize to sale/rental
df_prod["transaction_type"] = "sale"
df_naem["transaction_type"] = "rental"

df_staging = pd.concat([df_prod, df_naem], ignore_index=True)

# Drop rows where the scraper failed to extract data (property_type == "unknown").
unknown_mask = df_staging["property_type"] == "unknown"
if unknown_mask.any():
    print(f"Dropping {unknown_mask.sum():,} rows with property_type == 'unknown' (failed scrapes)")
    df_staging = df_staging[~unknown_mask].reset_index(drop=True)

print(f"Staging rows: {len(df_staging):,}  |  prodazhbi: {len(df_prod):,}  |  naemi: {len(df_naem):,}")

# =============================================================================
# HELPERS
# =============================================================================

def null_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return null count and null % for every column, sorted descending."""
    null_counts = df.isnull().sum()
    null_pct = (null_counts / len(df) * 100).round(1)
    summary = pd.DataFrame({"null_count": null_counts, "null_pct": null_pct})
    return summary.sort_values("null_pct", ascending=False)


def value_counts_block(series: pd.Series, top_n: int = None) -> str:
    """
    Return a markdown table of value counts for a Series.
    top_n=None means show all values (used for low-cardinality fields).
    """
    vc = series.value_counts(dropna=False)
    total = len(series)

    if top_n:
        vc = vc.head(top_n)

    lines = ["| Value | Count | % |", "|---|---|---|"]
    for val, count in vc.items():
        pct = round(count / total * 100, 1)
        display_val = "(null)" if pd.isna(val) else str(val)
        lines.append(f"| {display_val} | {count:,} | {pct} |")

    return "\n".join(lines)


def section(title: str) -> str:
    return f"\n---\n\n## {title}\n"


def subsection(title: str) -> str:
    return f"\n### {title}\n"

# =============================================================================
# BUILD REPORT
# =============================================================================

lines = []

# -----------------------------------------------------------------------------
# Header
# -----------------------------------------------------------------------------
lines.append("# Audit Report — Raw Staging Data")
lines.append(f"\n**Source files:** `{prodazhbi_files[0].name}` + `{naemi_files[0].name}`")
lines.append(f"**Total rows:** {len(df_staging):,} ({len(df_prod):,} sales + {len(df_naem):,} rentals)  ")
lines.append(f"**Total columns:** {len(df_staging.columns)}")

# -----------------------------------------------------------------------------
# Section 1 — Dtypes
# -----------------------------------------------------------------------------
lines.append(section("1. Column Dtypes"))
lines.append("| Column | Dtype |")
lines.append("|---|---|")
for col, dtype in df_staging.dtypes.items():
    lines.append(f"| {col} | {dtype} |")

# -----------------------------------------------------------------------------
# Section 2 — Null rates (all columns)
# -----------------------------------------------------------------------------
lines.append(section("2. Null Rates (all columns)"))
ns = null_summary(df_staging)
lines.append("| Column | Null Count | Null % |")
lines.append("|---|---|---|")
for col, row in ns.iterrows():
    lines.append(f"| {col} | {int(row['null_count']):,} | {row['null_pct']} |")

# -----------------------------------------------------------------------------
# Section 3 — Identifiers
# -----------------------------------------------------------------------------
lines.append(section("3. Identifiers"))

lines.append(subsection("source_id"))
n_unique = df_staging["source_id"].nunique()
n_dupes = len(df_staging) - n_unique
lines.append("| Metric | Value |")
lines.append("|---|---|")
lines.append(f"| Unique values | {n_unique:,} |")
lines.append(f"| Duplicate source_ids | {n_dupes:,} |")

lines.append(subsection("transaction_type"))
lines.append(value_counts_block(df_staging["transaction_type"]))

lines.append(subsection("status"))
lines.append(value_counts_block(df_staging["status"]))

lines.append(subsection("listing_tier"))
lines.append(value_counts_block(df_staging["listing_tier"]))

lines.append(subsection("listing_url — sample"))
lines.append("```")
for url in df_staging["listing_url"].dropna().head(3):
    lines.append(str(url))
lines.append("```")

lines.append(subsection("scraped_at — range"))
lines.append(f"- Min: `{df_staging['scraped_at'].dropna().min()}`")
lines.append(f"- Max: `{df_staging['scraped_at'].dropna().max()}`")
lines.append(f"- Unique dates: {df_staging['scraped_at'].nunique():,}")

# -----------------------------------------------------------------------------
# Section 4 — Geography
# Note: country and has_phone columns do not exist in raw data — not audited.
# -----------------------------------------------------------------------------
lines.append(section("4. Geography"))

lines.append(subsection("region — top 20"))
lines.append(value_counts_block(df_staging["region"], top_n=20))

lines.append(subsection("locality_type"))
lines.append(value_counts_block(df_staging["locality_type"]))

lines.append(subsection("locality — top 20"))
lines.append(value_counts_block(df_staging["locality"], top_n=20))

lines.append(subsection("area — top 20 (locality + area)"))
lines.append(f"- Non-null rows: {df_staging['area'].notna().sum():,}")
lines.append("")
nb_with_loc = (
    df_staging[df_staging["area"].notna()]
    .assign(loc_nb=lambda d: d["locality"] + " / " + d["area"])
)
lines.append(value_counts_block(nb_with_loc["loc_nb"], top_n=20))

lines.append(subsection("Localities with area data"))
lines.append("Area is populated only for city-level listings:")
nb_by_locality = (
    df_staging[df_staging["area"].notna()]
    .groupby("locality")
    .size()
    .sort_values(ascending=False)
)
lines.append("")
lines.append("| Locality | Rows with area |")
lines.append("|---|---|")
for loc, cnt in nb_by_locality.items():
    lines.append(f"| {loc} | {cnt:,} |")

lines.append(subsection("Geographic hierarchy — samples"))

lines.append("**Region-level** (area is null — smaller cities/villages):")
lines.append("```")
geo_region = (
    df_staging[df_staging["area"].isna()][["region", "locality", "locality_type"]]
    .drop_duplicates()
    .head(10)
    .to_string(index=False)
)
lines.append(geo_region)
lines.append("```")

lines.append("\n**City-level** (area populated):")
lines.append("```")
geo_city = (
    df_staging[df_staging["area"].notna()][["region", "locality", "area"]]
    .drop_duplicates()
    .head(10)
    .to_string(index=False)
)
lines.append(geo_city)
lines.append("```")

# -----------------------------------------------------------------------------
# Section 5 — Property characteristics
# -----------------------------------------------------------------------------
lines.append(section("5. Property Characteristics"))

lines.append(subsection("property_type"))
lines.append(value_counts_block(df_staging["property_type"]))

lines.append(subsection("bedrooms"))
bedrooms_non_null = df_staging["bedrooms"].notna().sum()
if bedrooms_non_null == 0:
    lines.append("> All values null — bedrooms will be extracted from `property_type` during cleaning.")
else:
    lines.append(f"- Non-null rows: {bedrooms_non_null:,}")
    lines.append(value_counts_block(df_staging["bedrooms"]))

lines.append(subsection("area_m2"))
area = df_staging["area_m2"].dropna()
lines.append(f"- Non-null rows: {len(area):,}")
lines.append(f"- Min: {area.min()}")
lines.append(f"- Max: {area.max()}")
lines.append(f"- Mean: {area.mean():.1f}")
lines.append(f"- Median: {area.median():.1f}")
lines.append(f"- Rows where area_m2 = 0: {(area == 0).sum():,}")

lines.append(subsection("floor — raw values (top 30)"))
lines.append(value_counts_block(df_staging["floor"], top_n=30))

lines.append(subsection("construction_type"))
lines.append(value_counts_block(df_staging["construction_type"]))

lines.append(subsection("construction_status"))
lines.append(value_counts_block(df_staging["construction_status"]))

lines.append(subsection("year_built"))
yb = df_staging["year_built"].dropna()
lines.append(f"- Non-null rows: {len(yb):,}")
if len(yb) > 0:
    lines.append(f"- Min: {yb.min()}")
    lines.append(f"- Max: {yb.max()}")
    lines.append(f"- Values outside plausible range (< 1800 or > 2030): {((yb < 1800) | (yb > 2030)).sum():,}")

lines.append(subsection("gas"))
lines.append(value_counts_block(df_staging["gas"]))

lines.append(subsection("tec"))
lines.append(value_counts_block(df_staging["tec"]))

lines.append(subsection("features — top 10 raw strings"))
lines.append("Raw comma-separated strings — shown before parsing:")
lines.append(value_counts_block(df_staging["features"], top_n=10))

lines.append(subsection("features — individual value counts"))
lines.append("Parsed from comma-separated strings:")
feature_series = (
    df_staging["features"]
    .dropna()
    .str.split(", ")
    .explode()
    .str.strip()
)
lines.append(value_counts_block(feature_series))

# -----------------------------------------------------------------------------
# Section 6 — Listing details
# -----------------------------------------------------------------------------
lines.append(section("6. Listing Details"))

lines.append(subsection("price — raw value samples"))
price_raw = df_staging["price"]
lines.append(f"- Non-null rows: {price_raw.notna().sum():,}")
lines.append(f"- Null rows: {price_raw.isna().sum():,}")

# "Цена при запитване" rows
price_on_request_mask = price_raw.astype(str).str.contains("запитване", na=False)
lines.append(f"- 'Цена при запитване' rows: {price_on_request_mask.sum():,}")

# $ rows
dollar_mask = price_raw.astype(str).str.contains(r"\$", na=False)
lines.append(f"- Rows with $ currency: {dollar_mask.sum():,}")

lines.append("\nSample raw price values (first 10 non-null):")
lines.append("```")
for val in price_raw.dropna().head(10):
    lines.append(str(val))
lines.append("```")

lines.append(subsection("price — by transaction_type"))
lines.append("| transaction_type | total | null | on request | $ |")
lines.append("|---|---|---|---|---|")
for tx_type in ["sale", "rental"]:
    subset = df_staging[df_staging["transaction_type"] == tx_type]["price"]
    on_request = subset.astype(str).str.contains("запитване", na=False).sum()
    dollar = subset.astype(str).str.contains(r"\$", na=False).sum()
    null = subset.isna().sum()
    lines.append(f"| {tx_type} | {len(subset):,} | {null:,} | {on_request:,} | {dollar:,} |")

lines.append(subsection("date_posted — sample raw values"))
dp = df_staging["date_posted"].dropna()
lines.append(f"- Non-null rows: {len(dp):,}")
lines.append(f"- Null rows: {df_staging['date_posted'].isna().sum():,}")
lines.append("\nSample raw strings:")
lines.append("```")
for val in dp.head(5):
    lines.append(str(val))
lines.append("```")

lines.append(subsection("date_modified — sample raw values"))
dm = df_staging["date_modified"].dropna()
lines.append(f"- Non-null rows: {len(dm):,}")
lines.append(f"- Null rows: {df_staging['date_modified'].isna().sum():,}")
lines.append("\nSample raw strings:")
lines.append("```")
for val in dm.head(5):
    lines.append(str(val))
lines.append("```")

lines.append(subsection("has_photos"))
lines.append(value_counts_block(df_staging["has_photos"]))

# -----------------------------------------------------------------------------
# Section 7 — Poster / Agency
# -----------------------------------------------------------------------------
lines.append(section("7. Poster / Agency"))

lines.append(subsection("poster_type"))
lines.append(value_counts_block(df_staging["poster_type"]))

lines.append(subsection("agency_name — top 20"))
lines.append(f"- Non-null rows: {df_staging['agency_name'].notna().sum():,}")
lines.append("")
lines.append(value_counts_block(df_staging["agency_name"], top_n=20))

lines.append(subsection("agency_phone — dtype and samples"))
lines.append(f"- Dtype: `{df_staging['agency_phone'].dtype}`")
lines.append(f"- Non-null rows: {df_staging['agency_phone'].notna().sum():,}")
lines.append("\nSample raw values (first 5 non-null):")
lines.append("```")
for val in df_staging["agency_phone"].dropna().head(5):
    lines.append(str(val))
lines.append("```")

# NOTE: has_phone column does not exist in raw data — removed from audit

# -----------------------------------------------------------------------------
# Section 8 — Encoding check
# -----------------------------------------------------------------------------
lines.append(section("8. Encoding Check"))
lines.append("Sample Bulgarian text from key fields — verify no mojibake or garbled characters:\n")

for col in ["property_type", "construction_type", "features", "tec", "gas", "region"]:
    sample_vals = df_staging[col].dropna().unique()[:3]
    lines.append(f"**{col}:** {' | '.join(str(v) for v in sample_vals)}")
    lines.append("")

# =============================================================================
# WRITE REPORT
# =============================================================================

report_path = DOCS_PATH / "audit_report.md"
report_content = "\n".join(lines)

with open(report_path, "w", encoding="utf-8") as f:
    f.write(report_content)

print(f"\nAudit report written to: {report_path}")