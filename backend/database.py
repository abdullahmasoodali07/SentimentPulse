"""
database.py - reading reviews out of a SQLite file (read-only).

Expected table (names can be changed with command-line options):

    CREATE TABLE reviews (
        id          INTEGER PRIMARY KEY,
        review_date TEXT,      -- 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS' or ISO 'YYYY-MM-DDTHH:MM:SS'
        review_text TEXT
    );

Optional extra table that labels the dataset on the dashboard:

    CREATE TABLE dataset_info (key TEXT PRIMARY KEY, value TEXT);
    -- keys used: name, is_synthetic ('true'/'false'), notice
"""

import re
import sqlite3
from datetime import date
from pathlib import Path

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier(name):
    """Table/column names cannot be passed as SQL parameters, so we validate them instead."""
    if not _IDENTIFIER.match(name or ""):
        raise ValueError(f"'{name}' is not a valid table/column name (letters, digits, underscore only)")
    return f'"{name}"'


def connect_readonly(db_path):
    """Open the database read-only. (Plain sqlite3.connect would silently create a missing file.)"""
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"Database file not found: {path}")
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def read_reviews(conn, table="reviews", id_col="id", date_col="review_date", text_col="review_text"):
    """Return all rows as a list of (id, raw_date_value, raw_text) tuples."""
    sql = "SELECT {i}, {d}, {t} FROM {tb}".format(
        i=_safe_identifier(id_col), d=_safe_identifier(date_col),
        t=_safe_identifier(text_col), tb=_safe_identifier(table))
    try:
        return conn.execute(sql).fetchall()
    except sqlite3.OperationalError as err:
        raise ValueError(
            f"Could not read table '{table}' with columns {id_col}, {date_col}, {text_col}: {err}"
        ) from err


def read_dataset_info(conn):
    """Read the optional dataset_info table. Defaults describe an unlabelled custom dataset."""
    info = {"name": "Custom dataset", "is_synthetic": False, "notice": ""}
    try:
        rows = dict(conn.execute("SELECT key, value FROM dataset_info").fetchall())
    except sqlite3.OperationalError:
        return info  # table does not exist: fine
    if rows.get("name"):
        info["name"] = rows["name"]
    info["is_synthetic"] = str(rows.get("is_synthetic", "")).strip().lower() in ("true", "1", "yes")
    info["notice"] = rows.get("notice", "") or ""
    return info


def parse_date(value):
    """
    Turn a stored date value into a datetime.date, or None if it cannot be read.
    Only the first 10 characters (YYYY-MM-DD) matter, so times and time zones are ignored.
    """
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None
