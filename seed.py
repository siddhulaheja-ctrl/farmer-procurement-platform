"""Builds the database from scratch.

Run:  python seed.py
DROPS every table and recreates it.

Six farmers, all of us, with numbers registered in vonage so the calls land.
Between them they cover every state the app can be in - see CASES below.
Everyone is in Uttarakhand.

Phone numbers come from .env so they stay out of the repo.
"""

import json
import os
import sqlite3
from datetime import date, datetime, timedelta

import core
import db
import env
import payments
import weather
from accounts import DEMO_PASSWORD, DEMO_STAFF, hash_password
from alerts import hi
from validation import run_checks

env.load()

CENTRES = [
    ("Rudrapur Mandi Samiti", "Rudrapur", "Udham Singh Nagar", 220,
     "Paddy,Wheat,Maize"),
    ("Kichha Kharid Kendra", "Kichha Block", "Udham Singh Nagar", 160, "Paddy,Wheat"),
    ("Haridwar Kharid Kendra", "Jwalapur", "Haridwar", 140, "Wheat,Paddy"),
    ("Vikasnagar Grain Market", "Vikasnagar", "Dehradun", 120, "Wheat,Gram"),
    ("Haldwani Mandi Centre", "Mandi Road, Haldwani", "Nainital", 150, "Paddy,Wheat,Maize"),
]

TIME_WINDOWS = ["08:00 - 10:00", "10:00 - 12:00", "12:00 - 14:00", "14:00 - 16:00"]

# What each farmer is here to show. Kept next to the data so it doesn't drift.
CASES = """
  1  Chandra Bhushan Kumar   clean record, slot in 3 days     -> token reminder call
  2  Ravi Kumar              clean, slot 9 days out           -> storage risk + rain call
  3  Mayank Verma            warning flags (name, land id)    -> payment still clears
  4  Vivek Kumar             blocking flags (aadhaar, ifsc)   -> payment HELD, documents call
  5  Aayush Raj              registered at a CSC counter      -> in at the gate, weighed, grade B -> close,
                                                                 send batch, credited with a UTR 30s later
  6  Siddharth Laheja        history: bill waiting 4 days (late), cancelled, upcoming
  2  Ravi Kumar (again)      aadhaar not linked to his bank   -> payment RETURNED; tick "linked", send again
"""

# name, env var holding the phone, village, district, how they registered
PEOPLE = [
    ("Chandra Bhushan Kumar", "DEMO_FARMER_PHONE_1", "Dineshpur", "Udham Singh Nagar", "self"),
    ("Ravi Kumar", "DEMO_FARMER_PHONE_2", "Kichha", "Udham Singh Nagar", "staff"),
    ("Mayank Verma", "DEMO_FARMER_PHONE_3", "Jwalapur", "Haridwar", "self"),
    ("Vivek Kumar", "DEMO_FARMER_PHONE_4", "Manglaur", "Haridwar", "self"),
    ("Aayush Raj", "DEMO_FARMER_PHONE_5", "Gadarpur", "Udham Singh Nagar", "csc"),
    ("Siddharth Laheja", "VOICE_DEMO_NUMBER", "Vikasnagar", "Dehradun", "self"),
]

# aadhaar, account no, ifsc, name on the account, land record id.
# All valid except where a case needs otherwise. Vivek's aadhaar fails the
# verhoeff check like a mistyped one would, and his ifsc is missing the 0.
# Mayank's account is in his father's name - the most common reason a DBT
# payment bounces - and his land id is in the old tehsil format.
PAPERWORK = {
    "Chandra Bhushan Kumar": ("482910563723", "30671249885210", "SBIN0004567",
                              "Chandra Bhushan Kumar", "USN-104238-12"),
    "Ravi Kumar": ("529301847561", "40218836710294", "PUNB0123456",
                   "Ravi Kumar", "USN-238104-07"),
    "Mayank Verma": ("671048295136", "51930274618835", "BARB0HARIDW",
                     "Ramesh Chandra Verma", "UK/1123"),
    "Vivek Kumar": ("482910563728", "20845619273044", "BARB1MANGLR",
                    "Vivek Kumar", "HRD-882410-05"),
    "Aayush Raj": ("295810374622", "60193827450116", "CNRB0002841",
                   "Aayush Raj", "USN-410238-21"),
    "Siddharth Laheja": ("840192638572", "10938475610283", "HDFC0000562",
                         "Siddharth Laheja", "DDN-192837-03"),
}

RAIN_CALL_HI = ("नमस्ते {name} जी। कृषि सूत्र से सूचना। {centre} पर आपका स्लॉट {days} दिन दूर है "
                "और आपके क्षेत्र में बारिश का अनुमान है। अपनी उपज को ढककर ऊंची जगह रखें, या "
                "अपने केंद्र से पहले का स्लॉट मांगें। धन्यवाद।")


def phone_for(var):
    return "".join(c for c in os.environ.get(var, "") if c.isdigit())[-10:]


def workday(offset):
    """Slots skip Sundays, so step past if we land on one."""
    d = date.today() + timedelta(days=offset)
    return d + timedelta(days=1) if d.weekday() == 6 else d


class Seeder:
    """Wrapper so the cases below read as data instead of SQL."""

    def __init__(self, cur):
        self.cur = cur
        self.centres = {}
        self.farmers = {}
        self.staff = {}

    def slot(self, centre, day, window):
        row = self.cur.execute(
            "SELECT id FROM slots WHERE centre_id=? AND date=? AND time_window=?",
            (self.centres[centre], workday(day).isoformat(), TIME_WINDOWS[window])).fetchone()
        return row["id"]

    def booking(self, who, centre, day, crop, qty, status="booked", window=0,
                grade=None, actual=None, payment=None):
        """Writes a booking straight in. Not using core.book_slot because it
        refuses past dates and half of these are history."""
        sid = self.slot(centre, day, window)
        created = (date.today() + timedelta(days=min(day, 0) - 4)).isoformat() + "T09:15:00"
        self.cur.execute(
            "INSERT INTO bookings (farmer_id, slot_id, crop_type, estimated_quantity, status,"
            " created_at) VALUES (?,?,?,?,?,?)",
            (self.farmers[who], sid, crop, qty, status, created))
        bid = self.cur.lastrowid

        # cancelled and completed ones have released their place again
        if status in ("booked", "arrived"):
            self.cur.execute("UPDATE slots SET booked_count = booked_count + 1 WHERE id=?", (sid,))
        seq = self.cur.execute("SELECT COUNT(*) c FROM bookings WHERE slot_id=?",
                               (sid,)).fetchone()["c"]
        self.cur.execute("UPDATE bookings SET token_no=? WHERE id=?",
                         ("PC%02d-S%03d-%03d" % (self.centres[centre], sid, seq), bid))

        if grade is not None:
            self.transaction(bid, centre, day, window, crop, actual, grade, payment)
        return bid

    def transaction(self, bid, centre, day, window, crop, net, grade, stage, moisture=None):
        """The weighbridge record, the gate, and however far the money got.
        `stage` is one of payments.STAGES."""
        cur = self.cur
        rate, total = core.compute_amount(crop, net, grade)
        bags = int(round(net * 2))              # 50 kg bags
        gross = round(net + bags * 0.6 / 100, 2)
        limit = core.MOISTURE_MAX.get(crop, 14.0)
        if moisture is None:
            moisture = {"A": limit - 2.5, "FAQ": limit - 0.8, "B": limit + 1.2, "Rejected": limit + 3.4}[grade]
        foreign = {"A": 0.2, "FAQ": 0.5, "B": 0.9, "Rejected": 2.6}[grade]

        start = datetime.combine(workday(day), datetime.strptime(TIME_WINDOWS[window][:5], "%H:%M").time())
        latest = datetime.now() - timedelta(minutes=20)

        def when(minutes):
            # today's history can't have happened later than now, or before
            # midnight either when the seed is run in the small hours
            t = start + timedelta(minutes=minutes)
            if day != 0:
                return t
            t = min(t, latest - timedelta(minutes=60 - minutes))
            midnight = datetime.combine(date.today(), datetime.min.time())
            return max(t, midnight + timedelta(minutes=minutes / 10.0))

        def iso(t):
            return t.isoformat(timespec="seconds") if t else None

        gate_in, weighed = when(5), when(38)
        closed = when(56) if stage != "weighed" else None
        centre_id = self.centres[centre]
        staff = cur.execute("SELECT id FROM staff WHERE centre_id = ? ORDER BY id LIMIT 1",
                            (centre_id,)).fetchone()
        staff_id = staff["id"] if staff else None

        queue = cur.execute("SELECT COUNT(*) c FROM bookings b JOIN slots s ON s.id = b.slot_id"
                            " WHERE s.centre_id = ? AND substr(b.gate_in_at, 1, 10) = ?",
                            (centre_id, gate_in.date().isoformat())).fetchone()["c"] + 1
        cur.execute("UPDATE bookings SET gate_in_at = ?, gate_queue = ? WHERE id = ?", (iso(gate_in), queue, bid))
        cur.execute("INSERT INTO booking_events (booking_id, kind, detail, staff_id, centre_id, at)"
                    " VALUES (?, 'gate_in', ?, ?, ?, ?)", (bid, "Queue no. %d" % queue, staff_id, centre_id, iso(gate_in)))

        cur.execute(
            "INSERT INTO transactions (booking_id, actual_quantity, quality_grade, price_per_unit, total_amount,"
            " payment_status, gross_weight, bags, bag_weight_kg, moisture, foreign_matter, pay_stage,"
            " weighed_at, closed_at) VALUES (?,?,?,?,?,?,?,?,0.6,?,?,?,?,?)",
            (bid, net, grade, rate, total, payments.status_for(stage), gross, bags, round(moisture, 1), foreign,
             stage, iso(weighed), iso(closed)))
        tid = cur.lastrowid

        def event(stage_name, detail, at, who=staff_id):
            cur.execute("INSERT INTO payment_events (transaction_id, stage, detail, staff_id, at) VALUES (?,?,?,?,?)",
                        (tid, stage_name, detail, who, iso(at)))

        event("weighed", "%.2f q gross, %d bags, %.2f q net, moisture %.1f%%, grade %s"
              % (gross, bags, net, moisture, grade), weighed)
        if closed is None:
            return tid

        receipt = "KS/PC%02d/%d/%06d" % (centre_id, start.year, tid)
        bill = "BL-%s-%06d" % (closed.strftime("%y%m%d"), tid) if total else None
        cur.execute("UPDATE transactions SET receipt_no = ?, bill_no = ? WHERE id = ?", (receipt, bill, tid))
        event("closed", "Receipt %s issued" % receipt, closed)
        gate_out = closed + timedelta(minutes=9)
        cur.execute("UPDATE bookings SET gate_out_at = ? WHERE id = ?", (iso(gate_out), bid))
        cur.execute("INSERT INTO booking_events (booking_id, kind, staff_id, centre_id, at) VALUES (?, 'gate_out', ?, ?, ?)",
                    (bid, staff_id, centre_id, iso(gate_out)))

        if stage == "nil":
            event("nil", "Rejected at grade check, nothing payable", closed)
        elif stage == "held":
            event("held", "Held: aadhaar, bank to be fixed first", closed)
        elif stage == "billed":
            event("billed", "Bill ready for the bank", closed)
        elif stage == "credited":
            # marked paid by hand, no bank reference - the override the supervisor should notice
            event("billed", "Bill ready for the bank", closed)
            settled = closed + timedelta(days=1, hours=7)
            event("credited", "Set by hand: bank confirmed the credit on the phone", settled)
            cur.execute("UPDATE transactions SET settled_at = ?, payment_date = ? WHERE id = ?",
                        (iso(settled), iso(settled), tid))
        elif stage == "returned":
            event("billed", "Bill ready for the bank", closed)
            sent = closed + timedelta(hours=3)
            cur.execute("INSERT INTO payment_batches (batch_no, centre_id, staff_id, items, amount, created_at)"
                        " VALUES ('', ?, ?, 1, ?, ?)", (centre_id, staff_id, total, iso(sent)))
            batch_id = cur.lastrowid
            batch_no = "B-%s-%04d" % (sent.strftime("%y%m%d"), batch_id)
            cur.execute("UPDATE payment_batches SET batch_no = ? WHERE id = ?", (batch_no, batch_id))
            event("sent", "Sent to bank in batch %s" % batch_no, sent)
            back = sent + timedelta(seconds=payments.CREDIT_SECONDS)
            event("returned", payments.RETURNS["AADHAAR_NOT_SEEDED"][0], back, who=None)
            cur.execute("UPDATE transactions SET batch_id = ?, sent_at = ?, settled_at = ?, attempts = 1,"
                        " return_code = 'AADHAAR_NOT_SEEDED' WHERE id = ?", (batch_id, iso(sent), iso(back), tid))
        return tid

    def alert(self, who, kind, channel, message, booking_id=None, days_ago=0, hi=None):
        self.cur.execute(
            "INSERT INTO alerts_log (farmer_id, booking_id, alert_type, channel, message,"
            " message_hi, sent_at, read_flag) VALUES (?,?,?,?,?,?,?,?)",
            (self.farmers[who], booking_id, kind, channel, message, hi,
             (datetime.now() - timedelta(days=days_ago)).isoformat(timespec="seconds"),
             1 if days_ago > 2 else 0))


def build_centres_and_slots(cur, s):
    for c in CENTRES:
        cur.execute("INSERT INTO procurement_centres (name, location, district, daily_capacity,"
                    " crop_types_accepted) VALUES (?,?,?,?,?)", c)
        s.centres[c[0]] = cur.lastrowid

    # one supervisor who sees every centre, and the people at each counter
    for code, name, centre, role in DEMO_STAFF:
        cur.execute("INSERT INTO staff (name, staff_code, password, centre_id, role)"
                    " VALUES (?,?,?,?,?)",
                    (name, code, hash_password(DEMO_PASSWORD), s.centres.get(centre), role))
        s.staff[code] = cur.lastrowid

    today = date.today()
    for name, cid in s.centres.items():
        cap = cur.execute("SELECT daily_capacity FROM procurement_centres WHERE id=?",
                          (cid,)).fetchone()["daily_capacity"]
        per_slot = max(6, cap // len(TIME_WINDOWS) // 8)
        for d in range(-4, 15):          # a few days of history, two weeks ahead
            day = today + timedelta(days=d)
            if day.weekday() == 6:       # centres are shut on sunday
                continue
            for tw in TIME_WINDOWS:
                cur.execute("INSERT INTO slots (centre_id, date, time_window, max_capacity,"
                            " booked_count) VALUES (?,?,?,?,0)",
                            (cid, day.isoformat(), tw, per_slot))


def build_farmers(cur, s, now):
    """Returns anyone whose number is missing from .env."""
    missing = []
    for name, var, village, district, via in PEOPLE:
        phone = phone_for(var)
        if not phone:
            missing.append("%-24s %s" % (name, var))
            continue
        aadhaar, acct, ifsc, on_acct, land = PAPERWORK[name]
        cur.execute(
            "INSERT INTO farmers (name, phone_number, aadhaar_number, bank_account, ifsc_code,"
            " bank_name_on_account, land_record_id, village, district, registered_via, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (name, phone, aadhaar, acct, ifsc, on_acct, land, village, district, via, now))
        s.farmers[name] = cur.lastrowid
    # nothing the portal checks can see this one - only the bank's answer does
    if "Ravi Kumar" in s.farmers:
        cur.execute("UPDATE farmers SET aadhaar_seeded = 0 WHERE id = ?", (s.farmers["Ravi Kumar"],))
    return missing


def flag_everyone(cur, s, now):
    """run_checks has no db calls, so it works without an app context."""
    for name, fid in s.farmers.items():
        problems = run_checks(dict(cur.execute("SELECT * FROM farmers WHERE id=?",
                                               (fid,)).fetchone()))
        for p in problems:
            cur.execute(
                "INSERT INTO data_validation_flags (farmer_id, field_flagged, detail, severity,"
                " status, flagged_at) VALUES (?,?,?,?,'unresolved',?)",
                (fid, p["field"], p["detail"], p["severity"], now))
        if problems:
            blocking = sum(1 for p in problems if p["severity"] == "blocking")
            s.alert(name, "data_mismatch", "app",
                    "%d issue(s) found in your registration details (%d critical). Please visit "
                    "your procurement centre or update your profile before your slot date, "
                    "otherwise your payment may be delayed." % (len(problems), blocking),
                    days_ago=5,
                    hi="आपकी जानकारी में %d गड़बड़ी मिली (%d गंभीर)। भुगतान न रुके, इसलिए "
                       "स्लॉट से पहले इन्हें ठीक करें।" % (len(problems), blocking))


def build_bookings(s):
    # 1. chandra - slot soon, so no storage worry. plus a load rejected at
    #    the gate last week, to fill in the grade -> zero rupees path.
    b = s.booking("Chandra Bhushan Kumar", "Rudrapur Mandi Samiti", 3, "Wheat", 42)
    s.alert("Chandra Bhushan Kumar", "booking_confirmed", "app",
            "Slot confirmed at Rudrapur Mandi Samiti. Bring your gate pass and Aadhaar card.",
            booking_id=b, days_ago=1,
            hi="स्लॉट पक्का: रुद्रपुर मंडी समिति। गेट पास और आधार कार्ड साथ लाएं।")
    s.booking("Chandra Bhushan Kumar", "Rudrapur Mandi Samiti", -3, "Paddy", 18, window=2,
              status="completed", grade="Rejected", actual=17.4, payment="nil")

    # 2. ravi - far enough out for the weather check to matter
    b = s.booking("Ravi Kumar", "Kichha Kharid Kendra", 9, "Paddy", 60, window=1)
    s.alert("Ravi Kumar", "booking_confirmed", "app",
            "Slot confirmed at Kichha Kharid Kendra.", booking_id=b, days_ago=2,
            hi="स्लॉट पक्का: किच्छा खरीद केंद्र।")
    # and yesterday's load, whose payment the bank sent back: his aadhaar
    # isn't linked to the account. every check the portal runs passed
    b = s.booking("Ravi Kumar", "Kichha Kharid Kendra", -1, "Paddy", 40, window=0,
                  status="completed", grade="A", actual=39.6, payment="returned")
    s.alert("Ravi Kumar", "payment_update", "app",
            "Your payment of Rs 91,080 came back from the bank: Aadhaar is not linked to this bank account. "
            "Ask your bank branch to link your Aadhaar to the account. Tell the centre once it is done.",
            booking_id=b, days_ago=0,
            hi="₹91080 का भुगतान बैंक से वापस आ गया: आधार इस बैंक खाते से जुड़ा नहीं है। अपने खरीद केंद्र से संपर्क करें।")

    # 3. mayank - warnings only, money still went out (marked by hand, see build_history)
    b = s.booking("Mayank Verma", "Haridwar Kharid Kendra", -2, "Wheat", 35,
                  status="completed", grade="FAQ", actual=34.2, payment="credited")
    s.alert("Mayank Verma", "payment_update", "app",
            "Payment of 82935.00 has been credited to your bank account.",
            booking_id=b, days_ago=1, hi="₹82935 आपके बैंक खाते में जमा हो गए।")
    s.booking("Mayank Verma", "Haridwar Kharid Kendra", 7, "Wheat", 30, window=1)

    # 4. vivek - blocking flags, so the payment got held
    b = s.booking("Vivek Kumar", "Haridwar Kharid Kendra", -3, "Paddy", 48, window=3,
                  status="completed", grade="A", actual=47.1, payment="held")
    s.alert("Vivek Kumar", "payment_update", "app",
            "Procurement completed but PAYMENT HELD: 2 unresolved detail(s) - aadhaar, bank. "
            "Visit the centre with correct documents to release the payment.",
            booking_id=b, days_ago=2,
            hi="खरीद पूरी हुई, पर भुगतान रुका है। 2 जानकारी ठीक करनी है। "
               "सही दस्तावेज़ लेकर अपने केंद्र जाएं।")

    # 5. aayush - booked at a csc counter, weighed in this morning
    b = s.booking("Aayush Raj", "Rudrapur Mandi Samiti", 0, "Wheat", 28, window=1,
                  status="arrived", grade="B", actual=26.8, payment="weighed")
    s.alert("Aayush Raj", "payment_update", "app",
            "Produce weighed at the centre: 26.8 quintals of Wheat, grade B. "
            "Provisional value 61090.60. Awaiting transaction completion.", booking_id=b,
            hi="आपकी उपज तौली गई: 26.8 क्विंटल गेहूं, ग्रेड B। अनुमानित राशि ₹61090।")

    # 6. siddharth - some history
    b = s.booking("Siddharth Laheja", "Vikasnagar Grain Market", -4, "Wheat", 25,
                  status="completed", grade="A", actual=25.6, payment="billed")
    s.alert("Siddharth Laheja", "payment_update", "app",
            "Transaction complete. Rs 62,080 will be sent to your registered bank account in the centre's next "
            "payment batch.", booking_id=b, days_ago=3,
            hi="लेनदेन पूरा। ₹62080 केंद्र के अगले भुगतान बैच में आपके बैंक खाते में भेजे जाएंगे।")
    s.booking("Siddharth Laheja", "Vikasnagar Grain Market", -1, "Gram", 12, status="cancelled")
    s.booking("Siddharth Laheja", "Vikasnagar Grain Market", 6, "Gram", 20, window=2)

    # A real queue in one window, or every farmer is alone in their slot and
    # the position card says "1 of 1". Aayush is already in this one, so these
    # land behind him and Chandra ends up last with the full picture.
    shared = ("Rudrapur Mandi Samiti", 0, 1)     # centre, today, second window
    s.booking("Vivek Kumar", shared[0], shared[1], "Paddy", 32, window=shared[2],
              status="arrived", grade="FAQ", actual=31.5, payment="weighed")
    s.booking("Mayank Verma", shared[0], shared[1], "Wheat", 22, window=shared[2])
    s.booking("Chandra Bhushan Kumar", shared[0], shared[1], "Wheat", 26, window=shared[2])


def build_history(cur, s):
    """A few days of staff activity, so the supervisor screens have a story.

    Arjun at Haridwar clears three flags without fixing anything and changes a
    payment by hand; Rudrapur is running late; Vivek's payment has been held
    for three days. Everything lines up with the bookings built above.
    """
    def booking(who, centre, status):
        row = s.cur.execute(
            "SELECT b.id, t.id AS txn FROM bookings b JOIN slots sl ON sl.id = b.slot_id"
            " LEFT JOIN transactions t ON t.booking_id = b.id"
            " WHERE b.farmer_id = ? AND sl.centre_id = ? AND b.status = ? ORDER BY sl.date LIMIT 1",
            (s.farmers[who], s.centres[centre], status)).fetchone()
        return (row["id"], row["txn"]) if row else (None, None)

    def at(days_ago, hhmm):
        h, m = (int(x) for x in hhmm.split(":"))
        return (datetime.now() - timedelta(days=days_ago)).replace(
            hour=h, minute=m, second=0, microsecond=0).isoformat(timespec="seconds")

    def log(code, action, days_ago, hhmm, farmer=None, booking_id=None, ref=None,
            detail=None, before=None, after=None, centre=None):
        sid = s.staff[code]
        home = cur.execute("SELECT centre_id FROM staff WHERE id = ?", (sid,)).fetchone()[0]
        cur.execute(
            "INSERT INTO audit_log (staff_id, centre_id, action, farmer_id, booking_id, ref_id,"
            " detail, before_value, after_value, at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sid, s.centres[centre] if centre else home, action,
             s.farmers[farmer] if farmer else None, booking_id, ref, detail,
             None if before is None else json.dumps(before, ensure_ascii=False),
             None if after is None else json.dumps(after, ensure_ascii=False),
             at(days_ago, hhmm)))

    def resolved_flag(who, field, detail, severity, days_ago, hhmm):
        cur.execute(
            "INSERT INTO data_validation_flags (farmer_id, field_flagged, detail, severity, status,"
            " flagged_at, resolved_at) VALUES (?,?,?,?,'resolved',?,?)",
            (s.farmers[who], field, detail, severity, at(days_ago + 2, "09:00"), at(days_ago, hhmm)))
        return cur.lastrowid

    # who was in this morning
    for code, hhmm in (("RUD01", "08:05"), ("RUD02", "08:12"), ("KIC01", "08:40"),
                       ("HAR01", "08:31"), ("VIK01", "09:02")):
        log(code, "sign_in", 0, hhmm)
        cur.execute("UPDATE staff SET last_login = ? WHERE id = ?", (at(0, hhmm), s.staff[code]))
    log("ADMIN", "sign_in", 1, "10:15")
    cur.execute("UPDATE staff SET last_login = ? WHERE id = ?", (at(1, "10:15"), s.staff["ADMIN"]))

    # rudrapur - today's window, and last week's rejected load
    b, _ = booking("Aayush Raj", "Rudrapur Mandi Samiti", "arrived")
    log("RUD01", "weigh", 0, "10:22", "Aayush Raj", b, detail="26.8 quintals of Wheat, grade B")
    b, _ = booking("Vivek Kumar", "Rudrapur Mandi Samiti", "arrived")
    log("RUD01", "weigh", 0, "10:41", "Vivek Kumar", b, detail="31.5 quintals of Paddy, grade FAQ")
    b, _ = booking("Chandra Bhushan Kumar", "Rudrapur Mandi Samiti", "completed")
    log("RUD01", "weigh", 3, "12:34", "Chandra Bhushan Kumar", b, detail="17.4 quintals of Paddy, grade Rejected")
    log("RUD01", "close", 3, "12:40", "Chandra Bhushan Kumar", b, detail="Rejected, nothing payable")
    rudrapur = s.centres["Rudrapur Mandi Samiti"]
    log("RUD02", "delay_set", 0, "11:05", ref=rudrapur, before=0, after=35)
    slot = s.slot("Rudrapur Mandi Samiti", 1, 0)
    log("RUD02", "capacity_change", 1, "17:32", ref=slot, detail="Tomorrow, 08:00 - 10:00", before=8, after=6)
    f = resolved_flag("Chandra Bhushan Kumar", "land", "Land record ID was missing.", "warning", 9, "15:10")
    log("RUD01", "flag_verified", 9, "15:10", "Chandra Bhushan Kumar", ref=f, detail="land: Land record ID was missing.")

    # haridwar - the one a supervisor should look at
    b, _ = booking("Vivek Kumar", "Haridwar Kharid Kendra", "completed")
    log("HAR01", "weigh", 3, "14:08", "Vivek Kumar", b, detail="47.1 quintals of Paddy, grade A")
    log("HAR01", "payment_held", 3, "14:26", "Vivek Kumar", b, detail="2 blocking flag(s) open")
    b, txn = booking("Mayank Verma", "Haridwar Kharid Kendra", "completed")
    log("HAR01", "weigh", 2, "08:42", "Mayank Verma", b, detail="34.2 quintals of Wheat, grade FAQ")
    log("HAR01", "close", 2, "08:57", "Mayank Verma", b, detail="Rs 82,935 to be paid")
    log("HAR01", "payment_manual", 1, "16:05", "Mayank Verma", b, ref=txn,
        detail="Rs 82,935 - bank confirmed the credit on the phone", before="Bill ready", after="Credited")
    for days_ago, hhmm, who, field, detail, sev in (
            (6, "11:20", "Mayank Verma", "land", "Land record ID 'UK/1102' does not match the state format.", "warning"),
            (4, "13:45", "Vivek Kumar", "name_match", "Registered name does not match bank account holder (61% match).", "warning"),
            (1, "15:50", "Mayank Verma", "bank", "IFSC 'BARB0HRDWR' is malformed.", "blocking")):
        f = resolved_flag(who, field, detail, sev, days_ago, hhmm)
        log("HAR01", "flag_verified", days_ago, hhmm, who, ref=f, detail="%s: %s" % (field, detail))

    # vikasnagar and kichha - ordinary days
    b, _ = booking("Siddharth Laheja", "Vikasnagar Grain Market", "completed")
    log("VIK01", "weigh", 4, "11:14", "Siddharth Laheja", b, detail="25.6 quintals of Wheat, grade A")
    log("VIK01", "close", 4, "11:31", "Siddharth Laheja", b, detail="Rs 62,080 to be paid")
    log("VIK01", "call", 1, "17:02", "Siddharth Laheja", b, detail="Payment update")
    log("KIC01", "register_farmer", 8, "12:00", "Ravi Kumar", detail="At the counter")
    b, _ = booking("Ravi Kumar", "Kichha Kharid Kendra", "booked")
    log("KIC01", "call", 1, "15:20", "Ravi Kumar", b, detail="Rain warning")

    log("ADMIN", "staff_create", 10, "10:30", ref=s.staff["HLD01"],
        detail="Pooja Rana (HLD01)", centre="Haldwani Mandi Centre")


def mark_a_centre_late(cur, now):
    """One centre running behind so the booking page has something to show.
    Staff set this by hand from the slots screen."""
    cur.execute("UPDATE procurement_centres SET delay_minutes = 35, delay_set_at = ?"
                " WHERE name = 'Rudrapur Mandi Samiti'", (now,))


def score_storage_risk(cur, now):
    """Weather check over every upcoming booking. Hits the live api, so what
    comes back depends on the actual weather today."""
    out = []
    rows = cur.execute(
        "SELECT b.id, b.farmer_id, f.name, f.district, f.village, s.date, c.name centre"
        "  FROM bookings b JOIN slots s ON s.id=b.slot_id"
        "  JOIN farmers f ON f.id=b.farmer_id"
        "  JOIN procurement_centres c ON c.id=s.centre_id"
        " WHERE b.status='booked' ORDER BY s.date").fetchall()
    for row in rows:
        r = weather.assess_risk(row["district"], row["date"], row["village"])
        cur.execute("UPDATE bookings SET storage_risk=? WHERE id=?", (r["level"], row["id"]))
        out.append((row["name"], row["village"], r))
        if r["level"] != "high":
            continue
        cur.execute(
            "INSERT INTO alerts_log (farmer_id, booking_id, alert_type, channel, message,"
            " message_hi, sent_at) VALUES (?,?,'storage_risk','app',?,?,?)",
            (row["farmer_id"], row["id"],
             "STORAGE RISK: Your slot at %s is %d days away and %s Consider requesting an earlier "
             "slot, or store your produce on a raised, covered platform."
             % (row["centre"], r["lead_days"], r["reason"]),
             "भंडारण जोखिम: %s पर आपका स्लॉट %d दिन दूर है और बारिश का अनुमान है। "
             "उपज ढककर ऊंची जगह रखें।" % (hi(row["centre"]), r["lead_days"]), now))
        # this gets read out if staff ring them, so write it to the farmer
        cur.execute(
            "INSERT INTO alerts_log (farmer_id, booking_id, alert_type, channel, message, sent_at)"
            " VALUES (?,?,'storage_risk','ivr',?,?)",
            (row["farmer_id"], row["id"],
             RAIN_CALL_HI.format(name=row["name"], centre=row["centre"], days=r["lead_days"]),
             now))
    return out


TABLES = ("procurement_centres", "slots", "farmers", "bookings", "transactions",
          "data_validation_flags", "alerts_log")


def main():
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    cur = conn.cursor()
    s = Seeder(cur)
    now = datetime.now().isoformat(timespec="seconds")

    build_centres_and_slots(cur, s)
    missing = build_farmers(cur, s, now)
    if missing:
        conn.rollback()
        conn.close()
        print("These numbers are not in .env, so nothing was written:")
        for m in missing:
            print("   " + m)
        return

    flag_everyone(cur, s, now)
    build_bookings(s)
    mark_a_centre_late(cur, now)
    build_history(cur, s)
    conn.commit()

    risks = score_storage_risk(cur, now)     # last, so every booking exists
    conn.commit()

    counts = {t: cur.execute("SELECT COUNT(*) c FROM " + t).fetchone()["c"] for t in TABLES}
    conn.close()

    print("Database rebuilt.")
    for t in TABLES:
        print("  %-22s %d" % (t, counts[t]))
    print("\n  Staff logins, all with password %s:" % DEMO_PASSWORD)
    for code, name, centre, role in DEMO_STAFF:
        print("    %-6s %-20s %s" % (code, name, "supervisor, every centre" if role == "superadmin" else centre))
    print(CASES)
    print("  Storage risk, from the forecast just now:")
    for name, village, r in risks:
        print("    %-23s %-11s %-5s  from %-11s (%s)"
              % (name, village, r["level"], r["place"], r["source"]))


if __name__ == "__main__":
    main()
