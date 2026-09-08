"""Slot booking rules - capacity limits and the per-farmer caps."""

from datetime import date, datetime

from db import execute, query

CROPS = ["Wheat", "Paddy", "Mustard", "Gram", "Maize", "Bajra"]

# Minimum Support Price per quintal (INR), RMS 2025-26 indicative figures.
# TODO: pull from the state procurement portal instead of hard-coding.
MSP = {"Wheat": 2425.0, "Paddy": 2300.0, "Mustard": 5950.0,
       "Gram": 5650.0, "Maize": 2225.0, "Bajra": 2625.0}

GRADES = ["A", "FAQ", "B", "Rejected"]
# Price adjustment applied to MSP by quality grade.
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
    """Makes a booking. Raises BookingError if any rule fails."""
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

    # Rule 1: capacity enforcement
    if slot_availability(slot) <= 0:
        raise BookingError("This slot is fully booked. Please choose another time window.")

    # Rule 2: fair access
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

    booking_id = execute(
        "INSERT INTO bookings (farmer_id, slot_id, crop_type, estimated_quantity, status, created_at)"
        " VALUES (?,?,?,?,'booked',?)",
        (farmer_id, slot_id, crop_type, qty, datetime.now().isoformat(timespec="seconds")))

    execute("UPDATE slots SET booked_count = booked_count + 1 WHERE id = ?", (slot_id,))
    seq = query("SELECT COUNT(*) AS c FROM bookings WHERE slot_id = ?", (slot_id,), one=True)["c"]
    token = _token_no(slot["centre_id"], slot_id, seq)
    execute("UPDATE bookings SET token_no = ? WHERE id = ?", (token, booking_id))
    return booking_id


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
    """Move a booking to a different slot, re-running the capacity check."""
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

    ph = ",".join("?" * len(ACTIVE_STATUSES))
    clash = query(
        "SELECT b.id FROM bookings b JOIN slots s ON s.id = b.slot_id"
        " WHERE b.farmer_id = ? AND s.date = ? AND b.id != ? AND b.status IN (%s)" % ph,
        (b["farmer_id"], new_slot["date"], booking_id) + ACTIVE_STATUSES, one=True)
    if clash:
        raise BookingError("You already have another booking on %s." % new_slot["date"])

    execute("UPDATE slots SET booked_count = MAX(0, booked_count - 1) WHERE id = ?", (b["slot_id"],))
    execute("UPDATE slots SET booked_count = booked_count + 1 WHERE id = ?", (new_slot_id,))
    execute("UPDATE bookings SET slot_id = ? WHERE id = ?", (new_slot_id, booking_id))
    seq = query("SELECT COUNT(*) AS c FROM bookings WHERE slot_id = ?", (new_slot_id,), one=True)["c"]
    execute("UPDATE bookings SET token_no = ? WHERE id = ?",
            (_token_no(new_slot["centre_id"], new_slot_id, seq), booking_id))
    return b


def queue_position(booking_id):
    """Where this booking sits in its own slot window.

    Deliberately not an ETA. An ETA needs somebody at the counter marking each
    farmer served the moment it happens, and they are busy weighing grain and
    arguing about moisture - the logging goes patchy and the estimate drifts.
    A wrong ETA is worse than none, because the farmer who trusted it and went
    for chai comes back to find he has been passed.

    So this counts positions, which cannot drift, and reports how many ahead
    have already been processed - which staff record anyway as part of taking
    delivery, so it costs nobody an extra tap.

    Returns None if the booking is not waiting for anything.
    """
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
    """How far behind the centre says it is running, with how long ago they
    said it. The staleness is shown too - a farmer should be able to see that
    the number is four hours old and weigh it accordingly."""
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


def compute_amount(crop_type, quantity, grade):
    rate = MSP.get(crop_type, 2000.0) * GRADE_FACTOR.get(grade, 1.0)
    return round(rate, 2), round(rate * float(quantity), 2)
