"""The gate: what a scanned pass means, and checking farmers in and out.

A scan answers one question for the person at the gate - let this tractor in
or not - and says what to do next if the farmer is already inside. Every scan
is written down, including the ones that matched nothing.
"""

import re
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import audit
from db import execute, query

EARLY_MINUTES = 60      # let people in this long before their window
LATE_MINUTES = 60       # and this long after it closes
TOKEN_RE = re.compile(r"PC\d{2}-S\d{3}-\d{3}", re.I)


def parse_code(text):
    """What a scanner or a typed box gave us -> (token, signature).

    The QR holds https://host/t/<token>?s=<sig>. Someone typing at the gate
    types just the token, so there is no signature to check."""
    text = (text or "").strip()
    if not text:
        return None, None
    if "://" in text:
        url = urlparse(text)
        m = TOKEN_RE.search(url.path)
        sig = (parse_qs(url.query).get("s") or [None])[0]
        return (m.group(0).upper() if m else None), sig
    m = TOKEN_RE.search(text)
    return (m.group(0).upper() if m else None), None


def find(token):
    return query(
        "SELECT b.*, s.date, s.time_window, s.centre_id, c.name AS centre_name,"
        " f.name AS farmer_name, f.village, f.district AS farmer_district, f.aadhaar_number,"
        " t.id AS txn_id, t.pay_stage, t.total_amount, t.weighed_at, t.closed_at"
        " FROM bookings b JOIN slots s ON s.id = b.slot_id"
        " JOIN procurement_centres c ON c.id = s.centre_id JOIN farmers f ON f.id = b.farmer_id"
        " LEFT JOIN transactions t ON t.booking_id = b.id WHERE b.token_no = ?", (token,), one=True)


def _window(b):
    """The slot's start and end as datetimes."""
    try:
        start, end = [x.strip() for x in b["time_window"].split("-")]
        day = datetime.strptime(b["date"], "%Y-%m-%d")
        return (datetime.combine(day, datetime.strptime(start, "%H:%M").time()),
                datetime.combine(day, datetime.strptime(end, "%H:%M").time()))
    except (ValueError, AttributeError):
        return None, None


def _hm(stamp):
    try:
        return datetime.fromisoformat(stamp).strftime("%H:%M")
    except (TypeError, ValueError):
        return "?"


def verdict(b, genuine, my_centre, now=None):
    """What the gate screen says.

    genuine: True (signature checked), None (typed by hand), False (bad code).
    tone is ok / warn / bad / info. `action` is what the big button does:
    checkin, checkin_anyway, checkout, open (the booking page) or None.
    """
    now = now or datetime.now()
    if b is None or genuine is False:
        return {"tone": "bad", "code": "not_genuine", "title": "Not a genuine pass",
                "detail": "This code was not issued by Krishi Sutra, or it has been changed or replaced. "
                          "Look the farmer up by name and check their Aadhaar card.",
                "action": None}
    if my_centre and b["centre_id"] != my_centre:
        return {"tone": "bad", "code": "wrong_centre", "title": "Booked at another centre",
                "detail": "This slot is at %s. Send the farmer there." % b["centre_name"], "action": None}
    if b["status"] == "cancelled":
        return {"tone": "bad", "code": "cancelled", "title": "Booking cancelled",
                "detail": "The farmer cancelled or moved this booking. An old printout may still be in their hand.",
                "action": None}
    if b["gate_out_at"]:
        return {"tone": "info", "code": "finished", "title": "Visit finished",
                "detail": "Left the centre at %s." % _hm(b["gate_out_at"]), "action": None}
    if b["status"] == "completed":
        return {"tone": "ok", "code": "closed", "title": "Transaction closed, let them out",
                "detail": "Receipt issued. Mark them out at the gate.", "action": "checkout"}
    if b["status"] == "arrived":
        return {"tone": "info", "code": "weighed", "title": "Weighed, waiting to be closed",
                "detail": "Weighed at %s. Open the booking to close the transaction." % _hm(b["weighed_at"]),
                "action": "open"}
    if b["gate_in_at"]:
        return {"tone": "info", "code": "inside", "title": "Already inside, queue no. %s" % (b["gate_queue"] or "?"),
                "detail": "Came in at %s. Send them to the weighbridge." % _hm(b["gate_in_at"]), "action": "open"}

    start, end = _window(b)
    today = now.date()
    slot_day = start.date() if start else None
    typed = " Typed by hand, so match the name to the Aadhaar card." if genuine is None else ""
    if slot_day and slot_day < today:
        return {"tone": "bad", "code": "missed", "title": "Slot was on %s" % slot_day.strftime("%d %b"),
                "detail": "The farmer missed this slot. Let them in only if the centre has room today." + typed,
                "action": "checkin_anyway"}
    if slot_day and slot_day > today:
        days = (slot_day - today).days
        return {"tone": "warn", "code": "early_day",
                "title": "Slot is on %s, %d day%s away" % (slot_day.strftime("%d %b"), days, "s" if days != 1 else ""),
                "detail": "Not today. Let them in only if the centre has room." + typed, "action": "checkin_anyway"}
    if start and now < start - timedelta(minutes=EARLY_MINUTES):
        return {"tone": "warn", "code": "early", "title": "Early, slot starts at %s" % start.strftime("%H:%M"),
                "detail": "More than an hour early." + typed, "action": "checkin_anyway"}
    if end and now > end + timedelta(minutes=LATE_MINUTES):
        return {"tone": "warn", "code": "late", "title": "Late, slot ended at %s" % end.strftime("%H:%M"),
                "detail": "More than an hour after the window." + typed, "action": "checkin_anyway"}
    return {"tone": "ok", "code": "allow", "title": "Genuine pass, let them in" if genuine else "Booking found, let them in",
            "detail": ("Right centre, right day, %s." % b["time_window"]) + typed, "action": "checkin"}


def log_scan(b, staff, v, centre_id=None):
    execute("INSERT INTO booking_events (booking_id, kind, result, detail, staff_id, centre_id, at)"
            " VALUES (?, 'scan', ?, ?, ?, ?, ?)",
            (b["id"] if b else None, v["code"], v["title"], staff["id"] if staff else None,
             b["centre_id"] if b else centre_id, datetime.now().isoformat(timespec="seconds")))


def check_in(b, staff, note=None):
    """Returns their number in today's line at this centre."""
    now = datetime.now().isoformat(timespec="seconds")
    n = query("SELECT COUNT(*) AS n FROM bookings bx JOIN slots sx ON sx.id = bx.slot_id"
              " WHERE sx.centre_id = ? AND substr(bx.gate_in_at, 1, 10) = ?",
              (b["centre_id"], date.today().isoformat()), one=True)["n"] + 1
    execute("UPDATE bookings SET gate_in_at = ?, gate_queue = ? WHERE id = ?", (now, n, b["id"]))
    detail = "Queue no. %d" % n + (" (%s)" % note if note else "")
    execute("INSERT INTO booking_events (booking_id, kind, detail, staff_id, centre_id, at)"
            " VALUES (?, 'gate_in', ?, ?, ?, ?)", (b["id"], detail, staff["id"], b["centre_id"], now))
    audit.record(staff, "gate_in", farmer_id=b["farmer_id"], booking_id=b["id"], centre_id=b["centre_id"],
                 detail=detail)
    return n


def check_out(b, staff):
    now = datetime.now().isoformat(timespec="seconds")
    execute("UPDATE bookings SET gate_out_at = ? WHERE id = ?", (now, b["id"]))
    execute("INSERT INTO booking_events (booking_id, kind, detail, staff_id, centre_id, at)"
            " VALUES (?, 'gate_out', NULL, ?, ?, ?)", (b["id"], staff["id"], b["centre_id"], now))
    audit.record(staff, "gate_out", farmer_id=b["farmer_id"], booking_id=b["id"], centre_id=b["centre_id"])


def visit(booking_id):
    """Everything that happened to one booking at the centre, in order:
    gate, weighbridge, closing, the money, leaving."""
    steps = []
    for e in query("SELECT e.*, s.staff_code FROM booking_events e LEFT JOIN staff s ON s.id = e.staff_id"
                   " WHERE e.booking_id = ? AND e.kind != 'scan' ORDER BY e.at", (booking_id,)):
        steps.append({"at": e["at"], "kind": e["kind"], "detail": e["detail"], "who": e["staff_code"]})
    t = query("SELECT * FROM transactions WHERE booking_id = ?", (booking_id,), one=True)
    if t and t["weighed_at"]:
        steps.append({"at": t["weighed_at"], "kind": "weighed",
                      "detail": "%.2f quintals net, grade %s" % (t["actual_quantity"] or 0, t["quality_grade"]),
                      "who": None})
    if t:
        for e in query("SELECT e.*, s.staff_code FROM payment_events e LEFT JOIN staff s ON s.id = e.staff_id"
                       " WHERE e.transaction_id = ? ORDER BY e.at, e.id", (t["id"],)):
            steps.append({"at": e["at"], "kind": "pay_" + e["stage"], "detail": e["detail"], "who": e["staff_code"]})
    steps.sort(key=lambda s: s["at"] or "")
    return steps


def today(centre_id=None):
    """The gate screen's numbers and its list of recent scans."""
    day = date.today().isoformat()
    scope = " AND sx.centre_id = %d" % int(centre_id) if centre_id else ""
    inside = query("SELECT COUNT(*) AS n FROM bookings bx JOIN slots sx ON sx.id = bx.slot_id"
                   " WHERE substr(bx.gate_in_at, 1, 10) = ?" + scope, (day,), one=True)["n"]
    out = query("SELECT COUNT(*) AS n FROM bookings bx JOIN slots sx ON sx.id = bx.slot_id"
                " WHERE substr(bx.gate_out_at, 1, 10) = ?" + scope, (day,), one=True)["n"]
    waits = query("SELECT bx.gate_in_at, t.weighed_at FROM bookings bx JOIN slots sx ON sx.id = bx.slot_id"
                  " JOIN transactions t ON t.booking_id = bx.id"
                  " WHERE substr(bx.gate_in_at, 1, 10) = ? AND t.weighed_at >= bx.gate_in_at" + scope, (day,))
    minutes = [(datetime.fromisoformat(w["weighed_at"]) - datetime.fromisoformat(w["gate_in_at"])).total_seconds() / 60
               for w in waits]
    escope = " AND e.centre_id = %d" % int(centre_id) if centre_id else ""
    scans = query("SELECT e.*, b.token_no, f.name AS farmer_name, st.staff_code FROM booking_events e"
                  " LEFT JOIN bookings b ON b.id = e.booking_id LEFT JOIN farmers f ON f.id = b.farmer_id"
                  " LEFT JOIN staff st ON st.id = e.staff_id"
                  " WHERE substr(e.at, 1, 10) = ?" + escope + " ORDER BY e.id DESC LIMIT 12", (day,))
    return {"inside": inside, "out": out, "wait": round(sum(minutes) / len(minutes)) if minutes else None,
            "scans": scans}
