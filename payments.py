"""DBT payment stages.

    weighed -> billed -> sent (batch) -> credited (UTR) / returned (reason)
    returned -> fixed -> sent again
    held = closed with a blocking flag, nil = rejected, nothing to pay

Mock bank: answers from the farmer record after CREDIT_SECONDS instead of 2-3 days.
TODO: PFMS / state portal integration
"""

import hashlib
import os
import re
import time
from datetime import datetime, timedelta

import env
from db import execute, get_db, query
from validation import IFSC_RE, NAME_MATCH_THRESHOLD, name_similarity, unresolved_flags

env.load()

CREDIT_SECONDS = int(os.environ.get("PAYMENT_CREDIT_SECONDS", "30"))
LATE_HOURS = 72

# stage -> (payment_status, label)
STAGES = {
    "weighed":  ("pending", "Weighed"),
    "billed":   ("processing", "Bill ready"),
    "sent":     ("processing", "Sent to bank"),
    "credited": ("completed", "Credited"),
    "returned": ("failed", "Returned by bank"),
    "held":     ("failed", "Held"),
    "nil":      ("failed", "Nothing payable"),
}

BANKS = {
    "SBIN": "State Bank of India", "PUNB": "Punjab National Bank", "BARB": "Bank of Baroda",
    "CNRB": "Canara Bank", "UBIN": "Union Bank of India", "BKID": "Bank of India",
    "HDFC": "HDFC Bank", "ICIC": "ICICI Bank", "UTIB": "Axis Bank", "CBIN": "Central Bank of India",
    "IDIB": "Indian Bank", "IOBA": "Indian Overseas Bank", "UCBA": "UCO Bank",
    "PSIB": "Punjab & Sind Bank", "MAHB": "Bank of Maharashtra", "NAIN": "Nainital Bank",
}
SHORT_BANK = {"SBIN": "SBI", "PUNB": "PNB", "BARB": "BoB", "CNRB": "Canara", "UBIN": "Union",
              "BKID": "BoI", "HDFC": "HDFC", "ICIC": "ICICI", "UTIB": "Axis", "CBIN": "Central",
              "IDIB": "Indian Bank", "IOBA": "IOB", "UCBA": "UCO", "PSIB": "P&S", "MAHB": "BoM",
              "NAIN": "Nainital"}

# return code -> (reason, what the farmer should do)
RETURNS = {
    "AADHAAR_NOT_SEEDED": ("Aadhaar is not linked to this bank account",
                           "Ask your bank branch to link your Aadhaar to the account. Tell the centre once it is done."),
    "NAME_MISMATCH": ("Name on the bank account does not match",
                      "Bring your bank passbook to the centre so your name can be corrected."),
    "INVALID_IFSC": ("IFSC code is wrong",
                     "Check the IFSC printed in your passbook and correct it on My Details."),
    "INVALID_ACCOUNT": ("Bank account number is wrong",
                        "Check the account number in your passbook and correct it on My Details."),
}
RETURNS_HI = {
    "AADHAAR_NOT_SEEDED": "आधार इस बैंक खाते से जुड़ा नहीं है",
    "NAME_MISMATCH": "बैंक खाते का नाम मेल नहीं खाता",
    "INVALID_IFSC": "IFSC कोड गलत है",
    "INVALID_ACCOUNT": "बैंक खाता नंबर गलत है",
}


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _parse(stamp):
    try:
        return datetime.fromisoformat(stamp) if stamp else None
    except ValueError:
        return None


def status_for(stage):
    return STAGES.get(stage, ("pending",))[0]


# ------------------------------------------------------------------ the bank

def bank_code(ifsc):
    return (ifsc or "").strip().upper()[:4]


def bank_label(farmer):
    # SBI ••••5210
    acct = "".join((farmer["bank_account"] or "").split())
    short = SHORT_BANK.get(bank_code(farmer["ifsc_code"]), "Bank")
    return "%s ••••%s" % (short, acct[-4:]) if acct else "—"


def checks(farmer):
    acct = "".join((farmer["bank_account"] or "").split())
    ifsc = (farmer["ifsc_code"] or "").strip().upper()
    score = name_similarity(farmer["name"], farmer["bank_name_on_account"] or farmer["name"])
    return [
        {"code": "INVALID_ACCOUNT", "label": "Account number",
         "ok": bool(re.fullmatch(r"\d{9,18}", acct)), "detail": bank_label(farmer)},
        {"code": "INVALID_IFSC", "label": "IFSC belongs to a bank",
         "ok": bool(IFSC_RE.match(ifsc)) and ifsc[:4] in BANKS,
         "detail": BANKS.get(ifsc[:4], ifsc or "missing")},
        {"code": "AADHAAR_NOT_SEEDED", "label": "Aadhaar linked to the account",
         "ok": bool(farmer["aadhaar_seeded"]), "detail": "NPCI mapper"},
        {"code": "NAME_MISMATCH", "label": "Name matches the account",
         "ok": score >= NAME_MATCH_THRESHOLD, "detail": "%d%% match" % round(score * 100)},
    ]


def bank_answer(farmer):
    for c in checks(farmer):
        if not c["ok"]:
            return c["code"]
    return None


def make_utr(ifsc, txn_id, attempt):
    # looks like a NEFT UTR
    today = datetime.now()
    digest = hashlib.sha1(("%s-%s-%s" % (txn_id, attempt, time.time())).encode()).hexdigest()
    serial = int(digest[:8], 16) % 1000000
    return "%sN%s%03d%06d" % ((bank_code(ifsc) or "KSBK").ljust(4, "X"), today.strftime("%y"),
                              today.timetuple().tm_yday, serial)


# ------------------------------------------------------------------- records

def log(txn_id, stage, detail=None, staff=None, at=None):
    execute("INSERT INTO payment_events (transaction_id, stage, detail, staff_id, at) VALUES (?,?,?,?,?)",
            (txn_id, stage, detail, staff["id"] if staff else None, at or _now()))


def _move(txn_id, stage, **cols):
    cols["pay_stage"] = stage
    cols["payment_status"] = status_for(stage)
    sets = ", ".join("%s = ?" % k for k in cols)
    execute("UPDATE transactions SET %s WHERE id = ?" % sets, tuple(cols.values()) + (txn_id,))


def receipt_no(centre_id, txn_id):
    return "KS/PC%02d/%s/%06d" % (centre_id, datetime.now().year, txn_id)


def events(txn_id):
    return query("SELECT e.*, s.staff_code FROM payment_events e LEFT JOIN staff s ON s.id = e.staff_id"
                 " WHERE e.transaction_id = ? ORDER BY e.at, e.id", (txn_id,))


def full(txn_id):
    return query(
        "SELECT t.*, b.token_no, b.crop_type, b.farmer_id, b.estimated_quantity, s.date, s.time_window,"
        " s.centre_id, c.name AS centre_name, c.location, c.district AS centre_district,"
        " f.name AS farmer_name, f.name, f.phone_number, f.village, f.district, f.bank_account, f.ifsc_code,"
        " f.bank_name_on_account, f.aadhaar_seeded, b.slot_id"
        " FROM transactions t JOIN bookings b ON b.id = t.booking_id"
        " JOIN slots s ON s.id = b.slot_id JOIN procurement_centres c ON c.id = s.centre_id"
        " JOIN farmers f ON f.id = b.farmer_id WHERE t.id = ?", (txn_id,), one=True)


def seconds_left(txn):
    if txn["pay_stage"] != "sent":
        return None
    sent = _parse(txn["sent_at"])
    if sent is None:
        return 0
    return max(0, int(CREDIT_SECONDS - (datetime.now() - sent).total_seconds()))


def is_late(txn):
    if txn["pay_stage"] not in ("billed", "sent", "returned", "held"):
        return False
    closed = _parse(txn["closed_at"])
    return closed is not None and datetime.now() - closed > timedelta(hours=LATE_HOURS)


# ------------------------------------------------------------------ the steps

def close(txn, booking, staff):
    now = _now()
    number = txn["receipt_no"] or receipt_no(booking["centre_id"], txn["id"])
    blocking = [f for f in unresolved_flags(booking["farmer_id"]) if f["severity"] == "blocking"]
    if not (txn["total_amount"] or 0):
        stage, detail = "nil", "Rejected at grade check, nothing payable"
    elif blocking:
        stage = "held"
        detail = "Held: %s to be fixed first" % ", ".join(sorted({f["field_flagged"] for f in blocking}))
    else:
        stage, detail = "billed", "Bill ready for the bank"
    _move(txn["id"], stage, receipt_no=number, closed_at=now,
          bill_no="BL-%s-%06d" % (datetime.now().strftime("%y%m%d"), txn["id"]) if stage == "billed" else None)
    log(txn["id"], "closed", "Receipt %s issued" % number, staff, now)
    log(txn["id"], stage, detail, staff, now)
    return stage


def send(txns, staff, centre_id=None):
    txns = [x for x in txns if x["pay_stage"] in ("billed", "returned")]
    if not txns:
        return None
    now = _now()
    amount = sum(x["total_amount"] or 0 for x in txns)
    batch_id = execute("INSERT INTO payment_batches (batch_no, centre_id, staff_id, items, amount, created_at)"
                       " VALUES ('', ?, ?, ?, ?, ?)",
                       (centre_id, staff["id"] if staff else None, len(txns), amount, now))
    batch_no = "B-%s-%04d" % (datetime.now().strftime("%y%m%d"), batch_id)
    execute("UPDATE payment_batches SET batch_no = ? WHERE id = ?", (batch_no, batch_id))
    for x in txns:
        again = x["pay_stage"] == "returned"
        _move(x["id"], "sent", batch_id=batch_id, sent_at=now, attempts=(x["attempts"] or 0) + 1,
              return_code=None, bill_no=x["bill_no"] or "BL-%s-%06d" % (datetime.now().strftime("%y%m%d"), x["id"]))
        log(x["id"], "sent", "%s in batch %s" % ("Sent again" if again else "Sent to bank", batch_no), staff, now)
    return query("SELECT * FROM payment_batches WHERE id = ?", (batch_id,), one=True)


_last_settle = 0.0


def settle_due(force=False):
    # runs on page loads instead of a background job
    global _last_settle
    if not force and time.time() - _last_settle < 2:
        return 0
    _last_settle = time.time()
    cutoff = (datetime.now() - timedelta(seconds=CREDIT_SECONDS)).isoformat(timespec="seconds")
    due = query("SELECT id FROM transactions WHERE pay_stage = 'sent' AND IFNULL(sent_at, '') <= ?", (cutoff,))
    for row in due:
        _settle(full(row["id"]))
    return len(due)


def _claim(txn_id, stage):
    # another worker may be settling the same payment
    db = get_db()
    cur = db.execute("UPDATE transactions SET pay_stage = ?, payment_status = ? WHERE id = ? AND pay_stage = 'sent'",
                     (stage, status_for(stage), txn_id))
    db.commit()
    return cur.rowcount == 1


def _settle(x):
    from alerts import raise_alert
    now = _now()
    code = bank_answer(x)
    if not _claim(x["id"], "returned" if code else "credited"):
        return
    amount = int(x["total_amount"] or 0)
    if code is None:
        utr = make_utr(x["ifsc_code"], x["id"], x["attempts"])
        _move(x["id"], "credited", utr=utr, settled_at=now, payment_date=now)
        log(x["id"], "credited", "Credited to %s, UTR %s" % (bank_label(x), utr), at=now)
        raise_alert(x["farmer_id"], "payment_update", "app",
                    "Rs %s credited to %s. Bank reference (UTR) %s." % (format(amount, ","), bank_label(x), utr),
                    booking_id=x["booking_id"],
                    message_hi="₹%d आपके खाते %s में जमा हो गए। बैंक संदर्भ (UTR) %s।" % (amount, bank_label(x), utr))
        raise_alert(x["farmer_id"], "payment_update", "ivr",
                    "नमस्ते। आपकी फसल के %d रुपये आपके बैंक खाते में जमा हो गए हैं। धन्यवाद।" % amount,
                    booking_id=x["booking_id"])
    else:
        _move(x["id"], "returned", return_code=code, settled_at=now)
        log(x["id"], "returned", RETURNS[code][0], at=now)
        raise_alert(x["farmer_id"], "payment_update", "app",
                    "Your payment of Rs %s came back from the bank: %s. %s"
                    % (format(amount, ","), RETURNS[code][0], RETURNS[code][1]),
                    booking_id=x["booking_id"],
                    message_hi="₹%d का भुगतान बैंक से वापस आ गया: %s। अपने खरीद केंद्र से संपर्क करें।"
                               % (amount, RETURNS_HI[code]))
        raise_alert(x["farmer_id"], "payment_update", "ivr",
                    "नमस्ते। आपका %d रुपये का भुगतान बैंक से वापस आ गया है, क्योंकि %s। "
                    "कृपया बैंक पासबुक लेकर अपने खरीद केंद्र आएं। धन्यवाद।" % (amount, RETURNS_HI[code]),
                    booking_id=x["booking_id"])


def release(txn, staff):
    blocking = [f for f in unresolved_flags(txn["farmer_id"]) if f["severity"] == "blocking"]
    if txn["pay_stage"] != "held" or blocking:
        return False
    _move(txn["id"], "billed", bill_no="BL-%s-%06d" % (datetime.now().strftime("%y%m%d"), txn["id"]))
    log(txn["id"], "billed", "Released: details fixed, bill ready for the bank", staff)
    return True


def override(txn, stage, reason, staff):
    cols = {}
    if stage == "credited":
        cols.update(settled_at=_now(), payment_date=_now())
    _move(txn["id"], stage, **cols)
    log(txn["id"], stage, "Set by hand: %s" % reason, staff)


# -------------------------------------------------------------- for screens

def register(centre_id=None, stage=None):
    sql = ("SELECT t.*, b.token_no, b.crop_type, b.farmer_id, f.name AS farmer_name, f.bank_account,"
           " f.ifsc_code, s.date, s.centre_id, c.name AS centre_name, pb.batch_no"
           " FROM transactions t JOIN bookings b ON b.id = t.booking_id"
           " JOIN farmers f ON f.id = b.farmer_id JOIN slots s ON s.id = b.slot_id"
           " JOIN procurement_centres c ON c.id = s.centre_id"
           " LEFT JOIN payment_batches pb ON pb.id = t.batch_id WHERE 1=1")
    args = []
    if centre_id:
        sql += " AND s.centre_id = ?"
        args.append(centre_id)
    if stage:
        sql += " AND t.pay_stage = ?"
        args.append(stage)
    return query(sql + " ORDER BY IFNULL(t.closed_at, s.date) DESC, t.id DESC", tuple(args))


def batches(centre_id=None, limit=6):
    sql = ("SELECT pb.*, st.staff_code, c.name AS centre_name,"
           " (SELECT COUNT(*) FROM transactions t WHERE t.batch_id = pb.id AND t.pay_stage = 'credited') AS credited,"
           " (SELECT COUNT(*) FROM transactions t WHERE t.batch_id = pb.id AND t.pay_stage = 'returned') AS returned"
           " FROM payment_batches pb LEFT JOIN staff st ON st.id = pb.staff_id"
           " LEFT JOIN procurement_centres c ON c.id = pb.centre_id")
    args = ()
    if centre_id:
        sql += " WHERE pb.centre_id = ?"
        args = (centre_id,)
    return query(sql + " ORDER BY pb.id DESC LIMIT %d" % limit, args)


def farmer_lines(farmer_id):
    # for the help chat
    rows = query("SELECT t.*, b.token_no FROM transactions t JOIN bookings b ON b.id = t.booking_id"
                 " WHERE b.farmer_id = ? ORDER BY t.id DESC LIMIT 6", (farmer_id,))
    out = []
    for r in rows:
        line = "token %s: Rs %d, %s" % (r["token_no"], r["total_amount"] or 0, STAGES.get(r["pay_stage"], ("", r["pay_stage"]))[1])
        if r["utr"]:
            line += ", UTR %s" % r["utr"]
        if r["return_code"]:
            line += ", returned because: %s (%s)" % RETURNS[r["return_code"]]
        out.append(line)
    return out
