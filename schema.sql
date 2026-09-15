-- Smart Farmer Procurement Platform - core schema (SIH 2026 / PS 26032)
-- SQLite for the demo. Column types kept simple so the DB can be
-- inspected with any sqlite browser during the presentation.
-- TODO: migrate to PostgreSQL for production (see spec section 2).

DROP TABLE IF EXISTS farmer_lands;
DROP TABLE IF EXISTS booking_events;
DROP TABLE IF EXISTS payment_events;
DROP TABLE IF EXISTS payment_batches;
DROP TABLE IF EXISTS audit_log;
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
    land_record_id  TEXT,              -- mock. the first of farmer_lands, for the screens that show one
    agristack_id    TEXT,              -- Farmer ID (AgriStack), when they registered with one
    -- mock of the NPCI mapper: is Aadhaar linked to this account. A DBT
    -- payment to an account that isn't comes back, whatever else is right
    aadhaar_seeded  INTEGER NOT NULL DEFAULT 1,
    village         TEXT,
    district        TEXT,
    registered_via  TEXT    NOT NULL DEFAULT 'self',   -- self | csc | staff
    created_at      TEXT    NOT NULL
);

-- every land parcel a farmer farms. one Aadhaar, one account, as many as they have
CREATE TABLE farmer_lands (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    farmer_id      INTEGER NOT NULL,
    land_record_id TEXT NOT NULL,
    village        TEXT,
    district       TEXT,
    area_acres     REAL,
    source         TEXT NOT NULL DEFAULT 'manual',   -- manual | registry (came with the Farmer ID)
    added_at       TEXT NOT NULL,
    FOREIGN KEY (farmer_id) REFERENCES farmers(id)
);
CREATE INDEX idx_farmer_lands_farmer ON farmer_lands(farmer_id);

CREATE TABLE staff (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    staff_code   TEXT NOT NULL UNIQUE,
    password     TEXT NOT NULL,   -- werkzeug hash, never the password itself
    centre_id    INTEGER,         -- centre staff are locked to this; NULL for a supervisor
    role         TEXT NOT NULL DEFAULT 'staff',   -- staff | superadmin
    active       INTEGER NOT NULL DEFAULT 1,      -- 0 = switched off, can't sign in
    last_login   TEXT,
    FOREIGN KEY (centre_id) REFERENCES procurement_centres(id)
);

CREATE TABLE procurement_centres (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    location            TEXT,
    district            TEXT NOT NULL,
    daily_capacity      INTEGER NOT NULL DEFAULT 200,
    crop_types_accepted TEXT NOT NULL,         -- comma separated
    -- How far behind the counter is running, set by staff when they notice.
    -- One number a person keeps up beats a per-farmer estimate nobody has time
    -- for. An old "40 minutes behind" is still roughly right.
    delay_minutes       INTEGER NOT NULL DEFAULT 0,
    delay_set_at        TEXT
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
    gate_in_at         TEXT,                   -- pass scanned in at the gate
    gate_queue         INTEGER,                -- their number in the day's line at that centre
    gate_out_at        TEXT,
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
    -- the weighbridge record behind actual_quantity
    gross_weight    REAL,                       -- quintals, bags and all
    bags            INTEGER,
    bag_weight_kg   REAL,
    moisture        REAL,                       -- percent
    foreign_matter  REAL,                       -- percent
    grade_note      TEXT,                       -- why staff picked a grade other than the suggested one
    -- where the money is. payment_status is the coarse version of this, kept
    -- for the screens that only need paid / not paid. see payments.py
    pay_stage       TEXT NOT NULL DEFAULT 'weighed',  -- weighed|billed|sent|credited|returned|held|nil
    receipt_no      TEXT,
    bill_no         TEXT,
    batch_id        INTEGER,
    utr             TEXT,                       -- the bank's reference for a credit
    attempts        INTEGER NOT NULL DEFAULT 0,
    return_code     TEXT,
    weighed_at      TEXT,
    closed_at       TEXT,
    sent_at         TEXT,
    settled_at      TEXT,
    FOREIGN KEY (booking_id) REFERENCES bookings(id)
);

CREATE TABLE payment_batches (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_no   TEXT NOT NULL,
    centre_id  INTEGER,                         -- NULL when a supervisor sent every centre's bills
    staff_id   INTEGER,
    items      INTEGER NOT NULL,
    amount     REAL NOT NULL,
    created_at TEXT NOT NULL
);

-- every step a payment took. only ever added to
CREATE TABLE payment_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL,
    stage          TEXT NOT NULL,
    detail         TEXT,
    staff_id       INTEGER,
    at             TEXT NOT NULL,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);
CREATE INDEX idx_payment_events_txn ON payment_events(transaction_id);

-- every scan of a pass and every gate in / gate out
CREATE TABLE booking_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER,                         -- NULL for a code that matched nothing
    kind       TEXT NOT NULL,                   -- scan|gate_in|gate_out
    result     TEXT,                            -- for a scan: what the gate screen said
    detail     TEXT,
    staff_id   INTEGER,
    centre_id  INTEGER,
    at         TEXT NOT NULL
);
CREATE INDEX idx_booking_events_booking ON booking_events(booking_id);
CREATE INDEX idx_booking_events_at ON booking_events(centre_id, at);

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
    message_hi TEXT,              -- same alert in hindi, shown when the farmer picks hindi
    sent_at    TEXT NOT NULL,
    read_flag  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (farmer_id) REFERENCES farmers(id)
);
CREATE INDEX idx_alerts_farmer ON alerts_log(farmer_id);

-- Who did what. Rows are only ever added.
CREATE TABLE IF NOT EXISTS audit_log (
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

-- Footer visitor count. Gov portals have had these forever. One row, bumped
-- on each home page view.
CREATE TABLE site_counters (
    name  TEXT    PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
INSERT INTO site_counters (name, value) VALUES ('visits', 0);
