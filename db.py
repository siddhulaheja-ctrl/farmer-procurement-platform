"""Small sqlite helpers. Not using an ORM, plain SQL is easier to read."""

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


def migrate():
    """Bring an older procurement.db up to date without wiping it."""
    if not os.path.exists(DB_PATH):
        return
    conn = sqlite3.connect(DB_PATH)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(alerts_log)")]
    if cols and "message_hi" not in cols:
        conn.execute("ALTER TABLE alerts_log ADD COLUMN message_hi TEXT")
        # most old in-app alerts had a hindi phone script written in the same
        # second. borrow that so old notices still read in hindi
        conn.execute(
            "UPDATE alerts_log SET message_hi = (SELECT i.message FROM alerts_log i"
            "  WHERE i.channel = 'ivr' AND i.farmer_id = alerts_log.farmer_id"
            "    AND i.alert_type = alerts_log.alert_type AND i.sent_at = alerts_log.sent_at"
            "    AND IFNULL(i.booking_id, 0) = IFNULL(alerts_log.booking_id, 0) LIMIT 1)"
            " WHERE channel = 'app'")
        conn.commit()
    if [r[1] for r in conn.execute("PRAGMA table_info(staff)")]:
        _migrate_staff(conn)
        conn.commit()
    conn.close()


AUDIT_SQL = """CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id     INTEGER NOT NULL,
    centre_id    INTEGER,          -- where the action happened
    action       TEXT NOT NULL,    -- see ACTIONS in audit.py
    farmer_id    INTEGER,
    booking_id   INTEGER,
    ref_id       INTEGER,          -- a slot, flag, transaction, centre or staff id
    detail       TEXT,
    before_value TEXT,             -- json
    after_value  TEXT,             -- json
    at           TEXT NOT NULL,
    FOREIGN KEY (staff_id) REFERENCES staff(id)
);
CREATE INDEX IF NOT EXISTS idx_audit_staff ON audit_log(staff_id, at);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at);
"""


def _migrate_staff(conn):
    """Roles, account switches, hashed passwords and the activity log - added
    when the shared ADMIN login was split into real accounts."""
    from accounts import DEMO_PASSWORD, DEMO_STAFF, hash_password, is_hashed
    cols = [r[1] for r in conn.execute("PRAGMA table_info(staff)")]
    if "role" not in cols:
        conn.execute("ALTER TABLE staff ADD COLUMN role TEXT NOT NULL DEFAULT 'staff'")
        # the old shared login saw every centre, so it becomes the supervisor
        conn.execute("UPDATE staff SET role = 'superadmin' WHERE centre_id IS NULL")
    if "active" not in cols:
        conn.execute("ALTER TABLE staff ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    if "last_login" not in cols:
        conn.execute("ALTER TABLE staff ADD COLUMN last_login TEXT")
    conn.executescript(AUDIT_SQL)
    for sid, pw in conn.execute("SELECT id, password FROM staff").fetchall():
        if not is_hashed(pw):
            conn.execute("UPDATE staff SET password = ? WHERE id = ?", (hash_password(pw), sid))
    # an older demo database only has the shared login - give it the counters
    centres = dict(conn.execute("SELECT name, id FROM procurement_centres").fetchall())
    for code, name, centre, role in DEMO_STAFF:
        if centre and centre not in centres:
            continue
        if conn.execute("SELECT 1 FROM staff WHERE staff_code = ?", (code,)).fetchone():
            continue
        conn.execute("INSERT INTO staff (name, staff_code, password, centre_id, role)"
                     " VALUES (?,?,?,?,?)",
                     (name, code, hash_password(DEMO_PASSWORD), centres.get(centre), role))


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
