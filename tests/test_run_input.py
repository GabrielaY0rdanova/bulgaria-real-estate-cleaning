import csv
import json

import pandas as pd
import pytest

from pipeline.run_input import ACTION_COLUMNS, SEEN_COLUMNS, load_completed_run
from pipeline.staging import stage_completed_run, stage_full_rebuild


ROW_COLUMNS = [
    "region", "locality", "locality_type", "area", "property_type",
    "poster_type", "price", "listing_url", "source_id", "transaction_type",
    "scraped_at", "status",
]


def _write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _make_run(tmp_path, status="complete"):
    run_dir = tmp_path / "20260917T080000Z"
    run_dir.mkdir()
    state = {
        "status": "complete",
        "pass1_status": "complete",
        "pass2_status": "complete",
        "expected_regions": ["region-a"],
        "completed_regions": ["region-a"],
        "failed_units": [],
        "allow_missing_updates": True,
    }
    manifest = {
        "schema_version": 1,
        "run_id": run_dir.name,
        "status": status,
        "finished_at": "2026-09-17T10:00:00+00:00" if status == "complete" else None,
        "transactions": {"prodazhbi": state.copy(), "naemi": state.copy()},
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    for transaction in ("prodazhbi", "naemi"):
        _write_csv(
            run_dir / f"{transaction}_rows.csv", ROW_COLUMNS,
            [{
                "region": "София", "locality": "София", "locality_type": "град",
                "area": "Център", "property_type": "2-СТАЕН", "poster_type": "агенция",
                "price": "100000", "listing_url": "https://example.test/1",
                "source_id": f"{transaction}-row", "transaction_type": transaction,
                "scraped_at": "2026-09-17T08:00:00+00:00", "status": "active",
            }],
        )
        _write_csv(
            run_dir / f"{transaction}_actions.csv", ACTION_COLUMNS,
            [{
                "source_id": f"{transaction}-row", "listing_id": "",
                "action": "new", "old_price": "", "new_price": "100000",
                "observed_at": "2026-09-17T08:00:00+00:00",
            }],
        )
        _write_csv(
            run_dir / f"{transaction}_seen_ids.csv", SEEN_COLUMNS,
            [{
                "source_id": f"{transaction}-row",
                "first_seen_at": "2026-09-17T08:00:00+00:00",
                "region_slug": "region-a",
            }],
        )
        (run_dir / f"{transaction}_pass2_selection.json").write_text(
            "[]", encoding="utf-8"
        )
    return run_dir


def test_complete_consistent_run_is_accepted(tmp_path):
    run_dir = _make_run(tmp_path)

    result = load_completed_run(run_dir)

    assert result.run_id == run_dir.name
    assert set(result.transactions) == {"prodazhbi", "naemi"}


def test_incomplete_run_is_rejected(tmp_path):
    run_dir = _make_run(tmp_path, status="partial")

    with pytest.raises(ValueError, match="status == 'complete'"):
        load_completed_run(run_dir)


def test_manifest_run_id_must_match_directory(tmp_path):
    run_dir = _make_run(tmp_path)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["run_id"] = "different"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="directory name"):
        load_completed_run(run_dir)


def test_missing_required_file_is_rejected(tmp_path):
    run_dir = _make_run(tmp_path)
    (run_dir / "naemi_actions.csv").unlink()

    with pytest.raises(FileNotFoundError, match="naemi_actions"):
        load_completed_run(run_dir)


def test_duplicate_seen_id_is_rejected(tmp_path):
    run_dir = _make_run(tmp_path)
    path = run_dir / "prodazhbi_seen_ids.csv"
    _write_csv(path, SEEN_COLUMNS, [
        {"source_id": "same", "first_seen_at": "a", "region_slug": "one"},
        {"source_id": "same", "first_seen_at": "b", "region_slug": "two"},
    ])

    with pytest.raises(ValueError, match="Duplicate source_id"):
        load_completed_run(run_dir)


def test_non_missing_action_requires_output_row(tmp_path):
    run_dir = _make_run(tmp_path)
    path = run_dir / "prodazhbi_actions.csv"
    _write_csv(path, ACTION_COLUMNS, [{
        "source_id": "no-row", "listing_id": "1", "action": "changed",
        "old_price": "10", "new_price": "20", "observed_at": "now",
    }])

    with pytest.raises(ValueError, match="no output row"):
        load_completed_run(run_dir)


def test_missing_action_cannot_also_be_seen(tmp_path):
    run_dir = _make_run(tmp_path)
    actions_path = run_dir / "prodazhbi_actions.csv"
    seen_path = run_dir / "prodazhbi_seen_ids.csv"
    _write_csv(actions_path, ACTION_COLUMNS, [{
        "source_id": "overlap", "listing_id": "1", "action": "missing",
        "old_price": "", "new_price": "", "observed_at": "now",
    }])
    _write_csv(seen_path, SEEN_COLUMNS, [{
        "source_id": "overlap", "first_seen_at": "now", "region_slug": "one",
    }])

    with pytest.raises(ValueError, match="also appear in seen"):
        load_completed_run(run_dir)


def test_completed_run_is_staged_once_with_normalised_transaction_types(tmp_path):
    run_dir = _make_run(tmp_path)
    work_dir = tmp_path / "work"

    result = stage_completed_run(run_dir, work_dir)

    staging = pd.read_pickle(work_dir / "df_staging.pkl")
    actions = pd.read_pickle(work_dir / "df_actions.pkl")
    context = json.loads((work_dir / "run_context.json").read_text(encoding="utf-8"))
    assert result.run_id == run_dir.name
    assert set(staging["transaction_type"]) == {"sale", "rental"}
    assert set(actions["transaction_type"]) == {"sale", "rental"}
    assert context["run_id"] == run_dir.name
    assert context["row_count"] == 2
    assert context["action_count"] == 2


def test_full_rebuild_uses_explicit_file_order_and_records_hashes(tmp_path):
    sales = tmp_path / "prodazhbi_01_04_2026.csv"
    rentals = tmp_path / "naemi_02_04_2026.csv"
    base = {
        "region": "София", "locality": "София", "locality_type": "град",
        "area": "Център", "property_type": "2-СТАЕН", "poster_type": "агенция",
        "price": "100000", "listing_url": "https://example.test/1",
        "scraped_at": "2026-04-01T08:00:00+00:00", "status": "active",
    }
    _write_csv(sales, ROW_COLUMNS, [{**base, "source_id": "sale-1", "transaction_type": "wrong"}])
    _write_csv(rentals, ROW_COLUMNS, [{**base, "source_id": "rent-1", "transaction_type": "wrong"}])

    context = stage_full_rebuild([sales, rentals], tmp_path / "work")

    staging = pd.read_pickle(tmp_path / "work" / "df_staging.pkl")
    assert list(staging["transaction_type"]) == ["sale", "rental"]
    assert [source["path"] for source in context["sources"]] == [
        str(sales.resolve()), str(rentals.resolve())
    ]
    assert all(len(source["sha256"]) == 64 for source in context["sources"])


def test_full_rebuild_requires_both_transaction_types(tmp_path):
    sales = tmp_path / "prodazhbi_01_04_2026.csv"
    row = {column: "value" for column in ROW_COLUMNS}
    row.update({
        "source_id": "sale-1", "property_type": "2-СТАЕН",
        "transaction_type": "prodazhbi",
    })
    _write_csv(sales, ROW_COLUMNS, [row])

    with pytest.raises(ValueError, match="both sales and rental"):
        stage_full_rebuild([sales], tmp_path / "work")


def test_full_rebuild_rejects_ambiguous_filename(tmp_path):
    path = tmp_path / "listings.csv"
    _write_csv(path, ROW_COLUMNS, [])

    with pytest.raises(ValueError, match="Cannot determine transaction type"):
        stage_full_rebuild([path], tmp_path / "work")


def test_full_rebuild_rejects_non_chronological_order(tmp_path):
    july = tmp_path / "prodazhbi_27_07_2026.csv"
    april = tmp_path / "naemi_10_04_2026.csv"
    row = {column: "value" for column in ROW_COLUMNS}
    row.update({"source_id": "id", "property_type": "2-СТАЕН"})
    _write_csv(july, ROW_COLUMNS, [row])
    _write_csv(april, ROW_COLUMNS, [{**row, "source_id": "id-2"}])

    with pytest.raises(ValueError, match="chronological order"):
        stage_full_rebuild([july, april], tmp_path / "work")
