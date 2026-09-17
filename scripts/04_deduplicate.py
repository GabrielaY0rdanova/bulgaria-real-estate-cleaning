# =============================================================================
# real_estate_cleaning — Prepare Listing Changes
# Purpose: Apply mode-specific change semantics after field cleaning.
#          Full rebuild deduplicates historical observations. Incremental mode
#          trusts the validated scraper action file.
# Run after: 03_clean_fields.py
# =============================================================================

import json
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.change_semantics import prepare_full_rebuild, prepare_incremental


CLEAN_PATH = Path("data/clean")
WORK_PATH = Path("data/work")


def main():
    clean_path = CLEAN_PATH / "df_clean.pkl"
    context_path = WORK_PATH / "run_context.json"
    if not clean_path.is_file():
        raise FileNotFoundError("Missing data/clean/df_clean.pkl. Run 03_clean_fields.py first.")
    if not context_path.is_file():
        raise FileNotFoundError("Missing data/work/run_context.json. Run 01_ingest.py first.")

    cleaned = pd.read_pickle(clean_path)
    with context_path.open(encoding="utf-8") as file:
        context = json.load(file)

    mode = context.get("mode")
    if mode == "full_rebuild":
        prepared = prepare_full_rebuild(cleaned)
    elif mode == "incremental":
        actions_path = WORK_PATH / "df_actions.pkl"
        if not actions_path.is_file():
            raise FileNotFoundError("Missing data/work/df_actions.pkl. Run 01_ingest.py first.")
        actions = pd.read_pickle(actions_path)
        prepared = prepare_incremental(cleaned, actions)
    else:
        raise ValueError(f"Unsupported cleaning mode: {mode!r}")

    CLEAN_PATH.mkdir(parents=True, exist_ok=True)
    prepared.listings.to_pickle(CLEAN_PATH / "df_dedup.pkl")
    prepared.price_history.to_pickle(CLEAN_PATH / "df_price_history_staging.pkl")
    prepared.missing_actions.to_pickle(CLEAN_PATH / "df_missing_actions.pkl")

    print(f"Mode: {mode}")
    print(f"Prepared listing rows: {len(prepared.listings):,}")
    print(f"Price changes: {len(prepared.price_history):,}")
    print(f"Missing actions: {len(prepared.missing_actions):,}")


if __name__ == "__main__":
    main()
