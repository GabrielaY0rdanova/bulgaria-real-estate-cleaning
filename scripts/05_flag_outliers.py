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
import pandas as pd

CLEAN_PATH = Path("data/clean")
DOCS_PATH = Path("docs")
DOCS_PATH.mkdir(exist_ok=True)

# =============================================================================
# LOAD
# =============================================================================

df = pd.read_pickle(CLEAN_PATH / "df_dedup.pkl")

print(f"Loaded: {len(df):,} rows")

# =============================================================================
# HELPERS
# =============================================================================

def iqr_bounds(series: pd.Series, k: float = 3.0) -> tuple[float, float]:
    """
    Return (lower, upper) outlier bounds using k * IQR rule.
    k=3.0 is used instead of the standard 1.5 — real estate prices have
    naturally wide distributions and we only want to flag extreme values,
    not aggressively trim the tails.
    """
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    return q1 - k * iqr, q3 + k * iqr


def flag_iqr_outliers(series: pd.Series, k: float = 3.0) -> pd.Series:
    """Return a boolean Series — True where value is outside k*IQR bounds."""
    lower, upper = iqr_bounds(series, k)
    return (series < lower) | (series > upper)

# =============================================================================
# FLAG — price (per property_type_en group)
# Rationale: a €2M apartment is suspicious; a €2M hotel is not.
# Only applied to rows where price is not null and not price_on_request.
# =============================================================================

df["price_outlier"] = False

price_mask = df["price"].notna() & ~df["price_on_request"]
price_data = df.loc[price_mask, ["price", "property_type_en"]].copy()

for prop_type, group in price_data.groupby("property_type_en"):
    if len(group) < 10:
        # Too few rows to compute meaningful IQR — skip flagging for this type
        continue
    outlier_flags = flag_iqr_outliers(group["price"])
    df.loc[outlier_flags[outlier_flags].index, "price_outlier"] = True

print(f"\nprice_outlier — flagged: {df['price_outlier'].sum():,} "
      f"({df['price_outlier'].mean()*100:.2f}% of all rows)")

# =============================================================================
# FLAG — area_m2 (global IQR)
# area_m2 = 0 always flagged regardless of IQR.
# =============================================================================

df["area_outlier"] = False

area_mask = df["area_m2"].notna()
area_flags = flag_iqr_outliers(df.loc[area_mask, "area_m2"])
df.loc[area_flags[area_flags].index, "area_outlier"] = True

# area_m2 = 0 is always an outlier (meaningless)
zero_area_mask = df["area_m2"] == 0
df.loc[zero_area_mask, "area_outlier"] = True

print(f"area_outlier  — flagged: {df['area_outlier'].sum():,} "
      f"({df['area_outlier'].mean()*100:.2f}% of all rows)")

# =============================================================================
# FLAG — year_built (range check)
# Anything before 1800 or after current year is implausible.
# =============================================================================

YEAR_MIN = 1800
CURRENT_YEAR = pd.Timestamp.now().year

# Hard cap for sanity (extreme future values)
YEAR_MAX_HARD = 2040

df["year_built_outlier"] = False

year_mask = df["year_built"].notna()

# Flag true outliers (past + extreme future)
year_flags = (
    (df.loc[year_mask, "year_built"] < YEAR_MIN) |
    (df.loc[year_mask, "year_built"] > YEAR_MAX_HARD)
)
df.loc[year_flags[year_flags].index, "year_built_outlier"] = True

# New feature: future / under-construction properties
df["is_future_property"] = False
future_mask = df["year_built"] > CURRENT_YEAR
df.loc[future_mask, "is_future_property"] = True

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
lines.append("**Method:** IQR × 3.0 applied per `property_type_en` group. "
             "Groups with fewer than 10 rows skipped.\n")
lines.append(f"**Total flagged:** {df['price_outlier'].sum():,}\n")

lines.append("\n### Flagged counts by property type\n")
lines.append("| property_type_en | total | flagged | flag % |")
lines.append("|---|---|---|---|")

price_summary = (
    df[price_mask]
    .groupby("property_type_en")
    .apply(lambda g: pd.Series({
        "total": len(g),
        "flagged": g["price_outlier"].sum(),
    }))
    .reset_index()
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
lines.append("**Method:** Global IQR × 3.0. Values of 0 always flagged.\n")
lines.append(f"**Total flagged:** {df['area_outlier'].sum():,}\n")

area_data = df.loc[df["area_m2"].notna(), "area_m2"]
lower, upper = iqr_bounds(area_data)
lines.append(f"- IQR bounds: {lower:.1f} m² → {upper:.1f} m²")
lines.append(f"- Zero area rows: {zero_area_mask.sum():,}")

flagged_area = df.loc[df["area_outlier"] & df["area_m2"].notna(), "area_m2"]
lines.append(f"\n### Distribution of flagged area values")
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
print(f"New columns: price_outlier, area_outlier, year_built_outlier, is_future_property")
