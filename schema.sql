-- Smart Farmer Procurement Platform - core schema (SIH 2026 / PS 26032)
-- SQLite for the demo. Column types kept simple so the DB can be
-- inspected with any sqlite browser during the presentation.
-- TODO: migrate to PostgreSQL for production (see spec section 2).

DROP TABLE IF EXISTS site_counters;
DROP TABLE IF EXISTS alerts_log;
DROP TABLE IF EXISTS data_validation_flags;
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS slots;
DROP TABLE IF EXISTS procurement_centres;
DROP TABLE IF EXISTS staff;
DROP TABLE IF EXISTS farmers;

CREATE TABLE farmers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    phone_number    TEXT    NOT NULL UNIQUE,
    aadhaar_number  TEXT,              -- mock. TODO: real Aadhaar/UIDAI API in production
    bank_account    TEXT,              -- mock
    ifsc_code       TEXT,              -- mock
    bank_name_on_account TEXT,         -- mock: used by the name-match validation rule
    land_record_id  TEXT,              -- mock
    village         TEXT,
    district        TEXT,
    registered_via  TEXT    NOT NULL DEFAULT 'self',   -- self | csc | staff
    created_at      TEXT    NOT NULL
);

CREATE TABLE staff (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    staff_code   TEXT NOT NULL UNIQUE,
    password     TEXT NOT NULL,   -- plaintext by design for the hackathon demo.
                                  -- TODO: bcrypt/argon2 hashing in production
    centre_id    INTEGER,
    FOREIGN KEY (centre_id) REFERENCES procurement_centres(id)
);

CREATE TABLE procurement_centres (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    location            TEXT,
    district            TEXT NOT NULL,
    daily_capacity      INTEGER NOT NULL DEFAULT 200,
    crop_types_accepted TEXT NOT NULL          -- comma separated
);

CREATE TABLE slots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    centre_id    INTEGER NOT NULL,
    date         TEXT    NOT NULL,             -- YYYY-MM-DD
    time_window  TEXT    NOT NULL,             -- e.g. "09:00 - 11:00"
    max_capacity INTEGER NOT NULL,
    booked_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (centre_id) REFERENCES procurement_centres(id)
);
CREATE INDEX idx_slots_centre_date ON slots(centre_id, date);

CREATE TABLE bookings (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    farmer_id          INTEGER NOT NULL,
    slot_id            INTEGER NOT NULL,
    crop_type          TEXT    NOT NULL,
    estimated_quantity REAL    NOT NULL,       -- quintals
    status             TEXT    NOT NULL DEFAULT 'booked',  -- booked|arrived|completed|cancelled
    token_no           TEXT,
    storage_risk       TEXT    NOT NULL DEFAULT 'none',    -- none|low|high
    created_at         TEXT    NOT NULL,
    FOREIGN KEY (farmer_id) REFERENCES farmers(id),
    FOREIGN KEY (slot_id)   REFERENCES slots(id)
);
CREATE INDEX idx_bookings_farmer ON bookings(farmer_id);
CREATE INDEX idx_bookings_slot   ON bookings(slot_id);

CREATE TABLE transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id      INTEGER NOT NULL UNIQUE,
    actual_quantity REAL,
    quality_grade   TEXT,                       -- A | B | FAQ | Rejected
    price_per_unit  REAL,
    total_amount    REAL,
    payment_status  TEXT NOT NULL DEFAULT 'pending',  -- pending|processing|completed|failed
    payment_date    TEXT,
    FOREIGN KEY (booking_id) REFERENCES bookings(id)
);

CREATE TABLE data_validation_flags (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    farmer_id     INTEGER NOT NULL,
    field_flagged TEXT NOT NULL,                -- aadhaar | bank | land | name_match
    detail        TEXT,
    severity      TEXT NOT NULL DEFAULT 'warning',  -- warning | blocking
    status        TEXT NOT NULL DEFAULT 'unresolved',
    flagged_at    TEXT NOT NULL,
    resolved_at   TEXT,
    FOREIGN KEY (farmer_id) REFERENCES farmers(id)
);
CREATE INDEX idx_flags_farmer ON data_validation_flags(farmer_id);

CREATE TABLE alerts_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    farmer_id  INTEGER NOT NULL,
    booking_id INTEGER,
    alert_type TEXT NOT NULL,     -- storage_risk|slot_reminder|payment_update|data_mismatch|booking_confirmed
    channel    TEXT NOT NULL,     -- app|ivr|sms
    message    TEXT NOT NULL,
    sent_at    TEXT NOT NULL,
    read_flag  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (farmer_id) REFERENCES farmers(id)
);
CREATE INDEX idx_alerts_farmer ON alerts_log(farmer_id);

-- Footer visitor count. A real number rather than a decorative one - gov
-- portals have carried these since the nineties and it is the kind of detail
-- people notice. One row, bumped on each home page view.
CREATE TABLE site_counters (
    name  TEXT    PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
INSERT INTO site_counters (name, value) VALUES ('visits', 0);
