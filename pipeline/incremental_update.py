"""Transactional safety layer for applying one light-scraper run."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import math
from pathlib import Path
from typing import Callable, Iterable, Mapping


ALLOWED_ACTIONS = {"new", "changed", "reappeared", "refreshed", "missing"}
EXISTING_ACTIONS = ALLOWED_ACTIONS - {"new"}


class IncrementalUpdateError(RuntimeError):
    """Raised when a run cannot be applied without risking inconsistent data."""


@dataclass(frozen=True)
class Action:
    source_id: str
    listing_id: int | None
    action: str
    old_price: object
    new_price: object
    observed_at: object


def manifest_sha256(path: str | Path) -> str:
    """Return the hash stored in the run ledger for auditability."""
    return sha256(Path(path).read_bytes()).hexdigest()


def parse_actions(rows: Iterable[Mapping]) -> list[Action]:
    """Validate action rows before a database transaction starts."""
    actions: list[Action] = []
    seen: set[str] = set()
    for position, row in enumerate(rows, start=1):
        source_id = str(row.get("source_id") or "").strip()
        action = str(row.get("action") or "").strip()
        if not source_id:
            raise ValueError(f"Action row {position} has no source_id")
        if source_id in seen:
            raise ValueError(f"Duplicate action for source_id: {source_id}")
        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"Unsupported action for {source_id}: {action}")

        listing_id = _optional_int(row.get("listing_id"))
        old_price = _optional_price(row.get("old_price"))
        new_price = _optional_price(row.get("new_price"))
        if action == "new" and listing_id is not None:
            raise ValueError(f"New action already has listing_id: {source_id}")
        if action in EXISTING_ACTIONS and listing_id is None:
            raise ValueError(f"{action} action has no listing_id: {source_id}")
        if action == "changed" and _same_value(old_price, new_price):
            action = "refreshed"
        if row.get("observed_at") in (None, ""):
            raise ValueError(f"Action has no observed_at: {source_id}")

        seen.add(source_id)
        actions.append(Action(
            source_id=source_id,
            listing_id=listing_id,
            action=action,
            old_price=old_price,
            new_price=new_price,
            observed_at=row.get("observed_at"),
        ))
    return actions


def apply_incremental_run(
    connection,
    *,
    run_id: str,
    manifest_hash: str,
    actions: Iterable[Action],
    apply_present: Callable[[object, Action], None],
) -> None:
    """Apply one run atomically without truncating any production table.

    ``apply_present`` must insert or update the normalized property, contact,
    listing and feature rows for every action except ``missing``. It receives
    the same transaction cursor, so any failure rolls back the whole run.
    """
    action_list = list(actions)
    if not run_id.strip():
        raise ValueError("run_id cannot be empty")
    if len(manifest_hash) != 64:
        raise ValueError("manifest_hash must be a SHA-256 hex digest")

    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtext('real_estate_incremental_update'))"
        )
        _claim_run(cursor, run_id, manifest_hash, len(action_list))
        existing = _lock_existing_listings(cursor, action_list)
        _validate_database_state(action_list, existing)

        for action in action_list:
            if action.action == "missing":
                _mark_missing(cursor, action)
                continue

            apply_present(cursor, action)
            if action.action == "changed" or (
                action.action == "reappeared"
                and not _same_value(action.old_price, action.new_price)
            ):
                _record_price_change(cursor, action)
            if action.action == "reappeared":
                _mark_reappeared(cursor, action)

        cursor.execute(
            """
            UPDATE pipeline_runs
               SET status = 'complete', finished_at = clock_timestamp()
             WHERE run_id = %s
            """,
            (run_id,),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def _claim_run(cursor, run_id: str, manifest_hash: str, action_count: int) -> None:
    cursor.execute(
        """
        INSERT INTO pipeline_runs (
            run_id, mode, source_manifest_sha256, status, action_count
        ) VALUES (%s, 'incremental', %s, 'running', %s)
        ON CONFLICT (run_id) DO NOTHING
        RETURNING run_id
        """,
        (run_id, manifest_hash, action_count),
    )
    if cursor.fetchone() is None:
        raise IncrementalUpdateError(f"Run has already been claimed: {run_id}")


def _lock_existing_listings(cursor, actions: list[Action]) -> dict[str, tuple[int, str, object]]:
    source_ids = [action.source_id for action in actions]
    if not source_ids:
        return {}
    cursor.execute(
        """
        SELECT source_id, listing_id, status::text, price
          FROM listings
         WHERE source_id = ANY(%s)
         FOR UPDATE
        """,
        (source_ids,),
    )
    return {
        source_id: (listing_id, status, price)
        for source_id, listing_id, status, price in cursor.fetchall()
    }


def _validate_database_state(
    actions: list[Action], existing: dict[str, tuple[int, str, object]]
) -> None:
    for action in actions:
        current = existing.get(action.source_id)
        if action.action == "new":
            if current is not None:
                raise IncrementalUpdateError(
                    f"New action already exists in listings: {action.source_id}"
                )
            continue
        if current is None:
            raise IncrementalUpdateError(
                f"Existing action is missing from listings: {action.source_id}"
            )
        database_id, status, database_price = current
        if database_id != action.listing_id:
            raise IncrementalUpdateError(
                f"listing_id mismatch for {action.source_id}: "
                f"action={action.listing_id}, database={database_id}"
            )
        if action.action == "reappeared" and status != "inactive":
            raise IncrementalUpdateError(
                f"Reappeared listing is not inactive: {action.source_id}"
            )
        if action.action in {"changed", "reappeared"} and not _same_value(
            action.old_price, database_price
        ):
            raise IncrementalUpdateError(
                f"old_price mismatch for {action.source_id}: "
                f"action={action.old_price}, database={database_price}"
            )


def _mark_missing(cursor, action: Action) -> None:
    cursor.execute(
        """
        UPDATE listings
           SET status = 'inactive',
               status_changed_at = CASE
                   WHEN status IS DISTINCT FROM 'inactive'::listing_status THEN %s
                   ELSE status_changed_at
               END,
               date_last_checked = GREATEST(date_last_checked, %s)
         WHERE listing_id = %s AND source_id = %s
        """,
        (action.observed_at, action.observed_at, action.listing_id, action.source_id),
    )
    if cursor.rowcount != 1:
        raise IncrementalUpdateError(f"Could not mark listing missing: {action.source_id}")


def _mark_reappeared(cursor, action: Action) -> None:
    cursor.execute(
        """
        UPDATE listings
           SET status = 'active', status_changed_at = %s
         WHERE listing_id = %s AND source_id = %s
        """,
        (action.observed_at, action.listing_id, action.source_id),
    )
    if cursor.rowcount != 1:
        raise IncrementalUpdateError(f"Could not reactivate listing: {action.source_id}")


def _record_price_change(cursor, action: Action) -> None:
    cursor.execute(
        """
        INSERT INTO price_history (listing_id, old_price, new_price, changed_at)
        VALUES (%s, %s, %s, %s)
        """,
        (action.listing_id, action.old_price, action.new_price, action.observed_at),
    )


def _optional_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid listing_id: {value}") from exc
    if math.isnan(number):
        return None
    if not math.isfinite(number):
        raise ValueError(f"Invalid listing_id: {value}")
    if not number.is_integer():
        raise ValueError(f"Invalid listing_id: {value}")
    return int(number)


def _optional_price(value) -> Decimal | None:
    if _is_missing(value):
        return None
    text = str(value).strip()
    if "запитване" in text.lower():
        return None
    cleaned = "".join(text.split()).replace("€", "").replace("$", "")
    try:
        number = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid price: {value}") from exc
    if not number.is_finite():
        raise ValueError(f"Invalid price: {value}")
    return number


def _same_value(left, right) -> bool:
    left_missing = _is_missing(left)
    right_missing = _is_missing(right)
    if left_missing and right_missing:
        return True
    if left_missing or right_missing:
        return False
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except InvalidOperation:
        return str(left) == str(right)


def _is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value == "":
        return True
    try:
        return bool(math.isnan(value))
    except (TypeError, ValueError):
        return False


class DatabaseEntityWriter:
    """Insert or update the normalized rows for listings seen in a run."""

    def __init__(self, rows_by_source: Mapping[str, Mapping]):
        self.rows_by_source = rows_by_source

    def __call__(self, cursor, action: Action) -> None:
        try:
            row = self.rows_by_source[action.source_id]
        except KeyError as exc:
            raise IncrementalUpdateError(
                f"No cleaned row for action: {action.source_id}"
            ) from exc

        geo_id = self._resolve_geography(cursor, row)
        property_type_id = self._lookup_id(
            cursor, "property_types", "property_type_id", "name_bg", row["property_type"]
        )
        construction_type_id = None
        if _value(row.get("construction_type")) is not None:
            construction_type_id = self._lookup_id(
                cursor,
                "construction_types",
                "construction_type_id",
                "name_en",
                row["construction_type"],
            )
        contact_id = self._resolve_contact(cursor, row)

        if action.action == "new":
            property_id = self._insert_property(
                cursor, row, geo_id, property_type_id, construction_type_id
            )
            listing_id = self._insert_listing(cursor, row, property_id, contact_id)
        else:
            cursor.execute(
                "SELECT property_id FROM listings WHERE listing_id = %s",
                (action.listing_id,),
            )
            result = cursor.fetchone()
            if result is None:
                raise IncrementalUpdateError(
                    f"Listing disappeared during update: {action.source_id}"
                )
            property_id = result[0]
            listing_id = action.listing_id
            self._update_property(
                cursor, property_id, row, geo_id, property_type_id, construction_type_id
            )
            self._update_listing(cursor, listing_id, row, contact_id)

        self._replace_features(cursor, property_id, row.get("features"))

    @staticmethod
    def _lookup_id(cursor, table: str, id_column: str, name_column: str, name) -> int:
        allowed = {
            ("property_types", "property_type_id", "name_bg"),
            ("construction_types", "construction_type_id", "name_en"),
            ("features", "feature_id", "name_bg"),
        }
        if (table, id_column, name_column) not in allowed:
            raise ValueError("Unsupported lookup")
        cursor.execute(
            f"SELECT {id_column} FROM {table} WHERE {name_column} = %s",
            (_value(name),),
        )
        result = cursor.fetchone()
        if result is None:
            raise IncrementalUpdateError(
                f"Lookup value is missing from {table}.{name_column}: {name}"
            )
        return result[0]

    def _resolve_geography(self, cursor, row: Mapping) -> int:
        region = _required_text(row, "region")
        locality = _required_text(row, "locality")
        locality_type = _value(row.get("locality_type"))
        area = _value(row.get("area"))

        region_id = self._get_or_create_geo(
            cursor, parent_id=None, level="region", name=region, locality_type="city"
        )
        locality_id = self._get_or_create_geo(
            cursor,
            parent_id=region_id,
            level="locality",
            name=locality,
            locality_type=locality_type,
        )
        if area is None:
            return locality_id
        return self._get_or_create_geo(
            cursor, parent_id=locality_id, level="area", name=str(area), locality_type=None
        )

    @staticmethod
    def _get_or_create_geo(
        cursor, *, parent_id: int | None, level: str, name: str, locality_type
    ) -> int:
        cursor.execute(
            """
            SELECT geo_id
              FROM geographies
             WHERE parent_id IS NOT DISTINCT FROM %s
               AND level = %s AND name_bg = %s
            """,
            (parent_id, level, name),
        )
        result = cursor.fetchone()
        if result is not None:
            return result[0]
        cursor.execute(
            """
            INSERT INTO geographies (parent_id, level, name_bg, name_en, locality_type)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING geo_id
            """,
            (parent_id, level, name, transliterate(name), locality_type),
        )
        return cursor.fetchone()[0]

    @staticmethod
    def _resolve_contact(cursor, row: Mapping) -> int:
        contact_type = _required_text(row, "poster_type")
        name = _value(row.get("agency_name"))
        phone = _value(row.get("agency_phone"))
        if contact_type == "owner" and name is None and phone is None:
            return DatabaseEntityWriter._insert_contact(cursor, contact_type, name, phone)
        cursor.execute(
            """
            SELECT contact_id
              FROM contacts
             WHERE contact_type = %s
               AND name IS NOT DISTINCT FROM %s
               AND phone IS NOT DISTINCT FROM %s
             ORDER BY contact_id
             LIMIT 1
            """,
            (contact_type, name, phone),
        )
        result = cursor.fetchone()
        if result is not None:
            return result[0]
        return DatabaseEntityWriter._insert_contact(cursor, contact_type, name, phone)

    @staticmethod
    def _insert_contact(cursor, contact_type, name, phone) -> int:
        cursor.execute(
            """
            INSERT INTO contacts (contact_type, name, phone)
            VALUES (%s, %s, %s)
            RETURNING contact_id
            """,
            (contact_type, name, phone),
        )
        return cursor.fetchone()[0]

    @staticmethod
    def _property_values(row, geo_id, property_type_id, construction_type_id) -> tuple:
        return (
            geo_id,
            property_type_id,
            construction_type_id,
            _value(row.get("bedrooms")),
            _value(row.get("area_m2")),
            _value(row.get("floor")),
            _value(row.get("total_floors")),
            _value(row.get("construction_status")),
            _value(row.get("year_built")),
            _value(row.get("gas")),
            _value(row.get("tec")),
        )

    def _insert_property(self, cursor, row, geo_id, property_type_id, construction_type_id):
        cursor.execute(
            """
            INSERT INTO properties (
                geo_id, property_type_id, construction_type_id, bedrooms,
                area_m2, floor, total_floors, construction_status,
                year_built, gas, tec
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING property_id
            """,
            self._property_values(row, geo_id, property_type_id, construction_type_id),
        )
        return cursor.fetchone()[0]

    def _update_property(
        self, cursor, property_id, row, geo_id, property_type_id, construction_type_id
    ) -> None:
        cursor.execute(
            """
            UPDATE properties
               SET geo_id = %s, property_type_id = %s, construction_type_id = %s,
                   bedrooms = %s, area_m2 = %s, floor = %s, total_floors = %s,
                   construction_status = %s, year_built = %s, gas = %s, tec = %s
             WHERE property_id = %s
            """,
            self._property_values(row, geo_id, property_type_id, construction_type_id)
            + (property_id,),
        )
        if cursor.rowcount != 1:
            raise IncrementalUpdateError(f"Property not found: {property_id}")

    @staticmethod
    def _listing_values(row, property_id, contact_id) -> tuple:
        scraped_at = _value(row.get("scraped_at"))
        return (
            _required_text(row, "source_id"),
            property_id,
            contact_id,
            _value(row.get("transaction_type")),
            _value(row.get("listing_tier")),
            _required_text(row, "listing_url"),
            _value(row.get("price")),
            _value(row.get("price_on_request")),
            _value(row.get("date_posted")),
            _value(row.get("date_modified")),
            _value(row.get("has_photos")),
            "active",
            scraped_at,
            scraped_at,
        )

    def _insert_listing(self, cursor, row, property_id, contact_id):
        cursor.execute(
            """
            INSERT INTO listings (
                source_id, property_id, contact_id, transaction_type, listing_tier,
                listing_url, price, price_on_request, date_posted, date_modified,
                has_photos, status, scraped_at, date_last_checked
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING listing_id
            """,
            self._listing_values(row, property_id, contact_id),
        )
        return cursor.fetchone()[0]

    def _update_listing(self, cursor, listing_id, row, contact_id) -> None:
        values = self._listing_values(row, property_id=0, contact_id=contact_id)
        cursor.execute(
            """
            UPDATE listings
               SET contact_id = %s, transaction_type = %s, listing_tier = %s,
                   listing_url = %s, price = %s, price_on_request = %s,
                   date_posted = %s, date_modified = %s, has_photos = %s,
                   scraped_at = %s, date_last_checked = %s
             WHERE listing_id = %s AND source_id = %s
            """,
            (
                values[2], values[3], values[4], values[5], values[6], values[7],
                values[8], values[9], values[10], values[12], values[13],
                listing_id, values[0],
            ),
        )
        if cursor.rowcount != 1:
            raise IncrementalUpdateError(f"Listing not found: {row['source_id']}")

    def _replace_features(self, cursor, property_id: int, raw_features) -> None:
        cursor.execute("DELETE FROM property_features WHERE property_id = %s", (property_id,))
        value = _value(raw_features)
        if value is None:
            return
        for feature in dict.fromkeys(part.strip() for part in str(value).split(",") if part.strip()):
            feature_id = self._lookup_id(
                cursor, "features", "feature_id", "name_bg", feature
            )
            cursor.execute(
                """
                INSERT INTO property_features (property_id, feature_id)
                VALUES (%s, %s)
                """,
                (property_id, feature_id),
            )


def _value(value):
    """Convert pandas/NumPy missing scalars to DB NULL without importing pandas."""
    if value is None:
        return None
    if type(value).__name__ == "NAType":
        return None
    try:
        if value != value:
            return None
    except (TypeError, ValueError):
        pass
    return value


def _required_text(row: Mapping, column: str) -> str:
    value = _value(row.get(column))
    if value is None or not str(value).strip():
        raise IncrementalUpdateError(f"Cleaned row has no {column}")
    return str(value).strip()


_CYR_TO_LAT = str.maketrans({
    "А": "A", "а": "a", "Б": "B", "б": "b", "В": "V", "в": "v",
    "Г": "G", "г": "g", "Д": "D", "д": "d", "Е": "E", "е": "e",
    "Ж": "Zh", "ж": "zh", "З": "Z", "з": "z", "И": "I", "и": "i",
    "Й": "Y", "й": "y", "К": "K", "к": "k", "Л": "L", "л": "l",
    "М": "M", "м": "m", "Н": "N", "н": "n", "О": "O", "о": "o",
    "П": "P", "п": "p", "Р": "R", "р": "r", "С": "S", "с": "s",
    "Т": "T", "т": "t", "У": "U", "у": "u", "Ф": "F", "ф": "f",
    "Х": "H", "х": "h", "Ц": "Ts", "ц": "ts", "Ч": "Ch", "ч": "ch",
    "Ш": "Sh", "ш": "sh", "Щ": "Sht", "щ": "sht", "Ъ": "A", "ъ": "a",
    "Ь": "Y", "ь": "y", "Ю": "Yu", "ю": "yu", "Я": "Ya", "я": "ya",
})


def transliterate(text: str) -> str:
    return text.translate(_CYR_TO_LAT)
