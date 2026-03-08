"""SQLite-backed price history storage for the Undermine Exchange monitor.

Stores and queries historical price data so the monitor can detect
new all-time-high prices for tracked items.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER NOT NULL,
    realm       TEXT    NOT NULL,
    price_copper INTEGER NOT NULL,
    recorded_at TEXT    NOT NULL
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_price_history_item_realm
    ON price_history (item_id, realm);
"""


class PriceStorage:
    """Manages price history persistence in a local SQLite database.

    Args:
        db_path: Filesystem path for the SQLite database file.
    """

    def __init__(self, db_path: str = "data/prices.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Initialising price storage at %s", self._db_path)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        """Create the ``price_history`` table and index if they do not exist."""
        cursor = self._conn.cursor()
        cursor.execute(_CREATE_TABLE_SQL)
        cursor.execute(_CREATE_INDEX_SQL)
        self._conn.commit()
        logger.debug("Database tables verified")

    def get_highest_price(self, item_id: int, realm: str) -> int | None:
        """Return the highest recorded price for an item on a realm.

        Args:
            item_id: The numeric item identifier.
            realm: The realm slug (e.g. ``"us-dalaran"``).

        Returns:
            The highest price in copper, or ``None`` if no records exist.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT MAX(price_copper) AS max_price "
            "FROM price_history "
            "WHERE item_id = ? AND realm = ?",
            (item_id, realm),
        )
        row = cursor.fetchone()
        if row and row["max_price"] is not None:
            return int(row["max_price"])
        return None

    def record_price(self, item_id: int, realm: str, price_copper: int) -> None:
        """Insert a new price record into the database.

        Args:
            item_id: The numeric item identifier.
            realm: The realm slug (e.g. ``"us-dalaran"``).
            price_copper: The price expressed entirely in copper.
        """
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT INTO price_history (item_id, realm, price_copper, recorded_at) "
            "VALUES (?, ?, ?, ?)",
            (item_id, realm, price_copper, now),
        )
        self._conn.commit()
        logger.debug(
            "Recorded price %d copper for item %d on %s",
            price_copper,
            item_id,
            realm,
        )

    def get_price_history(
        self, item_id: int, realm: str, limit: int = 10
    ) -> list[dict]:
        """Return recent price records for an item on a realm.

        Args:
            item_id: The numeric item identifier.
            realm: The realm slug (e.g. ``"us-dalaran"``).
            limit: Maximum number of records to return, newest first.

        Returns:
            A list of dicts with keys ``id``, ``item_id``, ``realm``,
            ``price_copper``, and ``recorded_at``.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT id, item_id, realm, price_copper, recorded_at "
            "FROM price_history "
            "WHERE item_id = ? AND realm = ? "
            "ORDER BY recorded_at DESC "
            "LIMIT ?",
            (item_id, realm, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
        logger.debug("Database connection closed")
