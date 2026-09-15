"""A stand-in for the AgriStack farmer registry.

States have been giving farmers a Farmer ID (Kisan Pehchaan Patra) under
AgriStack. It is tied to the farmer's Aadhaar, and the registry holds their
bank account and every land parcel they own, so a farmer who has one
shouldn't have to type any of that again.

This is mock data: four made-up farmers. In the live system the lookup goes to
the state registry and needs the farmer's consent - an OTP to the mobile linked
to that Farmer ID - before anything is shared.
TODO: AgriStack farmer registry API, with consent
"""

from validation import verhoeff_checksum_digit

FARMER_ID_LENGTH = 11


def _aadhaar(first_eleven):
    """A made-up Aadhaar that still passes the checksum, like a real one would."""
    return first_eleven + verhoeff_checksum_digit(first_eleven)


DEMO = {
    "10025000101": {
        "name": "Harish Chandra Joshi", "village": "Bhimtal", "district": "Nainital",
        "aadhaar": _aadhaar("73519026481"), "bank_account": "31456789012345", "ifsc": "SBIN0001234",
        "name_on_account": "Harish Chandra Joshi", "aadhaar_seeded": 1,
        "lands": [
            {"land_record_id": "NTL-204511-03", "village": "Bhimtal", "district": "Nainital", "area_acres": 1.8},
            {"land_record_id": "NTL-204587-11", "village": "Mehragaon", "district": "Nainital", "area_acres": 0.9},
        ],
    },
    "10025000102": {
        "name": "Suman Devi", "village": "Jwalapur", "district": "Haridwar",
        "aadhaar": _aadhaar("62840917352"), "bank_account": "52017734908812", "ifsc": "PUNB0456700",
        "name_on_account": "Suman Devi", "aadhaar_seeded": 1,
        "lands": [
            {"land_record_id": "HRD-118204-07", "village": "Jwalapur", "district": "Haridwar", "area_acres": 2.5},
        ],
    },
    "10025000103": {
        "name": "Gurpreet Singh", "village": "Gadarpur", "district": "Udham Singh Nagar",
        "aadhaar": _aadhaar("58392046175"), "bank_account": "60913247760031", "ifsc": "CNRB0003310",
        "name_on_account": "Gurpreet Singh", "aadhaar_seeded": 1,
        "lands": [
            {"land_record_id": "USN-330912-04", "village": "Gadarpur", "district": "Udham Singh Nagar", "area_acres": 4.0},
            {"land_record_id": "USN-330955-18", "village": "Gadarpur", "district": "Udham Singh Nagar", "area_acres": 2.2},
            {"land_record_id": "USN-341007-02", "village": "Dineshpur", "district": "Udham Singh Nagar", "area_acres": 1.5},
        ],
    },
    # the account is in a longer form of her name: registers fine, gets the name-match warning
    "10025000104": {
        "name": "Meena Rawat", "village": "Vikasnagar", "district": "Dehradun",
        "aadhaar": _aadhaar("49215830674"), "bank_account": "20385519624470", "ifsc": "BARB0VIKASN",
        "name_on_account": "Meena Singh Rawat", "aadhaar_seeded": 1,
        "lands": [
            {"land_record_id": "DDN-509321-06", "village": "Vikasnagar", "district": "Dehradun", "area_acres": 1.1},
        ],
    },
}


def clean(value):
    """Just the digits - people type the ID with spaces."""
    return "".join(c for c in str(value or "") if c.isdigit())


def lookup(farmer_id):
    """The registry record for a Farmer ID, or None."""
    code = clean(farmer_id)
    record = DEMO.get(code)
    if record is None:
        return None
    out = dict(record)
    out["farmer_id"] = code
    out["lands"] = [dict(land) for land in record["lands"]]
    return out


def mask(value, keep=4):
    digits = clean(value)
    return "•" * max(0, len(digits) - keep) + digits[-keep:] if digits else ""


def public(record):
    """What the registration page may show before anyone has registered: no
    full Aadhaar or account number. The server takes those from the registry
    itself when the form arrives."""
    return {
        "farmer_id": record["farmer_id"], "name": record["name"], "village": record["village"],
        "district": record["district"], "ifsc": record["ifsc"], "name_on_account": record["name_on_account"],
        "aadhaar_masked": mask(record["aadhaar"]), "account_masked": mask(record["bank_account"]),
        "lands": record["lands"],
    }
