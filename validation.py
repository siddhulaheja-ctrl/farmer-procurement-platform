"""Novelty Feature A - Data Mismatch Pre-Validation.

Existing state systems (e-Kharid, e-Uparjan, P-PAS) reject payments *after*
procurement because the farmer's Aadhaar / bank / land-record details don't
match. The farmer finds out weeks later. This module runs those checks at
REGISTRATION time and raises flags that staff can resolve before the slot date.

All checks run against mock data held in our own `farmers` table.
TODO: in production, replace check_aadhaar() with a real UIDAI demographic-auth
call and check_bank() with an NPCI penny-drop verification.
"""

import re
from datetime import datetime
from difflib import SequenceMatcher

from db import execute, query

# Verhoeff algorithm tables - this is the real checksum scheme Aadhaar uses,
# so a randomly typed 12-digit number will almost always fail it.
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_valid(number: str) -> bool:
    c = 0
    for i, digit in enumerate(reversed(number)):
        c = _D[c][_P[i % 8][int(digit)]]
    return c == 0


def verhoeff_checksum_digit(payload: str) -> str:
    """Return the check digit that makes `payload` a valid Verhoeff number.
    Used by the seeder to generate realistic-looking valid mock Aadhaars."""
    _inv = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]
    c = 0
    for i, digit in enumerate(reversed(payload)):
        c = _D[c][_P[(i + 1) % 8][int(digit)]]
    return str(_inv[c])


IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
LAND_RE = re.compile(r"^[A-Z]{2,4}-\d{3,6}-\d{1,3}$")
NAME_MATCH_THRESHOLD = 0.85


def _norm(s):
    return re.sub(r"[^a-z ]", "", (s or "").lower()).strip()


def name_similarity(a, b):
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def run_checks(farmer: dict) -> list:
    """Return a list of {field, detail, severity} problems. Empty list = clean."""
    problems = []

    # --- Aadhaar -----------------------------------------------------------
    aadhaar = (farmer.get("aadhaar_number") or "").replace(" ", "")
    if not aadhaar:
        problems.append({"field": "aadhaar", "severity": "blocking",
                         "detail": "Aadhaar number is missing."})
    elif not re.fullmatch(r"\d{12}", aadhaar):
        problems.append({"field": "aadhaar", "severity": "blocking",
                         "detail": "Aadhaar must be exactly 12 digits. Found %d character(s)." % len(aadhaar)})
    elif aadhaar[0] in "01":
        problems.append({"field": "aadhaar", "severity": "blocking",
                         "detail": "Aadhaar numbers cannot begin with 0 or 1."})
    elif not verhoeff_valid(aadhaar):
        problems.append({"field": "aadhaar", "severity": "blocking",
                         "detail": "Aadhaar failed the Verhoeff checksum - likely a typing error."})

    # --- Bank account ------------------------------------------------------
    acct = (farmer.get("bank_account") or "").strip()
    if not acct:
        problems.append({"field": "bank", "severity": "blocking",
                         "detail": "Bank account number is missing - payment cannot be credited."})
    elif not re.fullmatch(r"\d{9,18}", acct):
        problems.append({"field": "bank", "severity": "blocking",
                         "detail": "Bank account number must be 9-18 digits."})

    ifsc = (farmer.get("ifsc_code") or "").strip().upper()
    if not ifsc:
        problems.append({"field": "bank", "severity": "blocking",
                         "detail": "IFSC code is missing."})
    elif not IFSC_RE.match(ifsc):
        problems.append({"field": "bank", "severity": "blocking",
                         "detail": "IFSC '%s' is malformed. Expected 4 letters, then 0, then 6 characters." % ifsc})

    # --- Name on bank account vs registered name ---------------------------
    on_acct = farmer.get("bank_name_on_account")
    if on_acct:
        score = name_similarity(farmer.get("name"), on_acct)
        if score < NAME_MATCH_THRESHOLD:
            problems.append({
                "field": "name_match", "severity": "warning",
                "detail": "Registered name '%s' does not match bank account holder '%s' (%d%% match). "
                          "This is the most common cause of DBT payment failure."
                          % (farmer.get("name"), on_acct, round(score * 100)),
            })

    # --- Land record -------------------------------------------------------
    land = (farmer.get("land_record_id") or "").strip().upper()
    if not land:
        problems.append({"field": "land", "severity": "warning",
                         "detail": "Land record ID is missing - quantity limit cannot be verified."})
    elif not LAND_RE.match(land):
        problems.append({"field": "land", "severity": "warning",
                         "detail": "Land record ID '%s' does not match the state format (e.g. PNB-104238-12)." % land})

    return problems


def validate_and_flag(farmer_id: int) -> list:
    """Run checks for one farmer, clear their old unresolved flags, write new
    ones, and raise an in-app alert if anything was found."""
    row = query("SELECT * FROM farmers WHERE id = ?", (farmer_id,), one=True)
    if row is None:
        return []
    farmer = dict(row)
    problems = run_checks(farmer)

    execute("DELETE FROM data_validation_flags WHERE farmer_id = ? AND status = 'unresolved'", (farmer_id,))
    now = datetime.now().isoformat(timespec="seconds")
    for p in problems:
        execute(
            "INSERT INTO data_validation_flags (farmer_id, field_flagged, detail, severity, status, flagged_at)"
            " VALUES (?,?,?,?,'unresolved',?)",
            (farmer_id, p["field"], p["detail"], p["severity"], now),
        )

    if problems:
        from alerts import raise_alert
        blocking = sum(1 for p in problems if p["severity"] == "blocking")
        raise_alert(
            farmer_id, "data_mismatch", "app",
            "%d issue(s) found in your registration details (%d critical). Please visit your "
            "procurement centre or update your profile before your slot date, otherwise your "
            "payment may be delayed." % (len(problems), blocking),
        )
    return problems


def unresolved_flags(farmer_id: int):
    return query(
        "SELECT * FROM data_validation_flags WHERE farmer_id = ? AND status = 'unresolved'"
        " ORDER BY CASE severity WHEN 'blocking' THEN 0 ELSE 1 END, id",
        (farmer_id,),
    )
