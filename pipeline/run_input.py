"""Validate and describe one completed light-scraper run directory."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path


SCHEMA_VERSION = 1
TRANSACTIONS = ("prodazhbi", "naemi")
ALLOWED_ACTIONS = {"new", "changed", "reappeared", "refreshed", "missing"}
ROW_REQUIRED_COLUMNS = {
    "region", "locality", "locality_type", "area", "property_type",
    "poster_type", "price", "listing_url", "source_id", "transaction_type",
    "scraped_at", "status",
}
ACTION_COLUMNS = (
    "source_id", "listing_id", "action", "old_price", "new_price", "observed_at",
)
SEEN_COLUMNS = ("source_id", "first_seen_at", "region_slug")


@dataclass(frozen=True)
class TransactionInput:
    transaction_type: str
    rows_path: Path
    actions_path: Path
    seen_ids_path: Path
    pass2_selection_path: Path


@dataclass(frozen=True)
class RunInput:
    run_id: str
    run_dir: Path
    manifest_path: Path
    manifest: dict
    transactions: dict[str, TransactionInput]


def load_completed_run(run_dir: str | Path) -> RunInput:
    """Load a run only after all safety and file-contract checks pass."""
    directory = Path(run_dir).resolve()
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Run manifest not found: {manifest_path}")

    with manifest_path.open(encoding="utf-8") as file:
        manifest = json.load(file)

    _validate_manifest(directory, manifest)
    inputs = {}
    for transaction_type in TRANSACTIONS:
        item = TransactionInput(
            transaction_type=transaction_type,
            rows_path=directory / f"{transaction_type}_rows.csv",
            actions_path=directory / f"{transaction_type}_actions.csv",
            seen_ids_path=directory / f"{transaction_type}_seen_ids.csv",
            pass2_selection_path=directory / f"{transaction_type}_pass2_selection.json",
        )
        _validate_transaction_files(item)
        inputs[transaction_type] = item

    return RunInput(
        run_id=manifest["run_id"],
        run_dir=directory,
        manifest_path=manifest_path,
        manifest=manifest,
        transactions=inputs,
    )


def _validate_manifest(run_dir: Path, manifest: object) -> None:
    if not isinstance(manifest, dict):
        raise ValueError("Run manifest must be a JSON object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported run manifest schema version")
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("Run manifest has no valid run_id")
    if run_dir.name != run_id:
        raise ValueError("Run directory name does not match manifest run_id")
    if manifest.get("status") != "complete":
        raise ValueError("Cleaning accepts only runs with manifest.status == 'complete'")
    if not manifest.get("finished_at"):
        raise ValueError("Completed run has no finished_at timestamp")

    states = manifest.get("transactions")
    if not isinstance(states, dict) or set(states) != set(TRANSACTIONS):
        raise ValueError("Manifest must contain exactly both transaction types")
    for transaction_type in TRANSACTIONS:
        state = states[transaction_type]
        if not isinstance(state, dict):
            raise ValueError(f"Invalid transaction state: {transaction_type}")
        if state.get("status") != "complete":
            raise ValueError(f"Transaction is not complete: {transaction_type}")
        if state.get("pass1_status") != "complete" or state.get("pass2_status") != "complete":
            raise ValueError(f"Both passes must be complete: {transaction_type}")
        if state.get("failed_units"):
            raise ValueError(f"Transaction has unresolved failures: {transaction_type}")
        if state.get("allow_missing_updates") is not True:
            raise ValueError(f"Missing updates are not authorised: {transaction_type}")
        if set(state.get("completed_regions", [])) != set(state.get("expected_regions", [])):
            raise ValueError(f"Region completion mismatch: {transaction_type}")


def _validate_transaction_files(item: TransactionInput) -> None:
    for path in (
        item.rows_path,
        item.actions_path,
        item.seen_ids_path,
        item.pass2_selection_path,
    ):
        if not path.is_file():
            raise FileNotFoundError(f"Required run file not found: {path}")

    rows = _read_csv(item.rows_path, required_columns=ROW_REQUIRED_COLUMNS)
    actions = _read_csv(item.actions_path, exact_columns=ACTION_COLUMNS)
    seen = _read_csv(item.seen_ids_path, exact_columns=SEEN_COLUMNS)
    selection = _read_selection(item.pass2_selection_path)

    row_ids = _unique_ids(rows, item.rows_path)
    action_ids = _unique_ids(actions, item.actions_path)
    seen_ids = _unique_ids(seen, item.seen_ids_path)
    _unique_ids(selection, item.pass2_selection_path)

    invalid_actions = {
        row.get("action") for row in actions
        if row.get("action") not in ALLOWED_ACTIONS
    }
    if invalid_actions:
        raise ValueError(f"Unsupported actions in {item.actions_path}: {sorted(invalid_actions)}")

    missing_ids = {
        row["source_id"] for row in actions if row.get("action") == "missing"
    }
    output_action_ids = action_ids - missing_ids
    if not output_action_ids.issubset(row_ids):
        absent = sorted(output_action_ids - row_ids)
        raise ValueError(f"Action IDs have no output row in {item.actions_path}: {absent[:5]}")
    if missing_ids & seen_ids:
        overlap = sorted(missing_ids & seen_ids)
        raise ValueError(f"Missing IDs also appear in seen IDs: {overlap[:5]}")


def _read_csv(
    path: Path,
    *,
    required_columns: set[str] | None = None,
    exact_columns: tuple[str, ...] | None = None,
) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames or []
        if exact_columns is not None and columns != list(exact_columns):
            raise ValueError(f"Unexpected columns in {path}: {columns}")
        if required_columns is not None and not required_columns.issubset(columns):
            missing = sorted(required_columns - set(columns))
            raise ValueError(f"Missing columns in {path}: {missing}")
        return list(reader)


def _read_selection(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as file:
        selection = json.load(file)
    if not isinstance(selection, list) or not all(isinstance(row, dict) for row in selection):
        raise ValueError(f"Pass 2 selection must be a JSON array of objects: {path}")
    return selection


def _unique_ids(rows: list[dict], path: Path) -> set[str]:
    ids = []
    for row in rows:
        source_id = str(row.get("source_id") or "").strip()
        if not source_id:
            raise ValueError(f"Missing source_id in {path}")
        ids.append(source_id)
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate source_id values in {path}")
    return set(ids)
