"""Staff accounts: the demo roster and password hashing.

Passwords are stored as werkzeug hashes (scrypt), never as the password.
Werkzeug already ships with Flask, so this needs no new dependency.
"""

from werkzeug.security import check_password_hash, generate_password_hash

ROLES = ("staff", "superadmin")
DEMO_PASSWORD = "demo123"

# code, name, centre (by name, None for the supervisor), role.
# One supervisor who sees every centre, and counter staff locked to theirs.
DEMO_STAFF = [
    ("ADMIN", "District Supervisor", None, "superadmin"),
    ("RUD01", "Suresh Rawat", "Rudrapur Mandi Samiti", "staff"),
    ("RUD02", "Meena Bisht", "Rudrapur Mandi Samiti", "staff"),
    ("KIC01", "Deepak Pant", "Kichha Kharid Kendra", "staff"),
    ("HAR01", "Arjun Negi", "Haridwar Kharid Kendra", "staff"),
    ("VIK01", "Kavita Joshi", "Vikasnagar Grain Market", "staff"),
    ("HLD01", "Pooja Rana", "Haldwani Mandi Centre", "staff"),
]


def hash_password(password):
    return generate_password_hash(password)


def is_hashed(stored):
    return (stored or "").startswith(("scrypt:", "pbkdf2:"))


def check_password(stored, given):
    """True if `given` matches. An unhashed stored value never matches - the
    migration hashes those on startup, so one left over means something is off."""
    if not stored or not is_hashed(stored):
        return False
    return check_password_hash(stored, given or "")
