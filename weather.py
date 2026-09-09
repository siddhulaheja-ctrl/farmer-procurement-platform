"""Storage risk alerts.

If a farmer's slot is a week away they have to keep the grain at home till
then. If it rains it gets damp and the centre downgrades it at the gate.
So we check the forecast for their district and warn them.

Uses OpenWeatherMap if OWM_API_KEY is set, otherwise a fake forecast so the
demo still works without internet.
"""

import os
from datetime import date, datetime, timedelta

from db import execute, query

import env

env.load()

OWM_API_KEY = os.environ.get("OWM_API_KEY", "").strip()
OWM_URL = "https://api.openweathermap.org/data/2.5/forecast"
OWM_GEO_URL = "https://api.openweathermap.org/geo/1.0/direct"

# Slots further out than this trigger a storage-risk evaluation.
LEAD_DAYS_THRESHOLD = int(os.environ.get("STORAGE_RISK_LEAD_DAYS", "5"))

# Rule thresholds
RAIN_MM_HIGH = 5.0        # total forecast rain (mm) over the window
HUMIDITY_HIGH = 80        # average relative humidity %

# STORAGE_RISK_FORCE=1 makes everything come back HIGH, for when the weather
# is dry and we still need to show the alert
DEMO_FORCE_RISK = {"on": os.environ.get("STORAGE_RISK_FORCE", "").strip() in ("1", "true", "yes")}

# Where to ask for the forecast.
# OWM only knows towns. Districts come back "city not found" and so do most
# villages, so asking for the farmer's address never worked - it just fell
# through to the mock and we didn't notice for weeks.
# Now: geocode the village, else use the district HQ coords below, else mock.
# The HQ coords are hardcoded so step 2 can't fail. A reading from 30km away
# is still useful for rain, and we show which town it came from.
# TODO: IMD's Gramin Krishi Mausam Sewa does this at block level. Needs a govt
# data agreement.
DISTRICT_POINTS = {
    "Udham Singh Nagar": (28.975, 79.396, "Rudrapur"),
    "Haridwar":          (29.967, 78.167, "Haridwar"),
    "Dehradun":          (30.326, 78.044, "Dehradun"),
    "Nainital":          (29.217, 79.517, "Haldwani"),
}

_geo_cache = {}


def resolve_point(district, village=None):
    """Returns lat/lon, the place name we used, and how precise it is."""
    if village:
        key = "%s|%s" % (village, district)
        if key not in _geo_cache:
            _geo_cache[key] = _geocode("%s,Uttarakhand,IN" % village)
        hit = _geo_cache[key]
        if hit:
            return {"lat": hit[0], "lon": hit[1], "place": village, "precision": "village"}

    point = DISTRICT_POINTS.get(district)
    if point:
        return {"lat": point[0], "lon": point[1], "place": point[2], "precision": "district"}
    return None


def _geocode(q):
    """village -> (lat, lon), or None. Usually None."""
    if not OWM_API_KEY:
        return None
    try:
        import requests
        r = requests.get(OWM_GEO_URL, params={"q": q, "limit": 1, "appid": OWM_API_KEY},
                         timeout=6)
        hits = r.json() if r.status_code == 200 else []
        return (hits[0]["lat"], hits[0]["lon"]) if hits else None
    except Exception:
        return None


def _mock_forecast(district: str, days: int):
    """Fake forecast. Same district always gives the same answer so demos
    are repeatable."""
    seed = sum(ord(c) for c in (district or "X"))
    # only some are wet, otherwise everything gets flagged and the watchlist
    # is useless
    wet_district = (district in MOCK_WET_DISTRICTS) if district in MOCK_KNOWN_DISTRICTS \
        else (seed % 3 == 0)
    out = []
    for i in range(days):
        wet = wet_district and (seed + i * 7) % 10 >= 4
        out.append({
            "date": (date.today() + timedelta(days=i)).isoformat(),
            "rain_mm": round(((seed + i * 13) % 40) / 4.0, 1) if wet else 0.0,
            "humidity": 74 + ((seed + i * 5) % 20) if wet else 42 + ((seed + i * 3) % 22),
            "description": "moderate rain" if wet else "clear sky",
        })
    return out


def _live_forecast(point, days):
    """Query OpenWeatherMap by coordinate. Returns None on any failure so
    callers fall back to the mock."""
    if not OWM_API_KEY or not point:
        return None
    try:
        import requests
        r = requests.get(OWM_URL, params={
            "lat": point["lat"], "lon": point["lon"],
            "appid": OWM_API_KEY, "units": "metric",
        }, timeout=6)
        if r.status_code != 200:
            # used to fall back silently, so you couldn't tell if live data
            # was working
            print("[weather] %s -> HTTP %s from openweathermap, using mock. %s"
                  % (point["place"], r.status_code, r.text[:120]))
            return None
        buckets = {}
        for entry in r.json().get("list", []):
            d = entry["dt_txt"][:10]
            b = buckets.setdefault(d, {"rain_mm": 0.0, "hum": [], "desc": ""})
            b["rain_mm"] += entry.get("rain", {}).get("3h", 0.0)
            b["hum"].append(entry["main"]["humidity"])
            b["desc"] = entry["weather"][0]["description"]
        out = []
        for d in sorted(buckets)[:days]:
            b = buckets[d]
            out.append({
                "date": d,
                "rain_mm": round(b["rain_mm"], 1),
                "humidity": round(sum(b["hum"]) / len(b["hum"])),
                "description": b["desc"],
            })
        return out or None
    except Exception as e:
        print("[weather] %s -> %s, using mock" % (point["place"], e))
        return None


def get_forecast(district, days=5, village=None):
    """Returns (forecast, source, place). source is 'live' or 'mock'."""
    point = resolve_point(district, village)
    live = _live_forecast(point, days)
    if live:
        return live, "live", point
    return _mock_forecast(district, days), "mock", point


def assess_risk(district, slot_date_str, village=None):
    """Risk of the grain spoiling while it waits for `slot_date_str`.

    Returns level (none|low|high), lead_days, reason, forecast, source, place,
    and nearby=True if we fell back from the village to the district town.
    """
    try:
        slot_date = datetime.strptime(slot_date_str, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return {"level": "none", "lead_days": 0, "reason": "Invalid slot date.",
                "forecast": [], "source": "mock", "place": district, "nearby": False}

    lead_days = (slot_date - date.today()).days
    window = max(1, min(lead_days, 5))       # OWM free tier gives 5 days
    forecast, source, point = get_forecast(district, window, village)

    place = point["place"] if point else district
    # say when the reading is from the district town, not their village -
    # otherwise "no rain expected" sounds like a promise about their field
    nearby = bool(point and village and point["precision"] == "district")
    where = "%s (nearest station to %s)" % (place, village) if nearby else place
    meta = {"source": source, "place": place, "nearby": nearby}

    if DEMO_FORCE_RISK["on"]:
        return dict(meta, level="high", lead_days=lead_days, forecast=forecast,
                    reason="Demo override active: heavy rain and high humidity forecast for %s "
                           "during the %d-day wait before your slot." % (where, lead_days))

    if lead_days < LEAD_DAYS_THRESHOLD:
        return dict(meta, level="none", lead_days=lead_days, forecast=forecast,
                    reason="Slot is only %d day(s) away - storage exposure is minimal." % lead_days)

    total_rain = sum(d["rain_mm"] for d in forecast)
    avg_hum = sum(d["humidity"] for d in forecast) / len(forecast)
    rainy_days = sum(1 for d in forecast if d["rain_mm"] > 0.5)

    if total_rain >= RAIN_MM_HIGH or avg_hum >= HUMIDITY_HIGH:
        level = "high"
        reason = ("%.1f mm rain expected across %d of the next %d days and average humidity "
                  "of %d%% at %s. Grain stored for %d days is at high risk of moisture damage "
                  "and quality downgrade at the gate."
                  % (total_rain, rainy_days, len(forecast), avg_hum, where, lead_days))
    elif rainy_days >= 1 or avg_hum >= 65:
        level = "low"
        reason = ("Light rain possible on %d of the next %d days at %s (avg humidity %d%%). "
                  "Keep produce covered and on raised platforms."
                  % (rainy_days, len(forecast), where, avg_hum))
    else:
        level = "none"
        reason = ("Dry weather forecast for %s (avg humidity %d%%). No storage risk identified."
                  % (where, avg_hum))

    return dict(meta, level=level, lead_days=lead_days, reason=reason, forecast=forecast)


def evaluate_booking(booking_id: int):
    """Assess one booking, persist the risk level, and alert the farmer if high."""
    row = query(
        "SELECT b.id, b.farmer_id, b.storage_risk, s.date AS slot_date, f.district,"
        "       f.village, f.name,"
        "       c.name AS centre_name"
        "  FROM bookings b"
        "  JOIN slots s ON s.id = b.slot_id"
        "  JOIN farmers f ON f.id = b.farmer_id"
        "  JOIN procurement_centres c ON c.id = s.centre_id"
        " WHERE b.id = ?", (booking_id,), one=True)
    if row is None:
        return None

    result = assess_risk(row["district"], row["slot_date"], row["village"])
    execute("UPDATE bookings SET storage_risk = ? WHERE id = ?", (result["level"], booking_id))

    if result["level"] == "high" and row["storage_risk"] != "high":
        from alerts import raise_alert
        msg = ("STORAGE RISK: Your slot at %s is %d days away and %s. "
               "Consider requesting an earlier slot, or store your produce on a raised, "
               "covered platform." % (row["centre_name"], result["lead_days"], result["reason"]))
        raise_alert(row["farmer_id"], "storage_risk", "app", msg, booking_id=booking_id)
        # this gets read out on the call, so write it to the farmer, not
        # as a note to ourselves
        raise_alert(row["farmer_id"], "storage_risk", "ivr",
                    "नमस्ते %s जी। कृषि सूत्र से सूचना। %s पर आपका स्लॉट %d दिन दूर है और "
                    "आपके क्षेत्र में बारिश का अनुमान है। अपनी उपज को ढककर ऊंची जगह रखें, "
                    "या अपने केंद्र से पहले का स्लॉट मांगें। धन्यवाद।"
                    % (row["name"], row["centre_name"], result["lead_days"]),
                    booking_id=booking_id)
    return result


def rescan_all_upcoming():
    """Re-evaluate every future booking. Used by the demo control panel."""
    rows = query(
        "SELECT b.id FROM bookings b JOIN slots s ON s.id = b.slot_id"
        " WHERE b.status = 'booked' AND s.date >= ?", (date.today().isoformat(),))
    return [evaluate_booking(r["id"]) for r in rows]
