"""SQLite access helpers. Thin wrapper over sqlite3 - no ORM, so the
schema in schema.sql stays the single source of truth and the DB file
can be opened in any sqlite viewer during the demo."""

import os
import sqlite3
from flask import g

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "procurement.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    """Run a write and return the new/affected row id."""
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    last = cur.lastrowid
    cur.close()
    return last


def init_db(conn=None):
    """Create all tables from schema.sql. Destructive - drops existing tables."""
    own = conn is None
    if own:
        conn = sqlite3.connect(DB_PATH)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql"), encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    if own:
        conn.close()
