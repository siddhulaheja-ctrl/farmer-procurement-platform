"""Seed the demo database with realistic-looking mock data (spec guideline #2).

Run:  python seed.py
This DROPS and recreates every table.
"""

import os
import random
import sqlite3
from datetime import date, datetime, timedelta

from faker import Faker

import db
import env
from validation import verhoeff_checksum_digit

env.load()

fake = Faker("en_IN")
Faker.seed(26032)
random.seed(26032)

DISTRICTS = [
    ("Karnal", "Haryana"), ("Kurukshetra", "Haryana"), ("Sirsa", "Haryana"),
    ("Ludhiana", "Punjab"), ("Patiala", "Punjab"), ("Sangrur", "Punjab"),
    ("Hoshangabad", "Madhya Pradesh"), ("Vidisha", "Madhya Pradesh"),
    ("Udham Singh Nagar", "Uttarakhand"), ("Haridwar", "Uttarakhand"),
]

CENTRES = [
    ("Karnal Mandi Procurement Centre", "Sector 12, Karnal", "Karnal", 240, "Wheat,Paddy,Mustard"),
    ("Nilokheri Kharid Kendra", "Nilokheri Block", "Karnal", 160, "Wheat,Paddy"),
    ("Shahabad Grain Market", "GT Road, Shahabad", "Kurukshetra", 200, "Wheat,Paddy,Maize"),
    ("Sirsa Anaj Mandi Centre", "New Grain Market, Sirsa", "Sirsa", 180, "Wheat,Mustard,Bajra"),
    ("Khanna Procurement Yard", "Khanna, Ludhiana", "Ludhiana", 300, "Paddy,Wheat,Maize"),
    ("Rajpura Kharid Kendra", "Rajpura, Patiala", "Patiala", 150, "Wheat,Gram"),
    ("Sangrur District Centre", "Civil Lines, Sangrur", "Sangrur", 170, "Paddy,Wheat"),
    ("Itarsi Upaj Mandi Centre", "Itarsi, Hoshangabad", "Hoshangabad", 190, "Wheat,Gram,Maize"),
    ("Rudrapur Mandi Samiti", "Rudrapur, Udham Singh Nagar", "Udham Singh Nagar", 220,
     "Paddy,Wheat,Maize"),
    ("Haridwar Kharid Kendra", "Jwalapur, Haridwar", "Haridwar", 140, "Wheat,Paddy"),
]

TIME_WINDOWS = ["08:00 - 10:00", "10:00 - 12:00", "12:00 - 14:00", "14:00 - 16:00"]

# Farmers seeded with deliberately broken details so the Data Mismatch
# dashboard has content to show on demo day.
BROKEN_KINDS = ["aadhaar_typo", "aadhaar_short", "ifsc_bad",
                "name_mismatch", "land_missing", "acct_short"]

# Real team numbers for testing calls. These are actual people's phones so they
# live in .env, not in here - the repo is public. Without .env you get harmless
# placeholders and the calls just go to the demo phone.
TEAM_FARMERS = [
    ("Chandra Bhushan Kumar", os.environ.get("DEMO_FARMER_PHONE_1", "9000000011"),
     "Kichha", "Udham Singh Nagar"),
    ("Ravi Kumar", os.environ.get("DEMO_FARMER_PHONE_2", "9000000012"),
     "Jwalapur", "Haridwar"),
]


def valid_aadhaar():
    payload = str(random.randint(2, 9)) + "".join(random.choice("0123456789") for _ in range(10))
    return payload + verhoeff_checksum_digit(payload)


def valid_ifsc():
    bank = "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(4))
    branch = "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(6))
    return bank + "0" + branch


def valid_land(district):
    return "%s-%06d-%02d" % (district[:3].upper(), random.randint(1000, 999999),
                             random.randint(1, 40))


def main():
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec="seconds")

    # centres
    for c in CENTRES:
        cur.execute("INSERT INTO procurement_centres (name, location, district, daily_capacity,"
                    " crop_types_accepted) VALUES (?,?,?,?,?)", c)
    centre_ids = [r["id"] for r in cur.execute("SELECT id FROM procurement_centres").fetchall()]

    # staff
    for i, cid in enumerate(centre_ids, start=1):
        cur.execute("INSERT INTO staff (name, staff_code, password, centre_id) VALUES (?,?,?,?)",
                    (fake.name(), "STAFF%02d" % i, "demo123", cid))
    # A district-level supervisor who can see every centre.
    cur.execute("INSERT INTO staff (name, staff_code, password, centre_id) VALUES (?,?,?,NULL)",
                ("R. Sharma (District Supervisor)", "ADMIN", "demo123"))

    # slots: 3 days back, 14 days forward
    today = date.today()
    for cid in centre_ids:
        cap = cur.execute("SELECT daily_capacity FROM procurement_centres WHERE id=?",
                          (cid,)).fetchone()["daily_capacity"]
        per_slot = max(6, cap // len(TIME_WINDOWS) // 8)
        for d in range(-3, 15):
            day = today + timedelta(days=d)
            if day.weekday() == 6:      # centres closed on Sunday
                continue
            for tw in TIME_WINDOWS:
                cur.execute("INSERT INTO slots (centre_id, date, time_window, max_capacity,"
                            " booked_count) VALUES (?,?,?,?,0)",
                            (cid, day.isoformat(), tw, per_slot))

    # farmers
    farmer_ids = []
    for i in range(48):
        name = fake.name()
        district = random.choice(DISTRICTS)[0]
        # sequential on purpose - faker makes numbers that look real and
        # might actually be someone's, and this app can place calls
        phone = "90000001%02d" % i

        aadhaar = valid_aadhaar()
        acct = str(random.randint(10 ** 10, 10 ** 15))
        ifsc = valid_ifsc()
        land = valid_land(district)
        acct_name = name

        # Break roughly one in four records, cycling through the failure modes.
        if i % 4 == 3:
            kind = BROKEN_KINDS[(i // 4) % len(BROKEN_KINDS)]
            if kind == "aadhaar_typo":
                aadhaar = aadhaar[:-1] + str((int(aadhaar[-1]) + 3) % 10)
            elif kind == "aadhaar_short":
                aadhaar = aadhaar[:10]
            elif kind == "ifsc_bad":
                ifsc = ifsc.replace("0", "X", 1)
            elif kind == "name_mismatch":
                acct_name = fake.name()
            elif kind == "land_missing":
                land = ""
            elif kind == "acct_short":
                acct = acct[:6]

        cur.execute(
            "INSERT INTO farmers (name, phone_number, aadhaar_number, bank_account, ifsc_code,"
            " bank_name_on_account, land_record_id, village, district, registered_via, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (name, phone, aadhaar, acct, ifsc, acct_name, land, fake.city(), district,
             random.choice(["self", "self", "csc", "staff"]), now))
        farmer_ids.append(cur.lastrowid)

    # A guaranteed-clean demo login, easy to type on stage.
    cur.execute(
        "INSERT INTO farmers (name, phone_number, aadhaar_number, bank_account, ifsc_code,"
        " bank_name_on_account, land_record_id, village, district, registered_via, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,'self',?)",
        ("Ramesh Kumar", "9000000001", valid_aadhaar(), "34129087651234", "PUNB0123456",
         "Ramesh Kumar", valid_land("Karnal"), "Nilokheri", "Karnal", now))
    demo_farmer = cur.lastrowid
    farmer_ids.append(demo_farmer)

    # A second demo login that is deliberately dirty, for showing Feature A live.
    cur.execute(
        "INSERT INTO farmers (name, phone_number, aadhaar_number, bank_account, ifsc_code,"
        " bank_name_on_account, land_record_id, village, district, registered_via, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,'csc',?)",
        ("Sunita Devi", "9000000002", "123456789012", "4471", "SBIN12345",
         "Sunita D. Yadav", "", "Rampura", "Sirsa", now))
    farmer_ids.append(cur.lastrowid)

    # the two team members whose phones are verified with vonage, so the Call
    # button on their bookings actually rings them
    team_ids = []
    for name, phone, village, district in TEAM_FARMERS:
        cur.execute(
            "INSERT INTO farmers (name, phone_number, aadhaar_number, bank_account, ifsc_code,"
            " bank_name_on_account, land_record_id, village, district, registered_via, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,'self',?)",
            (name, phone, valid_aadhaar(), str(random.randint(10 ** 12, 10 ** 13)),
             valid_ifsc(), name, valid_land(district), village, district, now))
        team_ids.append(cur.lastrowid)
        farmer_ids.append(cur.lastrowid)

    conn.commit()

    # bookings
    slots = cur.execute("SELECT * FROM slots ORDER BY date, id").fetchall()
    past = [s for s in slots if s["date"] < today.isoformat()]
    future = [s for s in slots if s["date"] >= today.isoformat()]

    def make_booking(fid, slot, status):
        centre = cur.execute("SELECT * FROM procurement_centres WHERE id=?",
                             (slot["centre_id"],)).fetchone()
        crop = random.choice([c.strip() for c in centre["crop_types_accepted"].split(",")])
        qty = round(random.uniform(8, 90), 1)
        cur.execute("INSERT INTO bookings (farmer_id, slot_id, crop_type, estimated_quantity,"
                    " status, created_at) VALUES (?,?,?,?,?,?)",
                    (fid, slot["id"], crop, qty, status, now))
        bid = cur.lastrowid
        cur.execute("UPDATE slots SET booked_count = booked_count + 1 WHERE id=?", (slot["id"],))
        seq = cur.execute("SELECT COUNT(*) AS c FROM bookings WHERE slot_id=?",
                          (slot["id"],)).fetchone()["c"]
        cur.execute("UPDATE bookings SET token_no=? WHERE id=?",
                    ("PC%02d-S%03d-%03d" % (slot["centre_id"], slot["id"], seq), bid))
        return bid, crop, qty

    from core import compute_amount

    # Completed history so payment statuses look lived-in.
    completed = 0
    for _ in range(34):
        fid = random.choice(farmer_ids)
        slot = random.choice(past)
        bid, crop, qty = make_booking(fid, slot, "completed")
        actual = round(qty * random.uniform(0.88, 1.06), 1)
        grade = random.choices(["A", "FAQ", "B", "Rejected"], weights=[30, 45, 20, 5])[0]
        rate, total = compute_amount(crop, actual, grade)
        pstatus = random.choices(["completed", "processing", "pending", "failed"],
                                 weights=[55, 20, 15, 10])[0]
        pdate = None
        if pstatus == "completed":
            pdate = (datetime.now() - timedelta(days=random.randint(1, 20))
                     ).isoformat(timespec="seconds")
        cur.execute("INSERT INTO transactions (booking_id, actual_quantity, quality_grade,"
                    " price_per_unit, total_amount, payment_status, payment_date)"
                    " VALUES (?,?,?,?,?,?,?)", (bid, actual, grade, rate, total, pstatus, pdate))
        completed += 1

    # Upcoming bookings spread across centres and dates.
    upcoming = 0
    for _ in range(46):
        make_booking(random.choice(farmer_ids), random.choice(future), "booked")
        upcoming += 1

    # Guaranteed demo bookings for Ramesh: one soon, one far out (storage risk).
    near = [s for s in future if s["date"] == (today + timedelta(days=2)).isoformat()]
    far = [s for s in future if s["date"] >= (today + timedelta(days=9)).isoformat()]
    if near:
        make_booking(demo_farmer, near[0], "booked")
        upcoming += 1
    if far:
        make_booking(demo_farmer, far[0], "booked")
        upcoming += 1

    # One booking each for the team farmers so there is something to ring about.
    # Chandra gets a far off slot in a wet district, which trips the storage
    # risk warning. Ravi gets a completed sale whose payment failed.
    us_nagar = cur.execute("SELECT id FROM procurement_centres WHERE district='Udham Singh Nagar'",
                           ).fetchone()["id"]
    haridwar = cur.execute("SELECT id FROM procurement_centres WHERE district='Haridwar'",
                           ).fetchone()["id"]
    if len(team_ids) == 2:
        far_us = [s for s in future
                  if s["centre_id"] == us_nagar and s["date"] >= (today + timedelta(days=8)).isoformat()]
        if far_us:
            make_booking(team_ids[0], far_us[0], "booked")
            upcoming += 1

        past_hw = [s for s in past if s["centre_id"] == haridwar]
        if past_hw:
            bid, crop, qty = make_booking(team_ids[1], past_hw[0], "completed")
            rate, total = compute_amount(crop, qty, "FAQ")
            cur.execute("INSERT INTO transactions (booking_id, actual_quantity, quality_grade,"
                        " price_per_unit, total_amount, payment_status, payment_date)"
                        " VALUES (?,?,?,?,?,'failed',NULL)", (bid, qty, "FAQ", rate, total))
            completed += 1

    conn.commit()
    conn.close()

    # validation + storage-risk pass
    # Run inside the real Flask app context so the same code paths used at
    # registration time are exercised here.
    from app import create_app
    app = create_app()
    with app.app_context():
        from validation import validate_and_flag
        flagged = sum(1 for fid in farmer_ids if validate_and_flag(fid))
        from weather import rescan_all_upcoming
        results = rescan_all_upcoming()
        high = sum(1 for r in results if r and r["level"] == "high")

    print("Seed complete.")
    print("  centres      : %d" % len(centre_ids))
    print("  slots        : %d" % len(slots))
    print("  farmers      : %d  (%d carry data-mismatch flags)" % (len(farmer_ids), flagged))
    print("  bookings     : %d completed + %d upcoming" % (completed, upcoming))
    print("  storage risk : %d upcoming bookings flagged HIGH" % high)
    print("")
    for name, phone, _v, _d in TEAM_FARMERS:
        print("  Team farmer  : %-12s (%s)" % (phone, name))
    print("  Farmer login : 9000000001  (Ramesh Kumar - clean record)")
    print("  Farmer login : 9000000002  (Sunita Devi  - multiple data mismatches)")
    print("  OTP          : 123456")
    print("  Staff login  : ADMIN / demo123    (all centres)")
    print("  Staff login  : STAFF01 / demo123  (single centre)")


if __name__ == "__main__":
    main()
