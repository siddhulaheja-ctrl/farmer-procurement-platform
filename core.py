"""Slot booking rules - capacity limits and the per-farmer caps."""

from datetime import date, datetime

from db import execute, get_db, query

CROPS = ["Wheat", "Paddy", "Mustard", "Gram", "Maize", "Bajra"]

# MSP per quintal, RMS 2025-26
# TODO: pull from the state procurement portal instead of hard-coding.
MSP = {"Wheat": 2425.0, "Paddy": 2300.0, "Mustard": 5950.0,
       "Gram": 5650.0, "Maize": 2225.0, "Bajra": 2625.0}

# last season (rabi RMS 2024-25, kharif KMS 2023-24), for the rise shown on the home page
# TODO: double check these against the CACP notification
MSP_PREVIOUS = {"Wheat": 2275.0, "Paddy": 2183.0, "Mustard": 5650.0,
                "Gram": 5440.0, "Maize": 2090.0, "Bajra": 2500.0}

GRADES = ["A", "FAQ", "B", "Rejected"]
GRADE_FACTOR = {"A": 1.00, "FAQ": 1.00, "B": 0.94, "Rejected": 0.0}

# so one farmer can't book up the whole centre
MAX_ACTIVE_BOOKINGS = 3
ACTIVE_STATUSES = ("booked", "arrived")


class BookingError(Exception):
    pass


def _token_no(centre_id, slot_id, seq):
    return "PC%02d-S%03d-%03d" % (centre_id, slot_id, seq)


def slot_availability(slot_row):
    return max(0, slot_row["max_capacity"] - slot_row["booked_count"])


def book_slot(farmer_id, slot_id, crop_type, estimated_quantity):
    slot = query("SELECT * FROM slots WHERE id = ?", (slot_id,), one=True)
    if slot is None:
        raise BookingError("That slot no longer exists.")

    if slot["date"] < date.today().isoformat():
        raise BookingError("That slot date has already passed.")

    centre = query("SELECT * FROM procurement_centres WHERE id = ?", (slot["centre_id"],), one=True)
    accepted = [c.strip() for c in centre["crop_types_accepted"].split(",")]
    if crop_type not in accepted:
        raise BookingError("%s does not procure %s. Accepted crops: %s."
                           % (centre["name"], crop_type, ", ".join(accepted)))

    try:
        qty = float(estimated_quantity)
    except (TypeError, ValueError):
        raise BookingError("Enter a valid quantity in quintals.")
    if qty <= 0 or qty > 500:
        raise BookingError("Quantity must be between 0.1 and 500 quintals.")

    if slot_availability(slot) <= 0:
        raise BookingError("This slot is fully booked. Please choose another time window.")

    ph = ",".join("?" * len(ACTIVE_STATUSES))
    same_day = query(
        "SELECT b.id FROM bookings b JOIN slots s ON s.id = b.slot_id"
        " WHERE b.farmer_id = ? AND s.date = ? AND b.status IN (%s)" % ph,
        (farmer_id, slot["date"]) + ACTIVE_STATUSES, one=True)
    if same_day:
        raise BookingError("You already have a booking on %s. Only one slot per farmer per day "
                           "is allowed so that every farmer gets a turn." % slot["date"])

    active = query(
        "SELECT COUNT(*) AS c FROM bookings WHERE farmer_id = ? AND status IN (%s)" % ph,
        (farmer_id,) + ACTIVE_STATUSES, one=True)["c"]
    if active >= MAX_ACTIVE_BOOKINGS:
        raise BookingError("You already have %d active bookings, which is the maximum. "
                           "Complete or cancel one before booking again." % MAX_ACTIVE_BOOKINGS)

    _take_place(slot_id)
    booking_id = execute(
        "INSERT INTO bookings (farmer_id, slot_id, crop_type, estimated_quantity, status, created_at)"
        " VALUES (?,?,?,?,'booked',?)",
        (farmer_id, slot_id, crop_type, qty, datetime.now().isoformat(timespec="seconds")))
    execute("UPDATE bookings SET token_no = ? WHERE id = ?",
            (_token_no(slot["centre_id"], slot_id, _next_seq(slot_id, booking_id)), booking_id))
    return booking_id


def _take_place(slot_id):
    # check and increment in one statement, two people can't both get the last place
    db = get_db()
    cur = db.execute("UPDATE slots SET booked_count = booked_count + 1"
                     " WHERE id = ? AND booked_count < max_capacity", (slot_id,))
    db.commit()
    if cur.rowcount == 0:
        raise BookingError("This slot is fully booked. Please choose another time window.")


def _next_seq(slot_id, booking_id):
    # not COUNT(*): a booking moved out of the slot would free its number for a duplicate
    return query("SELECT COALESCE(MAX(CAST(substr(token_no, -3) AS INTEGER)), 0) + 1 AS n"
                 " FROM bookings WHERE slot_id = ? AND id != ?", (slot_id, booking_id), one=True)["n"]


def cancel_booking(booking_id, farmer_id=None):
    b = query("SELECT * FROM bookings WHERE id = ?", (booking_id,), one=True)
    if b is None:
        raise BookingError("Booking not found.")
    if farmer_id is not None and b["farmer_id"] != farmer_id:
        raise BookingError("That booking does not belong to you.")
    if b["status"] != "booked":
        raise BookingError("Only an upcoming booking can be cancelled (this one is '%s')." % b["status"])
    execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
    execute("UPDATE slots SET booked_count = MAX(0, booked_count - 1) WHERE id = ?", (b["slot_id"],))
    return b


def reschedule_booking(booking_id, new_slot_id, farmer_id=None):
    b = query("SELECT * FROM bookings WHERE id = ?", (booking_id,), one=True)
    if b is None:
        raise BookingError("Booking not found.")
    if farmer_id is not None and b["farmer_id"] != farmer_id:
        raise BookingError("That booking does not belong to you.")
    if b["status"] != "booked":
        raise BookingError("Only an upcoming booking can be rescheduled.")
    if int(new_slot_id) == b["slot_id"]:
        raise BookingError("That is already your current slot.")

    new_slot = query("SELECT * FROM slots WHERE id = ?", (new_slot_id,), one=True)
    if new_slot is None:
        raise BookingError("That slot no longer exists.")
    if new_slot["date"] < date.today().isoformat():
        raise BookingError("That slot date has already passed.")
    if slot_availability(new_slot) <= 0:
        raise BookingError("That slot is fully booked.")
    centre = query("SELECT * FROM procurement_centres WHERE id = ?", (new_slot["centre_id"],), one=True)
    if b["crop_type"] not in [c.strip() for c in centre["crop_types_accepted"].split(",")]:
        raise BookingError("%s does not procure %s." % (centre["name"], b["crop_type"]))

    ph = ",".join("?" * len(ACTIVE_STATUSES))
    clash = query(
        "SELECT b.id FROM bookings b JOIN slots s ON s.id = b.slot_id"
        " WHERE b.farmer_id = ? AND s.date = ? AND b.id != ? AND b.status IN (%s)" % ph,
        (b["farmer_id"], new_slot["date"], booking_id) + ACTIVE_STATUSES, one=True)
    if clash:
        raise BookingError("You already have another booking on %s." % new_slot["date"])

    _take_place(new_slot_id)
    execute("UPDATE slots SET booked_count = MAX(0, booked_count - 1) WHERE id = ?", (b["slot_id"],))
    execute("UPDATE bookings SET slot_id = ?, token_no = ? WHERE id = ?",
            (new_slot_id, _token_no(new_slot["centre_id"], new_slot_id, _next_seq(new_slot_id, booking_id)),
             booking_id))
    return b


def queue_position(booking_id):
    # position in the slot, not an ETA - nobody at the counter would keep an ETA updated
    b = query("SELECT id, slot_id, status FROM bookings WHERE id = ?", (booking_id,), one=True)
    if b is None or b["status"] not in ACTIVE_STATUSES:
        return None

    ph = ",".join("?" * len(ACTIVE_STATUSES))
    rows = query("SELECT id, status FROM bookings WHERE slot_id = ? AND status IN (%s)"
                 " ORDER BY id" % ph, (b["slot_id"],) + ACTIVE_STATUSES)
    ids = [r["id"] for r in rows]
    if booking_id not in ids:
        return None
    place = ids.index(booking_id)

    return {
        "position": place + 1,
        "total": len(ids),
        "done_ahead": sum(1 for r in rows[:place] if r["status"] == "arrived"),
        "waiting_ahead": sum(1 for r in rows[:place] if r["status"] == "booked"),
    }


def centre_delay(centre_id):
    row = query("SELECT delay_minutes, delay_set_at FROM procurement_centres WHERE id = ?",
                (centre_id,), one=True)
    if row is None or not row["delay_minutes"]:
        return None
    stale_mins = None
    if row["delay_set_at"]:
        try:
            set_at = datetime.fromisoformat(row["delay_set_at"])
            stale_mins = int((datetime.now() - set_at).total_seconds() // 60)
        except ValueError:
            pass
    return {"minutes": row["delay_minutes"], "set_at": row["delay_set_at"],
            "stale_mins": stale_mins}


# max moisture % for FAQ, roughly the published norms
MOISTURE_MAX = {"Wheat": 12.0, "Paddy": 17.0, "Maize": 14.0, "Gram": 14.0, "Mustard": 8.0, "Bajra": 12.0}
FOREIGN_FAQ = 0.75       # % foreign matter
FOREIGN_B = 2.0


def suggest_grade(crop_type, moisture, foreign_matter):
    if moisture is None or foreign_matter is None:
        return None
    limit = MOISTURE_MAX.get(crop_type, 14.0)
    if moisture > limit + 2 or foreign_matter > FOREIGN_B:
        return "Rejected"
    if moisture > limit or foreign_matter > FOREIGN_FAQ:
        return "B"
    if moisture <= limit - 1.5 and foreign_matter <= 0.25:
        return "A"
    return "FAQ"


def net_quantity(gross_quintals, bags, bag_weight_kg):
    return round(max(0.0, gross_quintals - (bags or 0) * (bag_weight_kg or 0) / 100.0), 2)


def compute_amount(crop_type, quantity, grade):
    rate = MSP.get(crop_type, 2000.0) * GRADE_FACTOR.get(grade, 1.0)
    return round(rate, 2), round(rate * float(quantity), 2)
