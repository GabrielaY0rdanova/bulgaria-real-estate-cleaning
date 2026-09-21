"""Build durable cleaning inputs from one validated scraper run."""

from __future__ import annotations

import json
import os
import hashlib
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from pipeline.run_input import ACTION_COLUMNS, ROW_REQUIRED_COLUMNS, RunInput, load_completed_run


PHONE_COLUMNS = ("agency_phone", "phone", "contact_phone")
TRANSACTION_ENUM = {"prodazhbi": "sale", "naemi": "rental"}


def stage_completed_run(run_dir: str | Path, work_dir: str | Path) -> RunInput:
    """Validate one run and atomically persist its rows, actions, and context."""
    run = load_completed_run(run_dir)
    destination = Path(work_dir)
    destination.mkdir(parents=True, exist_ok=True)

    row_frames = []
    action_frames = []
    for transaction_type, item in run.transactions.items():
        row_columns = pd.read_csv(item.rows_path, nrows=0).columns
        dtype_map = {column: "string" for column in PHONE_COLUMNS if column in row_columns}
        rows = pd.read_csv(item.rows_path, low_memory=False, dtype=dtype_map)
        rows["transaction_type"] = TRANSACTION_ENUM[transaction_type]
        row_frames.append(rows)

        actions = pd.read_csv(item.actions_path, low_memory=False, dtype={"source_id": "string"})
        actions["transaction_type"] = TRANSACTION_ENUM[transaction_type]
        action_frames.append(actions)

    staging = _concat_frames(row_frames)
    actions = _concat_frames(action_frames)

    unknown_mask = staging["property_type"].eq("unknown")
    if unknown_mask.any():
        raise ValueError(
            f"Validated run contains {int(unknown_mask.sum())} rows with property_type='unknown'"
        )
    if staging["source_id"].duplicated().any():
        raise ValueError("Combined run rows contain duplicate source IDs across transactions")

    _atomic_pickle(staging, destination / "df_staging.pkl")
    _atomic_pickle(actions, destination / "df_actions.pkl")
    _atomic_json(
        {
            "schema_version": 1,
            "mode": "incremental",
            "run_id": run.run_id,
            "run_dir": str(run.run_dir),
            "manifest_path": str(run.manifest_path),
            "row_count": len(staging),
            "action_count": len(actions),
        },
        destination / "run_context.json",
    )
    return run


def _concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Combine transaction files without pandas' empty-frame dtype warning."""
    nonempty = [frame for frame in frames if not frame.empty]
    if nonempty:
        return pd.concat(nonempty, ignore_index=True)
    if not frames:
        raise ValueError("No transaction frames were loaded")
    return frames[0].iloc[0:0].copy()


def stage_full_rebuild(raw_files: list[str | Path], work_dir: str | Path) -> dict:
    """Stage explicitly ordered historical raw files for a full rebuild."""
    if not raw_files:
        raise ValueError("At least one raw file is required for a full rebuild")

    paths = [Path(path).resolve() for path in raw_files]
    if len(paths) != len(set(paths)):
        raise ValueError("The full rebuild file list contains duplicate paths")

    frames = []
    sources = []
    transaction_counts = {"sale": 0, "rental": 0}
    source_transactions = [_transaction_from_filename(path) for path in paths]
    source_dates = [_date_from_filename(path) for path in paths]
    if source_dates != sorted(source_dates):
        raise ValueError("Full rebuild files must be supplied in chronological order")

    for position, (path, source_date, transaction_type) in enumerate(
        zip(paths, source_dates, source_transactions), start=1
    ):
        if not path.is_file():
            raise FileNotFoundError(f"Raw input file not found: {path}")
        columns = list(pd.read_csv(path, nrows=0).columns)
        missing_columns = sorted(ROW_REQUIRED_COLUMNS - set(columns))
        if missing_columns:
            raise ValueError(f"Missing columns in {path}: {missing_columns}")
        dtype_map = {column: "string" for column in PHONE_COLUMNS if column in columns}
        frame = pd.read_csv(path, low_memory=False, dtype=dtype_map)
        frame["transaction_type"] = transaction_type
        transaction_counts[transaction_type] += len(frame)
        frames.append(frame)
        sources.append({
            "position": position,
            "path": str(path),
            "transaction_type": transaction_type,
            "source_date": source_date.date().isoformat(),
            "row_count": len(frame),
            "sha256": _sha256(path),
        })

    if not all(transaction_counts.values()):
        raise ValueError("A full rebuild requires both sales and rental input files")

    staging = pd.concat(frames, ignore_index=True)
    unknown_mask = staging["property_type"].eq("unknown")
    rejected_unknown = int(unknown_mask.sum())
    if rejected_unknown:
        staging = staging.loc[~unknown_mask].reset_index(drop=True)

    actions = pd.DataFrame(columns=[*ACTION_COLUMNS, "transaction_type"])
    destination = Path(work_dir)
    destination.mkdir(parents=True, exist_ok=True)
    _atomic_pickle(staging, destination / "df_staging.pkl")
    _atomic_pickle(actions, destination / "df_actions.pkl")
    context = {
        "schema_version": 1,
        "mode": "full_rebuild",
        "run_id": None,
        "sources": sources,
        "row_count_before_rejections": sum(transaction_counts.values()),
        "rejected_unknown_rows": rejected_unknown,
        "row_count": len(staging),
        "action_count": 0,
    }
    _atomic_json(context, destination / "run_context.json")
    return context


def _transaction_from_filename(path: Path) -> str:
    name = path.name.lower()
    if name.startswith("prodazhbi_"):
        return "sale"
    if name.startswith("naemi_"):
        return "rental"
    raise ValueError(
        f"Cannot determine transaction type from filename: {path.name}. "
        "Expected prodazhbi_*.csv or naemi_*.csv."
    )


def _date_from_filename(path: Path) -> datetime:
    match = re.search(r"_(\d{2}_\d{2}_\d{4})\.csv$", path.name.lower())
    if not match:
        raise ValueError(f"Raw filename has no DD_MM_YYYY date: {path.name}")
    try:
        return datetime.strptime(match.group(1), "%d_%m_%Y")
    except ValueError as error:
        raise ValueError(f"Raw filename has an invalid date: {path.name}") from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_pickle(frame: pd.DataFrame, path: Path) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        frame.to_pickle(temp_path)
        os.replace(temp_path, path)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise


def _atomic_json(payload: dict, path: Path) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    except OSError:
        temp_path.unlink(missing_ok=True)
        raise
