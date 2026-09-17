# =============================================================================
# real_estate_cleaning — Flag Outliers
# Source: df_dedup.pkl (output of 04_deduplicate.py)
# Purpose: Identify statistical outliers in price, area_m2, and year_built.
#          Adds boolean flag columns — does NOT remove any rows.
#          Outlier decisions (keep/investigate/drop) belong in analysis.
# Task:    11
# Run after: 04_deduplicate.py
# =============================================================================

from pathlib import Path
import sys
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.outliers import add_outlier_flags

CLEAN_PATH = Path("data/clean")
DOCS_PATH = Path("docs")
DOCS_PATH.mkdir(exist_ok=True)

# =============================================================================
# LOAD
# =============================================================================

df = pd.read_pickle(CLEAN_PATH / "df_dedup.pkl")

print(f"Loaded: {len(df):,} rows")

# =============================================================================
# FLAG — shared, market-aware rules
# =============================================================================

YEAR_MIN = 1800
YEAR_MAX_HARD = 2040
CURRENT_YEAR = pd.Timestamp.now().year

df = add_outlier_flags(df, current_year=CURRENT_YEAR)
price_mask = df["price"].notna() & ~df["price_on_request"]

print(f"\nprice_outlier — flagged: {df['price_outlier'].sum():,} "
      f"({df['price_outlier'].mean()*100:.2f}% of all rows)")

# =============================================================================
# FLAG — area_m2 (global IQR)
# area_m2 = 0 always flagged regardless of IQR.
# =============================================================================

area_mask = df["area_m2"].notna()
zero_area_mask = df["area_m2"] == 0

print(f"area_outlier  — flagged: {df['area_outlier'].sum():,} "
      f"({df['area_outlier'].mean()*100:.2f}% of all rows)")

# =============================================================================
# FLAG — year_built (range check)
# Anything before 1800 or after current year is implausible.
# =============================================================================

print(f"year_built_outlier — flagged: {df['year_built_outlier'].sum():,} "
      f"({df['year_built_outlier'].mean()*100:.2f}% of all rows)")

print(f"is_future_property — flagged: {df['is_future_property'].sum():,} "
      f"({df['is_future_property'].mean()*100:.2f}% of all rows)")

# =============================================================================
# BUILD OUTLIER REPORT
# =============================================================================

lines = []
lines.append("# Outlier Report\n")
lines.append(f"**Total rows:** {len(df):,}\n")
lines.append("Outliers are **flagged, not removed**. "
             "Final decisions belong in analysis.\n")

# --- price ---
lines.append("\n---\n\n## Price Outliers\n")
lines.append("**Method:** IQR × 3.0 applied per transaction and property type. "
             "Groups with fewer than 10 rows skipped.\n")
lines.append(f"**Total flagged:** {df['price_outlier'].sum():,}\n")

lines.append("\n### Flagged counts by property type\n")
lines.append("| property_type_en | total | flagged | flag % |")
lines.append("|---|---|---|---|")

price_summary = (
    df[price_mask]
    .groupby("property_type_en", as_index=False)
    .agg(
        total=("source_id", "size"),
        flagged=("price_outlier", "sum"),
    )
)
price_summary["flag_pct"] = (price_summary["flagged"] / price_summary["total"] * 100).round(1)
price_summary = price_summary.sort_values("flagged", ascending=False)

for _, row in price_summary.iterrows():
    lines.append(f"| {row['property_type_en']} | {int(row['total']):,} | "
                 f"{int(row['flagged']):,} | {row['flag_pct']} |")

lines.append("\n### Price distribution of flagged rows\n")
flagged_prices = df.loc[df["price_outlier"], "price"]
lines.append(f"- Min: {flagged_prices.min():,.0f} €")
lines.append(f"- Max: {flagged_prices.max():,.0f} €")
lines.append(f"- Median: {flagged_prices.median():,.0f} €")

lines.append("\n### Sample flagged rows (10 highest prices)\n")
lines.append("| source_id | property_type_en | price | transaction_type |")
lines.append("|---|---|---|---|")
top_price = (
    df[df["price_outlier"]]
    .nlargest(10, "price")[["source_id", "property_type_en", "price", "transaction_type"]]
)
for _, row in top_price.iterrows():
    lines.append(f"| {row['source_id']} | {row['property_type_en']} | "
                 f"{row['price']:,.0f} € | {row['transaction_type']} |")

# --- area_m2 ---
lines.append("\n---\n\n## Area Outliers\n")
lines.append("**Method:** IQR × 3.0 applied per property type. "
             "Values of 0 are always flagged.\n")
lines.append(f"**Total flagged:** {df['area_outlier'].sum():,}\n")

lines.append(f"- Zero area rows: {zero_area_mask.sum():,}")

flagged_area = df.loc[df["area_outlier"] & df["area_m2"].notna(), "area_m2"]
lines.append("\n### Distribution of flagged area values")
lines.append(f"- Min: {flagged_area.min():,.1f} m²")
lines.append(f"- Max: {flagged_area.max():,.1f} m²")
lines.append(f"- Median: {flagged_area.median():,.1f} m²")

lines.append("\n### Sample flagged rows (10 largest areas)\n")
lines.append("| source_id | property_type_en | area_m2 | transaction_type |")
lines.append("|---|---|---|---|")
top_area = (
    df[df["area_outlier"] & df["area_m2"].notna()]
    .nlargest(10, "area_m2")[["source_id", "property_type_en", "area_m2", "transaction_type"]]
)
for _, row in top_area.iterrows():
    lines.append(f"| {row['source_id']} | {row['property_type_en']} | "
                 f"{row['area_m2']:,.1f} m² | {row['transaction_type']} |")

# --- year_built ---
lines.append("\n---\n\n## Year Built & Construction Status\n")
lines.append(f"**Completed properties:** year_built ≤ {CURRENT_YEAR}\n")
lines.append(f"**Future properties:** year_built > {CURRENT_YEAR} "
             "(interpreted as projected completion dates for off-plan listings)\n")
lines.append(f"**Hard outliers:** year_built < {YEAR_MIN} or > {YEAR_MAX_HARD}\n")

lines.append(f"\n- Future properties flagged: {df['is_future_property'].sum():,}")
lines.append(f"- Hard outliers flagged: {df['year_built_outlier'].sum():,}\n")

if df["is_future_property"].sum() > 0:
    flagged_years = df.loc[df["is_future_property"], "year_built"]
    lines.append(f"- Min: {flagged_years.min()}")
    lines.append(f"- Max: {flagged_years.max()}")
    lines.append("\n### Future properties by type and projected completion year\n")
    lines.append("| property_type_en | year_built | count |")
    lines.append("|---|---|---|")

    year_summary = (
        df[df["is_future_property"]]
        .groupby(["property_type_en", "year_built"])
        .size()
        .reset_index(name="count")
        .sort_values(["year_built", "count"], ascending=[True, False])
    )

    for _, row in year_summary.iterrows():
        lines.append(f"| {row['property_type_en']} | {int(row['year_built'])} | {int(row['count']):,} |")

# =============================================================================
# WRITE REPORT
# =============================================================================

report_path = DOCS_PATH / "outlier_report.md"
with open(report_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"\nOutlier report written to: {report_path}")

# =============================================================================
# SAVE
# =============================================================================

output_path = CLEAN_PATH / "df_flagged.pkl"
df.to_pickle(output_path)

print(f"df_flagged saved to: {output_path}")
print(f"Shape: {df.shape}")
print("New columns: price_outlier, area_outlier, year_built_outlier, is_future_property")
