from io import StringIO

import pytest

from pipeline.database_snapshot import TABLE_SELECTS, count_csv_rows, require_database


class DatabaseCursor:
    def __init__(self, database):
        self.database = database
        self.query = None

    def execute(self, query):
        self.query = query

    def fetchone(self):
        return (self.database,)


def test_count_csv_rows_handles_quoted_line_breaks(tmp_path):
    path = tmp_path / "rows.csv"
    path.write_text('id,text\n1,"two\nlines"\n2,plain\n', encoding="utf-8")

    assert count_csv_rows(path) == 2


def test_require_database_accepts_exact_name():
    require_database(DatabaseCursor("bulgaria_real_estate"), "bulgaria_real_estate")


def test_require_database_rejects_different_name():
    with pytest.raises(ValueError, match="expected 'bulgaria_real_estate'"):
        require_database(DatabaseCursor("old_database"), "bulgaria_real_estate")


def test_snapshot_preserves_boolean_csv_contract():
    assert "AS price_on_request" in TABLE_SELECTS["listings"]
    assert "AS has_photos" in TABLE_SELECTS["listings"]
    assert "AS gas" in TABLE_SELECTS["properties"]
    assert "'True'" in TABLE_SELECTS["listings"]
    assert "'False'" in TABLE_SELECTS["properties"]
