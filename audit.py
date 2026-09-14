"""Who did what.

Every staff action writes one row here. Nothing updates or deletes a row, so
the supervisor screens can trust it as the record of the day.
"""

import json
from datetime import datetime

from db import execute

# action -> (what the log says, icon, sensitive). Sensitive is money or
# identity changed by hand - the things a supervisor pulls up on their own.
ACTIONS = {
    "sign_in":         ("Signed in", "log-in", False),
    "weigh":           ("Weighed and graded a load", "scale", False),
    "close":           ("Closed a transaction", "check-circle", False),
    "payment_held":    ("Closed with payment held", "alert-triangle", False),
    "payment_manual":  ("Changed a payment status by hand", "banknote", True),
    "payment_batch":   ("Sent a payment batch to the bank", "send", False),
    "payment_resend":  ("Sent a returned payment again", "refresh", False),
    "payment_release": ("Released a held payment", "check-circle", False),
    "grade_override":  ("Picked a grade other than the readings suggest", "award", True),
    "gate_in":         ("Let a farmer in at the gate", "scan", False),
    "gate_out":        ("Marked a farmer out at the gate", "log-out", False),
    "flag_verified":   ("Cleared a flag without changing the record", "flag", True),
    "record_edit":     ("Edited farmer details", "sliders", False),
    "id_edit":         ("Changed Aadhaar or bank details", "id-card", True),
    "register_farmer": ("Registered a farmer", "user-plus", False),
    "call":            ("Called a farmer", "phone-call", False),
    "slot_create":     ("Published a slot", "layers", False),
    "capacity_change": ("Changed slot capacity", "layers", True),
    "delay_set":       ("Set how late the counter is", "hourglass", False),
    "staff_create":    ("Added a member account", "user-plus", False),
    "staff_update":    ("Changed a member account", "shield", True),
    "password_reset":  ("Reset a password", "lock", True),
}

SENSITIVE = tuple(k for k, v in ACTIONS.items() if v[2])

FIELD_LABELS = {
    "name": "Name", "aadhaar_number": "Aadhaar", "bank_account": "Bank account",
    "ifsc_code": "IFSC", "bank_name_on_account": "Name on account",
    "land_record_id": "Land record", "village": "Village", "district": "District",
}
# changing any of these is what gets money sent somewhere else
ID_FIELDS = ("aadhaar_number", "bank_account", "ifsc_code", "bank_name_on_account")
# never written to the log in full
MASKED = ("aadhaar_number", "bank_account")
UPPER = ("ifsc_code", "land_record_id")


def mask(value, keep=4):
    digits = "".join(str(value or "").split())
    if not digits:
        return "-"
    return "•" * max(0, len(digits) - keep) + digits[-keep:]


def _store(value):
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def record(staff, action, farmer_id=None, booking_id=None, ref_id=None, detail=None,
           before=None, after=None, centre_id=None, at=None):
    """Write one entry. `centre_id` defaults to where the person is posted;
    pass it when a supervisor acts on a particular centre."""
    if staff is None:
        return None
    return execute(
        "INSERT INTO audit_log (staff_id, centre_id, action, farmer_id, booking_id, ref_id,"
        " detail, before_value, after_value, at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (staff["id"], centre_id if centre_id is not None else staff["centre_id"], action,
         farmer_id, booking_id, ref_id, detail, _store(before), _store(after),
         at or datetime.now().isoformat(timespec="seconds")))


def farmer_diff(old, form):
    """Fields a staff edit actually changes, normalised the way the save does.
    Returns (changed field names, before, after) with id numbers masked."""
    changed, before, after = [], {}, {}
    for field, label in FIELD_LABELS.items():
        new = (form.get(field) or "").strip()
        if field in UPPER:
            new = new.upper()
        was = (old[field] or "").strip()
        if new == was:
            continue
        changed.append(field)
        if field in MASKED:
            before[label], after[label] = mask(was), mask(new)
        else:
            before[label], after[label] = was or "-", new or "-"
    return changed, before, after


def touches_id(changed):
    return any(f in ID_FIELDS for f in changed)


def changes(before_value, after_value):
    """The before/after columns as rows for a template."""
    def load(v):
        if v is None:
            return None
        try:
            return json.loads(v)
        except ValueError:
            return v

    b, a = load(before_value), load(after_value)
    if isinstance(b, dict) or isinstance(a, dict):
        b, a = b or {}, a or {}
        keys = list(b) + [k for k in a if k not in b]
        return [{"field": k, "before": b.get(k, "-"), "after": a.get(k, "-")} for k in keys]
    if b is None and a is None:
        return []
    return [{"field": "", "before": "-" if b is None else b,
             "after": "-" if a is None else a}]
