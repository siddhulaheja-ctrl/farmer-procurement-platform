"""Storage risk alerts.

If a farmer's slot is a week away they have to keep the grain at home till
then. If it rains it gets damp and the centre downgrades it at the gate.
So we check the forecast for their district and warn them.

Uses OpenWeatherMap if OWM_API_KEY is set, otherwise a fake forecast so the
demo still works without internet.
"""

import math
import os
from datetime import date, datetime, timedelta, timezone

from db import execute, query

import env

env.load()

OWM_API_KEY = os.environ.get("OWM_API_KEY", "").strip()
OWM_URL = "https://api.openweathermap.org/data/2.5/forecast"
OWM_GEO_URL = "https://api.openweathermap.org/geo/1.0/direct"

# only slots at least this far away get a storage risk check
LEAD_DAYS_THRESHOLD = int(os.environ.get("STORAGE_RISK_LEAD_DAYS", "5"))

RAIN_MM_HIGH = 5.0        # mm over the window
HUMIDITY_HIGH = 80        # avg %

# STORAGE_RISK_FORCE=1 -> always high, for demoing on a dry day
DEMO_FORCE_RISK = {"on": os.environ.get("STORAGE_RISK_FORCE", "").strip() in ("1", "true", "yes")}

# OWM doesn't know districts or most villages by name. so: geocode the village,
# else these district HQ coords, else mock
# TODO: IMD Gramin Krishi Mausam Sewa has block level data
DISTRICT_POINTS = {
    "Udham Singh Nagar": (28.975, 79.396, "Rudrapur"),
    "Haridwar":          (29.967, 78.167, "Haridwar"),
    "Dehradun":          (30.326, 78.044, "Dehradun"),
    "Nainital":          (29.217, 79.517, "Haldwani"),
}

_geo_cache = {}


def resolve_point(district, village=None):
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


def distance_km(a, b):
    # haversine
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _geocode(q):
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


# mock only. one wet district so the storage alert shows up offline
MOCK_KNOWN_DISTRICTS = {"Udham Singh Nagar", "Haridwar", "Dehradun", "Nainital"}
MOCK_WET_DISTRICTS = {"Udham Singh Nagar"}


def _mock_forecast(district: str, days: int):
    # deterministic per district
    seed = sum(ord(c) for c in (district or "X"))
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


_owm_cache = {}


def _owm_entries(point):
    # 3-hourly readings in local time, None on any failure
    if not OWM_API_KEY or not point:
        return None
    import time
    key = (point["lat"], point["lon"])
    hit = _owm_cache.get(key)
    if hit and time.time() - hit[0] < FORECAST_TTL:
        return hit[1]
    try:
        import requests
        r = requests.get(OWM_URL, params={
            "lat": point["lat"], "lon": point["lon"],
            "appid": OWM_API_KEY, "units": "metric",
        }, timeout=6)
        if r.status_code != 200:
            print("[weather] %s -> HTTP %s from openweathermap, using mock. %s"
                  % (point["place"], r.status_code, r.text[:120]))
            return None
        body = r.json()
        # dt is utc, shift to local or late evening lands on the next day
        offset = body.get("city", {}).get("timezone", 19800)
        entries = []
        for e in body.get("list", []):
            entries.append({
                "at": datetime.fromtimestamp(e["dt"] + offset, timezone.utc).replace(tzinfo=None),
                "temp": round(e["main"]["temp"]),
                "humidity": e["main"]["humidity"],
                "rain_mm": e.get("rain", {}).get("3h", 0.0),
                # not "pop": jinja finds dict.pop before the key
                "rain_chance": round(e.get("pop", 0) * 100),
                "wind_kmh": round(e.get("wind", {}).get("speed", 0) * 3.6),
                "description": e["weather"][0]["description"],
            })
        _owm_cache[key] = (time.time(), entries or None)
        return entries or None
    except Exception as e:
        print("[weather] %s -> %s, using mock" % (point["place"], e))
        return None


def _live_forecast(point, days):
    entries = _owm_entries(point)
    if not entries:
        return None
    buckets = {}
    for e in entries:
        b = buckets.setdefault(e["at"].date().isoformat(), {"rain_mm": 0.0, "hum": [], "desc": ""})
        b["rain_mm"] += e["rain_mm"]
        b["hum"].append(e["humidity"])
        b["desc"] = e["description"]
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


FORECAST_TTL = 30 * 60
_forecast_cache = {}


def get_forecast(district, days=5, village=None):
    # -> (days, 'live' or 'mock', point)
    import time
    key = (district, days, village)
    hit = _forecast_cache.get(key)
    if hit and time.time() - hit[0] < FORECAST_TTL:
        return hit[1]
    point = resolve_point(district, village)
    live = _live_forecast(point, days)
    result = (live, "live", point) if live else (_mock_forecast(district, days), "mock", point)
    _forecast_cache[key] = (time.time(), result)
    return result


def _mock_hours(district, day_iso):
    day = next((d for d in _mock_forecast(district, 5) if d["date"] == day_iso), None)
    if not day:
        return None
    seed = sum(ord(c) for c in (district or "X"))
    start = datetime.strptime(day_iso, "%Y-%m-%d")
    wet = day["rain_mm"] > 0
    weights = [0, 0, 0, 1, 2, 3, 2, 1] if wet else [0] * 8
    out = []
    for i in range(8):
        hour = i * 3
        rain = round(day["rain_mm"] * weights[i] / sum(weights), 1) if wet else 0.0
        out.append({
            "at": start + timedelta(hours=hour),
            "temp": 22 + seed % 6 + round(8 * math.sin((hour - 9) * math.pi / 12)),
            "humidity": max(20, min(100, day["humidity"] + (10 if hour < 9 else -8 if 12 <= hour <= 15 else 0))),
            "rain_mm": rain,
            "rain_chance": 40 + weights[i] * 20 if wet else (seed + i) % 10,
            "wind_kmh": 4 + (seed + i * 3) % 12,
            "description": ("moderate rain" if rain >= 2.5 else "light rain") if rain else
                           ("scattered clouds" if wet else "clear sky"),
        })
    return out


def get_hours(district, day_iso, village=None):
    point = resolve_point(district, village)
    entries = _owm_entries(point)
    if entries:
        return [e for e in entries if e["at"].date().isoformat() == day_iso], "live", point
    return _mock_hours(district, day_iso) or [], "mock", point


def assess_risk(district, slot_date_str, village=None):
    try:
        slot_date = datetime.strptime(slot_date_str, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return {"level": "none", "lead_days": 0, "reason": "Invalid slot date.",
                "forecast": [], "source": "mock", "place": district, "nearby": False}

    lead_days = (slot_date - date.today()).days
    window = max(1, min(lead_days, 5))       # free tier is 5 days
    forecast, source, point = get_forecast(district, window, village)

    place = point["place"] if point else district
    # say so when it's the district town's forecast, not their village's
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


def day_card(district, day_iso, village=None):
    forecast, source, point = get_forecast(district, 6, village)
    card = next((d for d in forecast if d["date"] == str(day_iso)[:10]), None)
    if not card:
        return None
    return dict(card, source=source, place=point["place"] if point else district)


def outlook(district, days=5, village=None):
    # for the help chat
    forecast, source, point = get_forecast(district, days, village)
    lines = ["%s: %s, rain %.1f mm, humidity %d%%"
             % (d["date"], d["description"], d["rain_mm"], d["humidity"]) for d in forecast]
    return lines, (point["place"] if point else district)


def evaluate_booking(booking_id: int):
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
        from alerts import hi
        raise_alert(row["farmer_id"], "storage_risk", "app", msg, booking_id=booking_id,
                    message_hi="भंडारण जोखिम: %s पर आपका स्लॉट %d दिन दूर है और बारिश का "
                               "अनुमान है। उपज ढककर ऊंची जगह रखें।"
                               % (hi(row["centre_name"]), result["lead_days"]))
        raise_alert(row["farmer_id"], "storage_risk", "ivr",
                    "नमस्ते %s जी। कृषि सूत्र से सूचना। %s पर आपका स्लॉट %d दिन दूर है और "
                    "आपके क्षेत्र में बारिश का अनुमान है। अपनी उपज को ढककर ऊंची जगह रखें, "
                    "या अपने केंद्र से पहले का स्लॉट मांगें। धन्यवाद।"
                    % (row["name"], row["centre_name"], result["lead_days"]),
                    booking_id=booking_id)
    return result

