"""Builds the database from scratch.

Run:  python seed.py
DROPS every table and recreates it.

Six farmers, all real people on the team whose numbers are registered in the
vonage dashboard, so any of them can actually be rung from the staff screens.
Between them they cover every state the app can be in - CASES below says which
farmer is which. Everyone is in Uttarakhand, and every village either resolves
in the weather api or falls back to its district town.

Phone numbers are read from .env so they stay out of the repo.
"""

import os
import sqlite3
from datetime import date, datetime, timedelta

import core
import db
import env
import weather
from validation import run_checks

env.load()

CENTRES = [
    ("Rudrapur Mandi Samiti", "Rudrapur, Udham Singh Nagar", "Udham Singh Nagar", 220,
     "Paddy,Wheat,Maize"),
    ("Kichha Kharid Kendra", "Kichha Block", "Udham Singh Nagar", 160, "Paddy,Wheat"),
    ("Haridwar Kharid Kendra", "Jwalapur, Haridwar", "Haridwar", 140, "Wheat,Paddy"),
    ("Vikasnagar Grain Market", "Vikasnagar, Dehradun", "Dehradun", 120, "Wheat,Gram"),
    ("Haldwani Mandi Centre", "Mandi Road, Haldwani", "Nainital", 150, "Paddy,Wheat,Maize"),
]

TIME_WINDOWS = ["08:00 - 10:00", "10:00 - 12:00", "12:00 - 14:00", "14:00 - 16:00"]

# What each farmer is here to show. Kept beside the data so it does not drift
# the moment somebody edits a row.
CASES = """
  1  Chandra Bhushan Kumar   clean record, slot in 3 days     -> token reminder call
  2  Ravi Kumar              clean, slot 9 days out           -> storage risk + rain call
  3  Mayank Verma            warning flags (name, land id)    -> payment still clears
  4  Vivek Kumar             blocking flags (aadhaar, ifsc)   -> payment HELD, documents call
  5  Aayush Raj              registered at a CSC counter      -> arrived, grade B price cut
  6  Siddharth Laheja        history: paid, cancelled, upcoming
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

# aadhaar, account no, ifsc, name the bank has, land record id.
# All valid except where the case needs otherwise. Vivek's aadhaar fails the
# verhoeff check the way a mistyped one would and his ifsc has no 0 in the
# fifth position. Mayank's account is in his father's name, which is the single
# most common reason a DBT payment bounces, and his land id is in the older
# format the tehsil used to hand out.
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
    """Slot dates skip Sundays, so step past one if we land on it."""
    d = date.today() + timedelta(days=offset)
    return d + timedelta(days=1) if d.weekday() == 6 else d


class Seeder:
    """Thin wrapper so the case list below reads as data rather than SQL."""

    def __init__(self, cur):
        self.cur = cur
        self.centres = {}
        self.farmers = {}

    def slot(self, centre, day, window):
        row = self.cur.execute(
            "SELECT id FROM slots WHERE centre_id=? AND date=? AND time_window=?",
            (self.centres[centre], workday(day).isoformat(), TIME_WINDOWS[window])).fetchone()
        return row["id"]

    def booking(self, who, centre, day, crop, qty, status="booked", window=0,
                grade=None, actual=None, payment=None):
        """Writes a booking straight in. Deliberately not going through
        core.book_slot, which refuses past dates - half of these are history."""
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
            rate, total = core.compute_amount(crop, actual, grade)
            paid = datetime.now().isoformat(timespec="seconds") if payment == "completed" else None
            self.cur.execute(
                "INSERT INTO transactions (booking_id, actual_quantity, quality_grade,"
                " price_per_unit, total_amount, payment_status, payment_date)"
                " VALUES (?,?,?,?,?,?,?)", (bid, actual, grade, rate, total, payment, paid))
        return bid

    def alert(self, who, kind, channel, message, booking_id=None, days_ago=0):
        self.cur.execute(
            "INSERT INTO alerts_log (farmer_id, booking_id, alert_type, channel, message, sent_at,"
            " read_flag) VALUES (?,?,?,?,?,?,?)",
            (self.farmers[who], booking_id, kind, channel, message,
             (datetime.now() - timedelta(days=days_ago)).isoformat(timespec="seconds"),
             1 if days_ago > 2 else 0))


def build_centres_and_slots(cur, s):
    for c in CENTRES:
        cur.execute("INSERT INTO procurement_centres (name, location, district, daily_capacity,"
                    " crop_types_accepted) VALUES (?,?,?,?,?)", c)
        s.centres[c[0]] = cur.lastrowid

    cur.execute("INSERT INTO staff (name, staff_code, password, centre_id) VALUES (?,?,?,NULL)",
                ("District Supervisor", "ADMIN", "demo123"))

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
    """Returns the names of anyone whose number is missing from .env."""
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
    return missing


def flag_everyone(cur, s, now):
    """run_checks is pure, so it works out here without an app context."""
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
                    days_ago=5)


def build_bookings(s):
    # 1. chandra - upcoming slot, close enough that storage is not a worry.
    #    also a load that got turned away at the gate last week, so the
    #    grade -> zero rupees path has something in it.
    b = s.booking("Chandra Bhushan Kumar", "Rudrapur Mandi Samiti", 3, "Wheat", 42)
    s.alert("Chandra Bhushan Kumar", "booking_confirmed", "app",
            "Slot confirmed at Rudrapur Mandi Samiti. Bring your gate pass and Aadhaar card.",
            booking_id=b, days_ago=1)
    s.booking("Chandra Bhushan Kumar", "Rudrapur Mandi Samiti", -3, "Paddy", 18, window=2,
              status="completed", grade="Rejected", actual=17.4, payment="failed")

    # 2. ravi - far enough out that the weather check has something to say
    b = s.booking("Ravi Kumar", "Kichha Kharid Kendra", 9, "Paddy", 60, window=1)
    s.alert("Ravi Kumar", "booking_confirmed", "app",
            "Slot confirmed at Kichha Kharid Kendra.", booking_id=b, days_ago=2)

    # 3. mayank - warnings only, so the money still went out
    b = s.booking("Mayank Verma", "Haridwar Kharid Kendra", -2, "Wheat", 35,
                  status="completed", grade="FAQ", actual=34.2, payment="completed")
    s.alert("Mayank Verma", "payment_update", "app",
            "Payment of 82935.00 has been credited to your bank account.",
            booking_id=b, days_ago=1)
    s.booking("Mayank Verma", "Haridwar Kharid Kendra", 7, "Wheat", 30, window=1)

    # 4. vivek - blocking flags, so completing the transaction held the payment
    b = s.booking("Vivek Kumar", "Haridwar Kharid Kendra", -3, "Paddy", 48, window=3,
                  status="completed", grade="A", actual=47.1, payment="failed")
    s.alert("Vivek Kumar", "payment_update", "app",
            "Procurement completed but PAYMENT HELD: 2 unresolved detail(s) - aadhaar, bank. "
            "Visit the centre with correct documents to release the payment.",
            booking_id=b, days_ago=2)

    # 5. aayush - booked at the csc counter, weighed in this morning
    b = s.booking("Aayush Raj", "Rudrapur Mandi Samiti", 0, "Wheat", 28, window=1,
                  status="arrived", grade="B", actual=26.8, payment="pending")
    s.alert("Aayush Raj", "payment_update", "app",
            "Produce weighed at the centre: 26.8 quintals of Wheat, grade B. "
            "Provisional value 61090.60. Awaiting transaction completion.", booking_id=b)

    # 6. siddharth - a bit of history behind him
    b = s.booking("Siddharth Laheja", "Vikasnagar Grain Market", -4, "Wheat", 25,
                  status="completed", grade="A", actual=25.6, payment="processing")
    s.alert("Siddharth Laheja", "payment_update", "app",
            "Transaction complete. 62080.00 is being credited to your registered bank account. "
            "Expect credit within 48-72 hours.", booking_id=b, days_ago=3)
    s.booking("Siddharth Laheja", "Vikasnagar Grain Market", -1, "Gram", 12, status="cancelled")
    s.booking("Siddharth Laheja", "Vikasnagar Grain Market", 6, "Gram", 20, window=2)


def score_storage_risk(cur, now):
    """Run the weather check over every upcoming booking. Hits the live api, so
    what comes back depends on the actual weather in Uttarakhand today."""
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
            "INSERT INTO alerts_log (farmer_id, booking_id, alert_type, channel, message, sent_at)"
            " VALUES (?,?,'storage_risk','app',?,?)",
            (row["farmer_id"], row["id"],
             "STORAGE RISK: Your slot at %s is %d days away and %s Consider requesting an earlier "
             "slot, or store your produce on a raised, covered platform."
             % (row["centre"], r["lead_days"], r["reason"]), now))
        # this is the text that actually gets read out if staff ring them, so
        # it has to be a message for the farmer and not a note for us
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
    conn.commit()

    risks = score_storage_risk(cur, now)     # last, so every booking exists
    conn.commit()

    counts = {t: cur.execute("SELECT COUNT(*) c FROM " + t).fetchone()["c"] for t in TABLES}
    conn.close()

    print("Database rebuilt.")
    for t in TABLES:
        print("  %-22s %d" % (t, counts[t]))
    print("\n  Staff login: ADMIN / demo123")
    print(CASES)
    print("  Storage risk, from the forecast just now:")
    for name, village, r in risks:
        print("    %-23s %-11s %-5s  from %-11s (%s)"
              % (name, village, r["level"], r["place"], r["source"]))


if __name__ == "__main__":
    main()
