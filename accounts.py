"""Staff accounts and password hashing (werkzeug scrypt)."""

from werkzeug.security import check_password_hash, generate_password_hash

ROLES = ("staff", "superadmin")
DEMO_PASSWORD = "demo123"

# code, name, centre name (None = all centres), role
DEMO_STAFF = [
    ("ADMIN", "District Superadmin", None, "superadmin"),
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
    # plain text never matches, migrate() hashes everything on startup
    if not stored or not is_hashed(stored):
        return False
    return check_password_hash(stored, given or "")


def demo_logins(db_path):
    # accounts still on demo123, the login pages show these as one-click buttons
    import sqlite3
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("SELECT staff_code, password FROM staff WHERE active = 1").fetchall()
    finally:
        con.close()
    return {code for code, stored in rows if check_password(stored, DEMO_PASSWORD)}
