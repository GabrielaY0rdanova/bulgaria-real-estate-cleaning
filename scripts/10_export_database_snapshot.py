"""Export the current normalized PostgreSQL database to clean CSV snapshots."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

import psycopg2
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.database_snapshot import export_database_snapshot, require_database


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export a validated read-only database snapshot to CSV."
    )
    parser.add_argument(
        "--target-database",
        required=True,
        help="Database name that must match the active connection.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/clean",
        help="Destination for the normalized CSV snapshot.",
    )
    return parser.parse_args()


def get_connection():
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    return psycopg2.connect(database_url) if database_url else psycopg2.connect()


def main() -> None:
    args = parse_args()
    connection = get_connection()
    try:
        connection.set_session(readonly=True, autocommit=True)
        cursor = connection.cursor()
        try:
            require_database(cursor, args.target_database)
        finally:
            cursor.close()
        counts = export_database_snapshot(connection, args.output_dir)
    finally:
        connection.close()

    print(f"Exported database snapshot: {args.target_database}")
    for table, count in counts.items():
        print(f"  {table:<22} {count:>10,} rows")
    print(f"Snapshot directory: {Path(args.output_dir).resolve()}")


if __name__ == "__main__":
    main()
