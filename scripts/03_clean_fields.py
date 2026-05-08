# =============================================================================
# real_estate_cleaning — Clean Fields
# Source: imot.bg scraper output (prodazhbi + naemi CSVs)
# Purpose: Validate and clean raw fields. Outputs df_clean as a pickle for
#          downstream scripts.
# Task:    8 + 9 (clean raw fields; extract bedrooms from property_type)
# Run after: 02_audit_raw_data.py
# =============================================================================

from pathlib import Path
import re
import pandas as pd

DATA_PATH = Path("data/raw")
CLEAN_PATH = Path("data/clean")
CLEAN_PATH.mkdir(exist_ok=True)

# =============================================================================
# LOAD — replicate ingest to produce df_staging
# =============================================================================

prodazhbi_files = list(DATA_PATH.glob("prodazhbi_*.csv"))
naemi_files = list(DATA_PATH.glob("naemi_*.csv"))

if len(prodazhbi_files) == 0:
    raise FileNotFoundError("No prodazhbi CSV found in data/raw/")
if len(naemi_files) == 0:
    raise FileNotFoundError("No naemi CSV found in data/raw/")
prodazhbi_files = [max(prodazhbi_files, key=lambda p: p.stat().st_mtime)]
naemi_files = [max(naemi_files, key=lambda p: p.stat().st_mtime)]

PHONE_COLUMNS = ["agency_phone", "phone", "contact_phone"]

df_prod = pd.read_csv(
    prodazhbi_files[0],
    low_memory=False,
    dtype={col: "string" for col in PHONE_COLUMNS if col}
)

df_naem = pd.read_csv(
    naemi_files[0],
    low_memory=False,
    dtype={col: "string" for col in PHONE_COLUMNS if col}
)

df_prod["transaction_type"] = "sale"
df_naem["transaction_type"] = "rental"

df = pd.concat([df_prod, df_naem], ignore_index=True)

print(f"Loaded: {len(df):,} rows ({len(df_prod):,} sales + {len(df_naem):,} rentals)")

# =============================================================================
# MAPPING DICTS
# =============================================================================

BG_MONTHS = {
    "януари":    "January",
    "февруари":  "February",
    "март":      "March",
    "април":     "April",
    "май":       "May",
    "юни":       "June",
    "юли":       "July",
    "август":    "August",
    "септември": "September",
    "октомври":  "October",
    "ноември":   "November",
    "декември":  "December",
}

PROPERTY_TYPE_MAP = {
    "1-СТАЕН":                          ("apartment",            1),
    "2-СТАЕН":                          ("apartment",            2),
    "3-СТАЕН":                          ("apartment",            3),
    "4-СТАЕН":                          ("apartment",            4),
    "МНОГОСТАЕН":                       ("multi-room apartment", None),
    "МЕЗОНЕТ":                          ("maisonette",           None),
    "АТЕЛИЕ, ТАВАН":                    ("studio/attic",         None),
    "СТАЯ":                             ("room",                 None),
    "ОФИС":                             ("office",               None),
    "ЗАВЕДЕНИЕ":                        ("restaurant/bar",       None),
    "МАГАЗИН":                          ("shop",                 None),
    "ПРОМ. ПОМЕЩЕНИЕ":                  ("industrial space",     None),
    "ЗЕМЕДЕЛСКА ЗЕМЯ":                  ("agricultural land",    None),
    "ГАРАЖ":                            ("garage",               None),
    "ПАРКОМЯСТО":                       ("parking space",        None),
    "ГАРАЖ, ПАРКОМЯСТО":                ("garage/parking",       None),
    "ПАРКИНГ":                          ("parking",              None),
    "КЪЩА":                             ("house",                None),
    "ЕТАЖ ОТ КЪЩА":                     ("house floor",          None),
    "ВИЛА":                             ("villa",                None),
    "ПАРЦЕЛ":                           ("plot",                 None),
    "МЯСТО":                            ("plot",                 None),
    "ХОТЕЛ":                            ("hotel",                None),
    "СКЛАД":                            ("warehouse",            None),
    "САМОСТОЯТЕЛНА СГРАДА":             ("standalone building",  None),
    "ФАБРИКА/ЗАВОД":                    ("factory/plant",        None),
    "ТЪРГОВСКИ КОМПЛЕКС":               ("commercial complex",   None),
    "ФЕРМА":                            ("farm",                 None),
    "ВИЛНО СЕЛИЩЕ":                     ("villa community",      None),
    "СОЛАРЕН ПАРК":                     ("solar park",           None),
    "АВТОСЕРВИЗ":                       ("auto repair shop",     None),
    "ФРИЗЬОРСКИ/КОЗМЕТИЧЕН САЛОН":      ("hair/beauty salon",    None),
    "ЛЕКАРСКИ КАБИНЕТ":                 ("doctor's office",      None),
    "БЕНЗИНОСТАНЦИЯ/ГАЗСТАНЦИЯ":        ("fuel/gas station",     None),
    "ФИТНЕС ЗАЛА":                      ("gym",                  None),
    "ДОМ ЗА ВЪЗРАСТНИ ХОРА":            ("care home",            None),
    "КЛИНИКА":                          ("clinic",               None),
    "СПА/СОЛАРНО СТУДИО":               ("spa/tanning studio",   None),
    "СТОМАТОЛОГИЧЕН КАБИНЕТ":           ("dental office",        None),
    "ДЕТСКИ ЦЕНТЪР":                    ("children's center",    None),
    "БАНКОВ ОФИС":                      ("bank office",          None),
    "АВТОМИВКА":                        ("car wash",             None),
    "АПТЕКА":                           ("pharmacy",             None),
    "ХЛАДИЛЕН СКЛАД":                   ("cold storage",         None),
    "АКВАПАРК":                         ("water park",           None),
    "ФОТОГРАФСКО СТУДИО":               ("photography studio",   None),
}

CONSTRUCTION_TYPE_MAP = {
    "Тухла":                 "brick",
    "Панел":                 "panel",
    "Гредоред":              "timber frame",
    "ЕПК":                   "EPK",
    "Сглобяема конструкция": "prefab",
    "ПК":                    "PK",
}

CONSTRUCTION_STATUS_MAP = {
    "Въведен в експлоатация":             "completed",
    "Ще бъде въведен в експлоатация":     "under_construction",
    "Не е въведен в експлоатация":        "not_completed",
}

TEC_MAP = {
    "ДА":           "district_heating",
    "НЕ":           "no_district_heating",
    "Лок.отопл.":   "local_heating",
    "Прокарва се":  "being_installed",
}

POSTER_TYPE_MAP = {
    "агенция":      "agency",
    "собственик":   "owner",
}

LOCALITY_TYPE_MAP = {
    "град":         "city",
    "село":         "village",
    "к.к.":         "resort_complex",
    "м-т":          "area",
    "м-ст":         "area",
    "магистрала":   "highway",
    "яз.":          "reservoir",
    "главен":       "main_road",
    "хижа":         "mountain_hut",
    "Гара":         "railway_station",
    "вилна зона":   "villa_zone",
}

# =============================================================================
# HELPERS
# =============================================================================

def parse_bg_date(raw: str) -> pd.Timestamp | None:
    """
    Parse Bulgarian date strings into a Timestamp.

    Expected formats:
        "Публикувана в 13:36 на 2 юли, 2025 год."
        "Коригирана в 15:05 на 5 април, 2026 год."
    """
    if pd.isna(raw):
        return None

    # Replace Bulgarian month names with English equivalents
    normalized = raw
    for bg, en in BG_MONTHS.items():
        normalized = normalized.replace(bg, en)

    # Extract time, day, month name, year
    match = re.search(
        r"(\d{1,2}:\d{2})\s+на\s+(\d{1,2})\s+(\w+),\s+(\d{4})",
        normalized
    )
    if not match:
        return None

    time_str, day, month_en, year = match.groups()
    try:
        return pd.Timestamp(f"{day} {month_en} {year} {time_str}")
    except Exception:
        return None


def parse_floor(raw: str) -> tuple[int | None, int | None]:
    """
    Parse raw floor string into (floor, total_floors).

    Expected format: "3 от 9"
    Returns (None, None) for null or unparseable values.
    """
    if pd.isna(raw):
        return None, None
    parts = str(raw).split(" от ")
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def parse_price(raw: str) -> tuple[float | None, bool]:
    """
    Parse raw price string into (price, price_on_request).

    Cases:
        "28 000 €"           → (28000.0, False)
        "Цена при запитване" → (None,    True)
        "$ 50000"            → (50000.0, False)  — $ treated same as €
        null                 → (None,    False)
    """
    if pd.isna(raw):
        return None, False

    raw_str = str(raw).strip()

    if "запитване" in raw_str:
        return None, True

    # Strip currency symbols and whitespace, then parse
    cleaned = raw_str.replace("€", "").replace("$", "").replace(" ", "").strip()
    try:
        return float(cleaned), False
    except ValueError:
        return None, False

# =============================================================================
# CLEAN — locality_type
# Fix 33 null rows — all are "в.з.*" localities (вилна зона)
# =============================================================================

vz_mask = df["locality"].str.startswith("в.з.", na=False) & df["locality_type"].isna()
df.loc[vz_mask, "locality_type"] = "вилна зона"

locality_type_nulls_after = df["locality_type"].isna().sum()
print(f"locality_type nulls after fix: {locality_type_nulls_after}")

# =============================================================================
# CLEAN — locality_type — translate to English
# =============================================================================

unmapped_locality_types = set(df["locality_type"].dropna().unique()) - set(LOCALITY_TYPE_MAP.keys())
if unmapped_locality_types:
    raise ValueError(f"Unmapped locality_type values: {unmapped_locality_types}")

df["locality_type"] = df["locality_type"].map(LOCALITY_TYPE_MAP)

print(f"locality_type values: {sorted(df['locality_type'].dropna().unique())}")

# =============================================================================
# CLEAN — price
# =============================================================================

price_parsed = df["price"].apply(parse_price)
df["price"] = price_parsed.apply(lambda x: x[0])
df["price_on_request"] = price_parsed.apply(lambda x: x[1])

print(f"price — non-null: {df['price'].notna().sum():,} | on_request: {df['price_on_request'].sum():,}")

# =============================================================================
# CLEAN — floor → floor + total_floors
# =============================================================================

floor_parsed = df["floor"].apply(parse_floor)
df["floor"] = floor_parsed.apply(lambda x: x[0]).astype("Int64")
df["total_floors"] = floor_parsed.apply(lambda x: x[1]).astype("Int64")

print(f"floor — non-null: {df['floor'].notna().sum():,} | total_floors non-null: {df['total_floors'].notna().sum():,}")

# =============================================================================
# CLEAN — date_posted + date_modified
# =============================================================================

df["date_posted"] = df["date_posted"].apply(parse_bg_date)
df["date_modified"] = df["date_modified"].apply(parse_bg_date)

posted_parsed = df["date_posted"].notna().sum()
modified_parsed = df["date_modified"].notna().sum()
print(f"date_posted — parsed: {posted_parsed:,} | nulls: {df['date_posted'].isna().sum():,}")
print(f"date_modified — parsed: {modified_parsed:,} | nulls: {df['date_modified'].isna().sum():,}")

# =============================================================================
# CLEAN — gas
# =============================================================================

df["gas"] = df["gas"].map({"ДА": True, "НЕ": False})

print(f"gas — True: {df['gas'].sum():,} | False: {(df['gas'] == False).sum():,} | null: {df['gas'].isna().sum():,}")

# =============================================================================
# CLEAN — tec
# =============================================================================

unmapped_tec = set(df["tec"].dropna().unique()) - set(TEC_MAP.keys())
if unmapped_tec:
    raise ValueError(f"Unmapped tec values: {unmapped_tec}")

df["tec"] = df["tec"].map(TEC_MAP)

print(f"tec values: {df['tec'].value_counts(dropna=False).to_dict()}")

# =============================================================================
# CLEAN — construction_type
# =============================================================================

unmapped_ct = set(df["construction_type"].dropna().unique()) - set(CONSTRUCTION_TYPE_MAP.keys())
if unmapped_ct:
    raise ValueError(f"Unmapped construction_type values: {unmapped_ct}")

df["construction_type"] = df["construction_type"].map(CONSTRUCTION_TYPE_MAP)

print(f"construction_type values: {df['construction_type'].value_counts(dropna=False).to_dict()}")

# =============================================================================
# CLEAN — construction_status
# =============================================================================

unmapped_cs = set(df["construction_status"].dropna().unique()) - set(CONSTRUCTION_STATUS_MAP.keys())
if unmapped_cs:
    raise ValueError(f"Unmapped construction_status values: {unmapped_cs}")

df["construction_status"] = df["construction_status"].map(CONSTRUCTION_STATUS_MAP)

print(f"construction_status values: {df['construction_status'].value_counts(dropna=False).to_dict()}")

# =============================================================================
# CLEAN — poster_type
# =============================================================================

unmapped_pt = set(df["poster_type"].dropna().unique()) - set(POSTER_TYPE_MAP.keys())
if unmapped_pt:
    raise ValueError(f"Unmapped poster_type values: {unmapped_pt}")

df["poster_type"] = df["poster_type"].map(POSTER_TYPE_MAP)

print(f"poster_type values: {df['poster_type'].value_counts(dropna=False).to_dict()}")

# =============================================================================
# CLEAN — agency_phone
# Cast float64 → string, strip trailing .0
# =============================================================================

def clean_bg_phone(x):
    """
    Normalize a raw Bulgarian phone number to a canonical string.

    Bulgarian phone structure (all formats with leading 0):
        Mobile  : 10 digits — 08x-xxx-xxxx or 09x-xxx-xxxx
        Landline:  9 digits — 02-xxxxxxx (Sofia) or 0xx-xxxxxx (other cities)

    Raw data quirks handled:
        - Float artifact      : "888355153.0"   → strip ".0"
        - Country code 359    : "359888355153"  → strip "359", prepend "0"
        - Missing leading 0   : 9-digit mobile  "888355153"  → prepend "0" → 10 digits
                                8-digit landline "28212121"   → prepend "0" →  9 digits
        - Masked placeholders : numbers ending in 000000 (redacted by portal) → None
        - Junk/incomplete     : anything that isn't 9 or 10 digits after normalization → None
    """
    if pd.isna(x):
        return None

    s = str(x).strip()

    # Step 1 — strip float artifact (e.g. "885355153.0")
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]

    # Step 2 — keep digits only
    s = re.sub(r"\D", "", s)
    if not s:
        return None

    # Step 3 — strip country code 359
    # e.g. "359888355153" → "0888355153" (mobile, 10 digits)
    #      "35928212121"  → "028212121"  (Sofia landline, 9 digits)
    if s.startswith("359"):
        s = "0" + s[3:]

    # Step 4 — add missing leading 0
    # Mobile without leading 0:   9 digits starting with 8 or 9
    if len(s) == 9 and s[0] in "89":
        s = "0" + s  # → 10 digits
    # Landline without leading 0: 8 digits (any start digit)
    if len(s) == 8:
        s = "0" + s  # → 9 digits

    # Step 5 — accept only valid final lengths
    #   10 digits = mobile  (08x / 09x)
    #    9 digits = landline (02 / 03x / 05x / ...)
    if len(s) not in (9, 10):
        return None

    # Step 6 — reject masked placeholders (last 6 digits all zeros)
    # imot.bg redacts some numbers as e.g. "0885000000" (from "359885000000" raw)
    if s.endswith("000000"):
        return None

    return s

# Apply to all phone columns present in the DataFrame.
# 'phone' and 'contact_phone' may not exist in current scraper output —
# the guard handles this gracefully.
for col in PHONE_COLUMNS:
    if col in df.columns:
        df[col] = df[col].apply(clean_bg_phone)
        print(f"{col} — non-null: {df[col].notna().sum():,}")

print(f"agency_phone — non-null: {df['agency_phone'].notna().sum():,} | sample: {df['agency_phone'].dropna().iloc[0]}")

# =============================================================================
# TASK 9 — Extract bedrooms from property_type
# =============================================================================

unmapped_prop = set(df["property_type"].dropna().unique()) - set(PROPERTY_TYPE_MAP.keys())
if unmapped_prop:
    raise ValueError(f"Unmapped property_type values: {unmapped_prop}")

df["property_type_en"] = df["property_type"].map(lambda x: PROPERTY_TYPE_MAP.get(x, (None, None))[0])
df["bedrooms"] = df["property_type"].map(lambda x: PROPERTY_TYPE_MAP.get(x, (None, None))[1])
df["bedrooms"] = df["bedrooms"].astype("Int64")

print(f"bedrooms — value counts:\n{df['bedrooms'].value_counts(dropna=False)}")

# =============================================================================
# CLEAN — scraped_at
# Convert to Timestamp (already ISO format, just needs parsing)
# =============================================================================

df["scraped_at"] = pd.to_datetime(df["scraped_at"], utc=True)

print(f"scraped_at — min: {df['scraped_at'].min()} | max: {df['scraped_at'].max()}")

# =============================================================================
# SAVE
# =============================================================================

output_path = CLEAN_PATH / "df_clean.pkl"
df.to_pickle(output_path)

print(f"\ndf_clean saved to: {output_path}")
print(f"Shape: {df.shape}")
print(f"\nColumns: {list(df.columns)}")
