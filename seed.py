"""Builds the database from scratch.

Run:  python seed.py
DROPS every table and recreates it.

The farmer data has been cleared out - we are rebuilding it properly with a
handful of realistic Uttarakhand cases instead of fifty random ones. What is
left is the scaffolding: the centres, their slots, and one staff login so the
admin side is still reachable.

Team phone numbers live in .env (DEMO_FARMER_PHONE_1 / _2) so they are not lost
while the farmer table is empty.
"""

import os
import random
import sqlite3
from datetime import date, datetime, timedelta

import db
import env
from validation import verhoeff_checksum_digit

env.load()
random.seed(26032)

DISTRICTS = [
    ("Udham Singh Nagar", "Uttarakhand"), ("Haridwar", "Uttarakhand"),
    ("Dehradun", "Uttarakhand"), ("Nainital", "Uttarakhand"),
]

CENTRES = [
    ("Rudrapur Mandi Samiti", "Rudrapur, Udham Singh Nagar", "Udham Singh Nagar", 220,
     "Paddy,Wheat,Maize"),
    ("Kichha Kharid Kendra", "Kichha Block", "Udham Singh Nagar", 160, "Paddy,Wheat"),
    ("Haridwar Kharid Kendra", "Jwalapur, Haridwar", "Haridwar", 140, "Wheat,Paddy"),
    ("Vikasnagar Grain Market", "Vikasnagar, Dehradun", "Dehradun", 120, "Wheat,Gram"),
    ("Haldwani Mandi Centre", "Mandi Road, Haldwani", "Nainital", 150, "Paddy,Wheat,Maize"),
]

TIME_WINDOWS = ["08:00 - 10:00", "10:00 - 12:00", "12:00 - 14:00", "14:00 - 16:00"]

# Phones we have verified with vonage, kept here so we know what is on file
# while there are no farmers to attach them to.
TEAM_PHONES = [
    ("Chandra Bhushan Kumar", os.environ.get("DEMO_FARMER_PHONE_1", "")),
    ("Ravi Kumar", os.environ.get("DEMO_FARMER_PHONE_2", "")),
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

    # centres
    for c in CENTRES:
        cur.execute("INSERT INTO procurement_centres (name, location, district, daily_capacity,"
                    " crop_types_accepted) VALUES (?,?,?,?,?)", c)
    centre_ids = [r["id"] for r in cur.execute("SELECT id FROM procurement_centres").fetchall()]

    # one supervisor account, otherwise there is no way into the admin side
    cur.execute("INSERT INTO staff (name, staff_code, password, centre_id) VALUES (?,?,?,NULL)",
                ("District Supervisor", "ADMIN", "demo123"))

    # slots: 3 days back, 14 days forward
    today = date.today()
    for cid in centre_ids:
        cap = cur.execute("SELECT daily_capacity FROM procurement_centres WHERE id=?",
                          (cid,)).fetchone()["daily_capacity"]
        per_slot = max(6, cap // len(TIME_WINDOWS) // 8)
        for d in range(-3, 15):
            day = today + timedelta(days=d)
            if day.weekday() == 6:      # centres closed on sunday
                continue
            for tw in TIME_WINDOWS:
                cur.execute("INSERT INTO slots (centre_id, date, time_window, max_capacity,"
                            " booked_count) VALUES (?,?,?,?,0)",
                            (cid, day.isoformat(), tw, per_slot))

    conn.commit()
    slots = cur.execute("SELECT COUNT(*) c FROM slots").fetchone()["c"]
    conn.close()

    print("Database rebuilt.")
    print("  centres   : %d  (all Uttarakhand)" % len(centre_ids))
    print("  slots     : %d" % slots)
    print("  farmers   : 0  - cleared, to be rebuilt")
    print("  bookings  : 0")
    print("")
    print("  Staff login : ADMIN / demo123")
    print("")
    print("  Phones on file for when farmers go back in:")
    for name, phone in TEAM_PHONES:
        print("    %-24s %s" % (name, phone or "(not set in .env)"))


if __name__ == "__main__":
    main()
