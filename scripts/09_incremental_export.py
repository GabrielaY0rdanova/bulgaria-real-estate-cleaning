"""Validate or apply one cleaned light-scraper run to PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import pandas as pd
import psycopg2
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.incremental_update import (
    DatabaseEntityWriter,
    apply_incremental_run,
    manifest_sha256,
    parse_actions,
)


WORK_PATH = Path("data/work")
CLEAN_PATH = Path("data/clean")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate an incremental export. Pass --apply to change PostgreSQL."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the run in one database transaction. Without this flag, no DB connection is made.",
    )
    return parser.parse_args()


def load_payload() -> tuple[dict, list, dict]:
    context_path = WORK_PATH / "run_context.json"
    actions_path = WORK_PATH / "df_actions.pkl"
    rows_path = CLEAN_PATH / "df_flagged.pkl"
    for path in (context_path, actions_path, rows_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required pipeline output is missing: {path}")

    context = json.loads(context_path.read_text(encoding="utf-8"))
    if context.get("mode") != "incremental":
        raise ValueError("09_incremental_export.py accepts incremental runs only")

    action_frame = pd.read_pickle(actions_path)
    row_frame = pd.read_pickle(rows_path)
    actions = parse_actions(action_frame.to_dict("records"))

    if row_frame["source_id"].duplicated().any():
        raise ValueError("Cleaned incremental rows contain duplicate source_id values")
    rows_by_source = {
        str(row["source_id"]): row
        for row in row_frame.to_dict("records")
    }
    expected_rows = {
        action.source_id for action in actions if action.action != "missing"
    }
    if set(rows_by_source) != expected_rows:
        missing = sorted(expected_rows - set(rows_by_source))
        extra = sorted(set(rows_by_source) - expected_rows)
        raise ValueError(
            f"Cleaned/action source_id mismatch. Missing={missing[:5]}, extra={extra[:5]}"
        )
    return context, actions, rows_by_source


def get_connection():
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    return psycopg2.connect(database_url) if database_url else psycopg2.connect()


def main() -> None:
    args = parse_args()
    context, actions, rows_by_source = load_payload()
    counts = {}
    for action in actions:
        counts[action.action] = counts.get(action.action, 0) + 1

    print(f"Validated run: {context['run_id']}")
    print(f"Actions: {len(actions):,} | {counts}")
    if not args.apply:
        print("Dry run only. PostgreSQL was not opened or changed.")
        print("Run again with --apply only after the database backup and migration are confirmed.")
        return

    manifest_path = Path(context["manifest_path"])
    connection = get_connection()
    try:
        apply_incremental_run(
            connection,
            run_id=context["run_id"],
            manifest_hash=manifest_sha256(manifest_path),
            actions=actions,
            apply_present=DatabaseEntityWriter(rows_by_source),
        )
    finally:
        connection.close()
    print(f"Applied incremental run: {context['run_id']}")


if __name__ == "__main__":
    main()
