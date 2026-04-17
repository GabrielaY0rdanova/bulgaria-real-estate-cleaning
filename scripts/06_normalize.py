# =============================================================================
# real_estate_cleaning — Normalize
# Source: df_flagged.pkl (output of 05_flag_outliers.py)
# Purpose: Split the cleaned, deduplicated, flagged DataFrame into the eight
#          relational tables defined in 00_schema.sql. Output is one CSV per
#          table in data/clean/.
# Task:    12
# Run after: 05_flag_outliers.py
# =============================================================================

from pathlib import Path
import pandas as pd

CLEAN_PATH = Path("data/clean")
CLEAN_PATH.mkdir(exist_ok=True)

# =============================================================================
# TRANSLITERATION  (Bulgarian Cyrillic → Latin, Streamlined Transliteration System)
# =============================================================================

_CYR_TO_LAT = {
    "А": "A",  "а": "a",
    "Б": "B",  "б": "b",
    "В": "V",  "в": "v",
    "Г": "G",  "г": "g",
    "Д": "D",  "д": "d",
    "Е": "E",  "е": "e",
    "Ж": "Zh", "ж": "zh",
    "З": "Z",  "з": "z",
    "И": "I",  "и": "i",
    "Й": "Y",  "й": "y",
    "К": "K",  "к": "k",
    "Л": "L",  "л": "l",
    "М": "M",  "м": "m",
    "Н": "N",  "н": "n",
    "О": "O",  "о": "o",
    "П": "P",  "п": "p",
    "Р": "R",  "р": "r",
    "С": "S",  "с": "s",
    "Т": "T",  "т": "t",
    "У": "U",  "у": "u",
    "Ф": "F",  "ф": "f",
    "Х": "H",  "х": "h",
    "Ц": "Ts", "ц": "ts",
    "Ч": "Ch", "ч": "ch",
    "Ш": "Sh", "ш": "sh",
    "Щ": "Sht","щ": "sht",
    "Ъ": "A",  "ъ": "a",
    "Ь": "Y",  "ь": "y",
    "Ю": "Yu", "ю": "yu",
    "Я": "Ya", "я": "ya",
}


def transliterate(text: str) -> str:
    """Transliterate Bulgarian Cyrillic text to Latin script."""
    if pd.isna(text):
        return None
    result = []
    for ch in str(text):
        result.append(_CYR_TO_LAT.get(ch, ch))   # non-Cyrillic passes through
    return "".join(result)

# =============================================================================
# LOAD
# =============================================================================

df = pd.read_pickle(CLEAN_PATH / "df_flagged.pkl")

print(f"Loaded: {len(df):,} rows | columns: {list(df.columns)}")

# =============================================================================
# TRANSLATION DICTS
# =============================================================================

# All 46 distinct feature values found in the audit (superset of the 39 in the
# handoff brief — 7 additional values confirmed in combined prodazhbi + naemi).
FEATURES_MAP = {
    # Security & access
    "Асансьор":                     "elevator",
    "Видео наблюдение":             "video surveillance",
    "Контрол на достъпа":           "access control",
    "Охрана":                       "security",
    "Автоматична врата":            "automatic gate",
    "СОТ":                          "alarm system",
    "В затворен комплекс":          "gated complex",

    # Parking
    "С паркинг":                    "parking available",        # parking available, not guaranteed
    "С паркомясто":                 "with parking space",       # dedicated parking space guaranteed
    "Подземен":                     "underground parking",
    "С гараж":                      "with garage",

    # Furnishing & fit-out
    "Обзаведен":                    "furnished",
    "Необзаведен":                  "unfurnished",
    "Саниран":                      "insulated/renovated",
    "За ремонт":                    "needs renovation",
    "Лукс":                         "luxury",
    "Отопляем":                     "heated",

    # Utilities & infrastructure
    "Климатик":                     "air conditioning",
    "Интернет връзка":              "internet connection",
    "Окабеляване":                  "wiring",
    "Ток":                          "electricity",
    "До ток":                       "electricity nearby",
    "Вода":                         "water",
    "До вода":                      "water nearby",
    "Канализация":                  "sewer connection",
    "Осветен":                      "well-lit",
    "Отделен електромер":           "separate electricity meter",
    "Ел. зарядна станция":          "EV charging station",
    "Поливност":                    "irrigation",

    # Land / planning
    "За жил.строителство":          "residential zoning",
    "За пром.строителство":         "industrial zoning",
    "Земеделска земя":              "agricultural land",
    "До регулация":                 "near zoning boundary",
    "До път":                       "near road",
    "Виза":                         "planning permit",

    # Transaction / commercial
    "Бартер":                       "barter",
    "Лизинг":                       "leasing available",
    "Ипотекиран":                   "mortgaged",
    "Обезщетение":                  "compensation deal",
    "Възможност за дан. кредит":    "VAT reclaimable",
    "С действащ бизнес":            "operating business included",
    "В строеж":                     "under construction",

    # Rental-specific
    "С дом. любимци":               "pets allowed",
    "Почистване":                   "cleaning service",
    "С преход":                     "walk-through rooms",

    # Vehicle services
    "Канал за ремонт":              "inspection pit",
}

# Property type categories — used to populate property_types.category
PROPERTY_TYPE_CATEGORIES = {
    "apartment":            "residential",
    "multi-room apartment": "residential",
    "maisonette":           "residential",
    "studio/attic":         "residential",
    "room":                 "residential",
    "house floor":          "residential",
    "house":                "residential",
    "villa":                "residential",
    "villa community":      "residential",
    "office":               "commercial",
    "shop":                 "commercial",
    "restaurant/bar":       "commercial",
    "commercial complex":   "commercial",
    "hotel":                "commercial",
    "hair/beauty salon":    "commercial",
    "doctor's office":      "commercial",
    "dental office":        "commercial",
    "clinic":               "commercial",
    "spa/tanning studio":   "commercial",
    "gym":                  "commercial",
    "children's center":    "commercial",
    "bank office":          "commercial",
    "pharmacy":             "commercial",
    "care home":            "commercial",
    "photography studio":   "commercial",
    "fuel/gas station":     "commercial",
    "auto repair shop":     "commercial",
    "car wash":             "commercial",
    "water park":           "commercial",
    "industrial space":     "industrial",
    "warehouse":            "industrial",
    "factory/plant":        "industrial",
    "standalone building":  "industrial",
    "cold storage":         "industrial",
    "farm":                 "land",
    "agricultural land":    "land",
    "plot":                 "land",
    "solar park":           "land",
    "garage":               "parking",
    "parking space":        "parking",
    "garage/parking":       "parking",
    "parking":              "parking",
}

# =============================================================================
# HELPER — assign surrogate IDs to a lookup DataFrame
# =============================================================================

def make_lookup(values: list[tuple], columns: list[str], id_col: str) -> pd.DataFrame:
    """
    Build a lookup DataFrame with a 1-based integer surrogate key.
    values  — list of tuples, one per unique row
    columns — column names (excluding the id column)
    id_col  — name of the surrogate key column
    """
    df_lookup = pd.DataFrame(values, columns=columns).drop_duplicates()
    df_lookup = df_lookup.reset_index(drop=True)
    df_lookup.insert(0, id_col, df_lookup.index + 1)
    return df_lookup

# =============================================================================
# TABLE 1 — geographies
# Hierarchy: region → locality → area
# geo_id points to the most specific level available.
# properties.geo_id will reference the area row when area
# is populated, otherwise the locality row.
# =============================================================================

print("\n--- Building geographies ---")

geo_rows = []
geo_id_counter = 1

# --- region level (top level — no parent) ---
region_keys = df[["region"]].drop_duplicates().sort_values("region")
region_id_map = {}   # region → geo_id
for _, row in region_keys.iterrows():
    name = row["region"]
    geo_rows.append({
        "geo_id": geo_id_counter,
        "parent_id": None,
        "level": "region",
        "name_bg": name,
        "name_en": transliterate(name),
        "locality_type": "city",
    })
    region_id_map[name] = geo_id_counter
    geo_id_counter += 1

# --- locality level ---
locality_keys = (
    df[["region", "locality", "locality_type"]]
    .drop_duplicates()
    .sort_values(["region", "locality"])
)
locality_id_map = {}   # (region, locality) → geo_id
for _, row in locality_keys.iterrows():
    parent = region_id_map[row["region"]]
    name = row["locality"]
    geo_rows.append({
        "geo_id": geo_id_counter,
        "parent_id": parent,
        "level": "locality",
        "name_bg": name,
        "name_en": transliterate(name),
        "locality_type": row["locality_type"],
    })
    locality_id_map[(row["region"], row["locality"])] = geo_id_counter
    geo_id_counter += 1

# --- area level ---
area_keys = (
    df.loc[df["area"].notna(), ["region", "locality", "area"]]
    .drop_duplicates()
    .sort_values(["region", "locality", "area"])
)
area_id_map = {}   # (region, locality, area) → geo_id
for _, row in area_keys.iterrows():
    parent = locality_id_map[(row["region"], row["locality"])]
    name = row["area"]
    geo_rows.append({
        "geo_id": geo_id_counter,
        "parent_id": parent,
        "level": "area",
        "name_bg": name,
        "name_en": transliterate(name),
        "locality_type": None,
    })
    area_id_map[
        (row["region"], row["locality"], row["area"])
    ] = geo_id_counter
    geo_id_counter += 1

df_geographies = pd.DataFrame(geo_rows)
df_geographies["parent_id"] = df_geographies["parent_id"].astype("Int64")
# Rename name_bg → name to match the DDL column.
# name_en (transliterated Latin) is retained in the CSV for reference
# but dropped during export (08_export.py) before COPY to PostgreSQL.


print(f"geographies rows: {len(df_geographies):,}")
print(f"  region:         {(df_geographies['level'] == 'region').sum():,}")
print(f"  locality:       {(df_geographies['level'] == 'locality').sum():,}")
print(f"  area:           {(df_geographies['level'] == 'area').sum():,}")

# --- resolve geo_id for each listing row ---
# Points to area when available, otherwise locality.

def resolve_geo_id(row) -> int:
    # Keys are guaranteed to exist — both maps were built from the same df.
    if pd.notna(row["area"]):
        return area_id_map[
            (row["region"], row["locality"], row["area"])
        ]
    return locality_id_map[(row["region"], row["locality"])]

df["_geo_id"] = df.apply(resolve_geo_id, axis=1)

print(f"_geo_id assigned to all {len(df):,} rows")

# =============================================================================
# TABLE 2 — construction_types
# =============================================================================

print("\n--- Building construction_types ---")

# English values are already in the df (mapped in 03_clean_fields.py).
# Rebuild name_bg → name_en from the mapping dict used there.
CONSTRUCTION_TYPE_MAP_EN = {
    "Тухла":                 "brick",
    "Панел":                 "panel",
    "Гредоред":              "timber frame",
    "ЕПК":                   "EPK",
    "Сглобяема конструкция": "prefab",
    "ПК":                    "PK",
}

ct_rows = [
    (i + 1, bg, en)
    for i, (bg, en) in enumerate(CONSTRUCTION_TYPE_MAP_EN.items())
]
df_construction_types = pd.DataFrame(
    ct_rows, columns=["construction_type_id", "name_bg", "name_en"]
)

# Build reverse map: name_en → construction_type_id (for joining to properties)
ct_en_to_id = dict(
    zip(df_construction_types["name_en"], df_construction_types["construction_type_id"])
)

print(f"construction_types rows: {len(df_construction_types)}")

# =============================================================================
# TABLE 3 — property_types
# =============================================================================

print("\n--- Building property_types ---")

# Rebuild from PROPERTY_TYPE_MAP in 03_clean_fields.py.
# Keys are Bulgarian; values are (name_en, bedrooms).
PROPERTY_TYPE_MAP_BG = {
    "1-СТАЕН":                          "apartment",
    "2-СТАЕН":                          "apartment",
    "3-СТАЕН":                          "apartment",
    "4-СТАЕН":                          "apartment",
    "МНОГОСТАЕН":                       "multi-room apartment",
    "МЕЗОНЕТ":                          "maisonette",
    "АТЕЛИЕ, ТАВАН":                    "studio/attic",
    "СТАЯ":                             "room",
    "ОФИС":                             "office",
    "ЗАВЕДЕНИЕ":                        "restaurant/bar",
    "МАГАЗИН":                          "shop",
    "ПРОМ. ПОМЕЩЕНИЕ":                  "industrial space",
    "ЗЕМЕДЕЛСКА ЗЕМЯ":                  "agricultural land",
    "ГАРАЖ":                            "garage",
    "ПАРКОМЯСТО":                       "parking space",
    "ГАРАЖ, ПАРКОМЯСТО":                "garage/parking",
    "ПАРКИНГ":                          "parking",
    "КЪЩА":                             "house",
    "ЕТАЖ ОТ КЪЩА":                     "house floor",
    "ВИЛА":                             "villa",
    "ПАРЦЕЛ":                           "plot",
    "МЯСТО":                            "plot",
    "ХОТЕЛ":                            "hotel",
    "СКЛАД":                            "warehouse",
    "САМОСТОЯТЕЛНА СГРАДА":             "standalone building",
    "ФАБРИКА/ЗАВОД":                    "factory/plant",
    "ТЪРГОВСКИ КОМПЛЕКС":               "commercial complex",
    "ФЕРМА":                            "farm",
    "ВИЛНО СЕЛИЩЕ":                     "villa community",
    "СОЛАРЕН ПАРК":                     "solar park",
    "АВТОСЕРВИЗ":                       "auto repair shop",
    "ФРИЗЬОРСКИ/КОЗМЕТИЧЕН САЛОН":      "hair/beauty salon",
    "ЛЕКАРСКИ КАБИНЕТ":                 "doctor's office",
    "БЕНЗИНОСТАНЦИЯ/ГАЗСТАНЦИЯ":        "fuel/gas station",
    "ФИТНЕС ЗАЛА":                      "gym",
    "ДОМ ЗА ВЪЗРАСТНИ ХОРА":            "care home",
    "КЛИНИКА":                          "clinic",
    "СПА/СОЛАРНО СТУДИО":               "spa/tanning studio",
    "СТОМАТОЛОГИЧЕН КАБИНЕТ":           "dental office",
    "ДЕТСКИ ЦЕНТЪР":                    "children's center",
    "БАНКОВ ОФИС":                      "bank office",
    "АВТОМИВКА":                        "car wash",
    "АПТЕКА":                           "pharmacy",
    "ХЛАДИЛЕН СКЛАД":                   "cold storage",
    "АКВАПАРК":                         "water park",
    "ФОТОГРАФСКО СТУДИО":               "photography studio",
}

# Unique (name_bg, name_en) pairs — note ПАРЦЕЛ and МЯСТО both map to "plot"
# so they get separate rows (different Bulgarian names, same English name).
pt_rows = []
for i, (bg, en) in enumerate(PROPERTY_TYPE_MAP_BG.items()):
    pt_rows.append({
        "property_type_id": i + 1,
        "name_bg": bg,
        "name_en": en,
        "category": PROPERTY_TYPE_CATEGORIES.get(en),
    })

df_property_types = pd.DataFrame(pt_rows)

# Build lookup: name_bg → property_type_id
pt_bg_to_id = dict(
    zip(df_property_types["name_bg"], df_property_types["property_type_id"])
)

print(f"property_types rows: {len(df_property_types)}")

# =============================================================================
# TABLE 4 — features
# =============================================================================

print("\n--- Building features ---")

unmapped_features = set(
    df["features"].dropna().str.split(", ").explode().str.strip().unique()
) - set(FEATURES_MAP.keys())

if unmapped_features:
    raise ValueError(f"Unmapped feature values: {unmapped_features}")

feature_rows = [
    {"feature_id": i + 1, "name_bg": bg, "name_en": en}
    for i, (bg, en) in enumerate(FEATURES_MAP.items())
]
df_features = pd.DataFrame(feature_rows)

# Build lookup: name_bg → feature_id
feat_bg_to_id = dict(zip(df_features["name_bg"], df_features["feature_id"]))

print(f"features rows: {len(df_features)}")

# =============================================================================
# TABLE 5 — contacts
# Deduplicated on (contact_type, name, phone).
# Owner rows where both name and phone are null each get their own row —
# there is no reliable way to identify them as the same person.
# =============================================================================

print("\n--- Building contacts ---")

# Use a sentinel string for null name/phone so tuples are hashable and
# distinct non-null values don't accidentally merge with nulls.
# The sentinel is stripped back to None when building the contact rows.
df["_contact_key"] = list(zip(
    df["poster_type"],
    df["agency_name"].fillna("__NULL__"),
    df["agency_phone"].fillna("__NULL__"),
))

# Build unique contact rows — preserve null sentinel only for keying,
# store as None in the actual table.
contact_key_to_id = {}
contact_rows = []
contact_id_counter = 1

# Owner listings with null name AND null phone: each listing is its own contact
# (no basis for deduplication). Process these separately so we don't merge them.
owner_null_mask = (
    (df["poster_type"] == "owner") &
    df["agency_name"].isna() &
    df["agency_phone"].isna()
)

# All other contacts — deduplicate
for key in df.loc[~owner_null_mask, "_contact_key"].unique():
    contact_type, name, phone = key
    contact_key_to_id[key] = contact_id_counter
    raw_phone = None if phone == "__NULL__" else phone
    contact_rows.append({
        "contact_id": contact_id_counter,
        "contact_type": contact_type,
        "name": None if name == "__NULL__" else name,
        "phone": None if phone == "__NULL__" else phone,
    })
    contact_id_counter += 1

# Owner listings with null name and null phone — one row per listing index
owner_null_indices = df.index[owner_null_mask].tolist()
owner_contact_ids = {}   # df index → contact_id
for idx in owner_null_indices:
    owner_contact_ids[idx] = contact_id_counter
    contact_rows.append({
        "contact_id": contact_id_counter,
        "contact_type": "owner",
        "name": None,
        "phone": None,
    })
    contact_id_counter += 1

# --- assign _contact_id to each listing row ---
def get_contact_id(row) -> int:
    if row.name in owner_contact_ids:
        return owner_contact_ids[row.name]
    return contact_key_to_id[row["_contact_key"]]

df["_contact_id"] = df.apply(get_contact_id, axis=1)

df_contacts = pd.DataFrame(contact_rows)

# =============================================================================
# VALIDATE — phone format (must already be clean from 03_clean_fields.py)
# =============================================================================

bad_phones = df_contacts[
    df_contacts["phone"].astype(str).str.contains(r"\.0", na=False)
]

if len(bad_phones) > 0:
    raise ValueError(
        f"Found {len(bad_phones)} phones with '.0' — cleaning failed upstream"
    )

print("✓ Phone validation passed (no .0 artifacts)")

dedup_savings = len(df) - len(df_contacts)

print(f"contacts rows: {len(df_contacts):,}  (deduplicated from {len(df):,} listings — saved {dedup_savings:,} rows)")
print(f"  agency contacts: {(df_contacts['contact_type'] == 'agency').sum():,}")
print(f"  owner contacts:  {(df_contacts['contact_type'] == 'owner').sum():,}")

# =============================================================================
# TABLE 6 — properties
# One row per listing (no cross-listing property identity — see design doc).
# =============================================================================

print("\n--- Building properties ---")

# Assign property_id = positional index + 1 (rows are already deduplicated
# in 04_deduplicate.py, so this is 1-to-1 with listings).
df = df.reset_index(drop=True)
df["_property_id"] = df.index + 1

# Resolve construction_type_id — null when construction_type is null
df["_construction_type_id"] = df["construction_type"].map(ct_en_to_id)

# Resolve property_type_id from the original Bulgarian column
df["_property_type_id"] = df["property_type"].map(pt_bg_to_id)

unmapped_pt = df.loc[df["property_type"].notna() & df["_property_type_id"].isna(), "property_type"].unique()
if len(unmapped_pt) > 0:
    raise ValueError(f"Unmapped property_type values: {unmapped_pt}")

df_properties = df[[
    "_property_id",
    "_geo_id",
    "_property_type_id",
    "_construction_type_id",
    "bedrooms",
    "area_m2",
    "floor",
    "total_floors",
    "construction_status",
    "year_built",
    "gas",
    "tec",
]].rename(columns={
    "_property_id":           "property_id",
    "_geo_id":                "geo_id",
    "_property_type_id":      "property_type_id",
    "_construction_type_id":  "construction_type_id",
})

# Cast nullable integer columns
for col in ["bedrooms", "floor", "total_floors", "year_built"]:
    df_properties[col] = df_properties[col].astype("Int64")

print(f"properties rows: {len(df_properties):,}")

# =============================================================================
# TABLE 7 — listings
# =============================================================================

print("\n--- Building listings ---")

df_listings = df[[
    "_property_id",
    "source_id",
    "_contact_id",
    "transaction_type",
    "listing_tier",
    "listing_url",
    "price",
    "price_on_request",
    "date_posted",
    "date_modified",
    "has_photos",
    "status",
    "status_changed_at",
    "scraped_at",
    "date_last_checked",
]].copy()

df_listings.insert(0, "listing_id", df_listings.index + 1)
df_listings = df_listings.rename(columns={
    "_property_id": "property_id",
    "_contact_id":  "contact_id",
})

print(f"listings rows: {len(df_listings):,}")

# =============================================================================
# TABLE 8 — property_features (junction)
# Parse the comma-separated features string for each row.
# =============================================================================

print("\n--- Building property_features ---")

pf_rows = []

features_series = df.loc[df["features"].notna(), ["_property_id", "features"]]

for _, row in features_series.iterrows():
    raw_features = [f.strip() for f in row["features"].split(", ") if f.strip()]
    for feat_bg in raw_features:
        feat_id = feat_bg_to_id.get(feat_bg)
        if feat_id is None:
            raise ValueError(f"Feature not in lookup: '{feat_bg}'")
        pf_rows.append({
            "property_id": row["_property_id"],
            "feature_id": feat_id,
        })

df_property_features = pd.DataFrame(pf_rows).drop_duplicates()

print(f"property_features rows: {len(df_property_features):,}")

# =============================================================================
# SANITY CHECKS
# =============================================================================

print("\n--- Sanity checks ---")

# 1. Every listing has a property_id that exists in properties
listings_pids = set(df_listings["property_id"])
properties_pids = set(df_properties["property_id"])
assert listings_pids == properties_pids, \
    f"property_id mismatch: {len(listings_pids - properties_pids)} listing IDs missing from properties"
print("✓ All listing property_ids exist in properties")

# 2. Every listing has a contact_id that exists in contacts
listings_cids = set(df_listings["contact_id"])
contacts_cids = set(df_contacts["contact_id"])
orphan_contacts = listings_cids - contacts_cids
assert not orphan_contacts, \
    f"contact_id mismatch: {len(orphan_contacts)} listing contact_ids missing from contacts"
print("✓ All listing contact_ids exist in contacts")

# 3. Every property has a geo_id that exists in geographies
prop_gids = set(df_properties["geo_id"])
geo_gids = set(df_geographies["geo_id"])
orphan_geos = prop_gids - geo_gids
assert not orphan_geos, \
    f"geo_id mismatch: {len(orphan_geos)} property geo_ids missing from geographies"
print("✓ All property geo_ids exist in geographies")

# 4. Every property has a property_type_id that exists in property_types
prop_ptids = set(df_properties["property_type_id"].dropna())
pt_ptids = set(df_property_types["property_type_id"])
orphan_pts = prop_ptids - pt_ptids
assert not orphan_pts, \
    f"property_type_id mismatch: {len(orphan_pts)} IDs missing from property_types"
print("✓ All property property_type_ids exist in property_types")

# 5. Every property_feature property_id exists in properties
pf_pids = set(df_property_features["property_id"])
orphan_pf = pf_pids - properties_pids
assert not orphan_pf, \
    f"property_features property_id mismatch: {len(orphan_pf)} IDs missing from properties"
print("✓ All property_features property_ids exist in properties")

# 6. Every property_feature feature_id exists in features
pf_fids = set(df_property_features["feature_id"])
feat_fids = set(df_features["feature_id"])
orphan_fids = pf_fids - feat_fids
assert not orphan_fids, \
    f"property_features feature_id mismatch: {len(orphan_fids)} IDs missing from features"
print("✓ All property_features feature_ids exist in features")

# 7. source_id is unique in listings
assert df_listings["source_id"].is_unique, "source_id is not unique in listings"
print("✓ source_id is unique in listings")

# 8. Row counts add up
print(f"\n=== FINAL TABLE SIZES ===")
tables = {
    "geographies":        df_geographies,
    "construction_types": df_construction_types,
    "property_types":     df_property_types,
    "features":           df_features,
    "contacts":           df_contacts,
    "properties":         df_properties,
    "listings":           df_listings,
    "property_features":  df_property_features,
}
for name, table in tables.items():
    print(f"  {name:<22} {len(table):>8,} rows  |  {len(table.columns)} cols")

# =============================================================================
# SAVE
# =============================================================================

print("\n--- Saving CSVs ---")

for name, table in tables.items():
    path = CLEAN_PATH / f"{name}.csv"
    table.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  {path}")

print("\n06_normalize.py complete.")
