import pytest

from pipeline.incremental_update import (
    apply_incremental_run,
    parse_actions,
    transliterate,
    _validate_database_state,
)


def row(**changes):
    result = {
        "source_id": "abc",
        "listing_id": "12",
        "action": "refreshed",
        "old_price": "100",
        "new_price": "100",
        "observed_at": "2026-09-17T08:00:00Z",
    }
    result.update(changes)
    return result


def test_parse_actions_accepts_new_without_listing_id():
    actions = parse_actions([row(action="new", listing_id="")])
    assert actions[0].listing_id is None


def test_parse_actions_accepts_pandas_nan_for_new_listing_id():
    actions = parse_actions([row(action="new", listing_id=float("nan"))])
    assert actions[0].listing_id is None


def test_parse_actions_requires_listing_id_for_existing_action():
    with pytest.raises(ValueError, match="has no listing_id"):
        parse_actions([row(action="missing", listing_id="")])


def test_parse_actions_rejects_duplicate_source_id():
    with pytest.raises(ValueError, match="Duplicate action"):
        parse_actions([row(), row()])


def test_parse_actions_rejects_fake_price_change():
    with pytest.raises(ValueError, match="identical prices"):
        parse_actions([row(action="changed")])


def test_database_state_matches_action_listing_id():
    action = parse_actions([row()])[0]
    _validate_database_state([action], {"abc": (12, "active", 100)})


def test_database_state_rejects_listing_id_mismatch():
    action = parse_actions([row()])[0]
    with pytest.raises(Exception, match="listing_id mismatch"):
        _validate_database_state([action], {"abc": (99, "active", 100)})


def test_reappeared_requires_inactive_database_status():
    action = parse_actions([row(action="reappeared")])[0]
    with pytest.raises(Exception, match="not inactive"):
        _validate_database_state([action], {"abc": (12, "active", 100)})


def test_new_action_must_not_exist_in_database():
    action = parse_actions([row(action="new", listing_id="")])[0]
    with pytest.raises(Exception, match="already exists"):
        _validate_database_state([action], {"abc": (12, "active", 100)})


def test_changed_price_must_start_from_database_price():
    action = parse_actions([row(action="changed", new_price="120")])[0]
    with pytest.raises(Exception, match="old_price mismatch"):
        _validate_database_state([action], {"abc": (12, "active", 90)})


def test_transliterate_matches_database_naming_rule():
    assert transliterate("София") == "Sofiya"


class TransactionCursor:
    def __init__(self, existing):
        self.existing = existing
        self.queries = []
        self.last_query = ""
        self.rowcount = 1
        self.closed = False

    def execute(self, query, params=None):
        self.last_query = " ".join(query.split())
        self.queries.append((self.last_query, params))

    def fetchone(self):
        if "RETURNING run_id" in self.last_query:
            return ("run-1",)
        return None

    def fetchall(self):
        if "FROM listings" in self.last_query and "FOR UPDATE" in self.last_query:
            return self.existing
        return []

    def close(self):
        self.closed = True


class TransactionConnection:
    def __init__(self, existing):
        self.cursor_instance = TransactionCursor(existing)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_apply_incremental_run_commits_missing_update_atomically():
    action = parse_actions([row(action="missing")])[0]
    connection = TransactionConnection([("abc", 12, "active", 100)])

    apply_incremental_run(
        connection,
        run_id="run-1",
        manifest_hash="a" * 64,
        actions=[action],
        apply_present=lambda *_args: None,
    )

    assert connection.committed is True
    assert connection.rolled_back is False
    assert connection.cursor_instance.closed is True
    assert any("SET status = 'inactive'" in query for query, _ in connection.cursor_instance.queries)
    assert any("SET status = 'complete'" in query for query, _ in connection.cursor_instance.queries)


def test_apply_incremental_run_rolls_back_writer_failure():
    action = parse_actions([row()])[0]
    connection = TransactionConnection([("abc", 12, "active", 100)])

    def fail(*_args):
        raise RuntimeError("write failed")

    with pytest.raises(RuntimeError, match="write failed"):
        apply_incremental_run(
            connection,
            run_id="run-1",
            manifest_hash="a" * 64,
            actions=[action],
            apply_present=fail,
        )

    assert connection.committed is False
    assert connection.rolled_back is True
    assert connection.cursor_instance.closed is True
