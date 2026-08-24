"""Novelty Feature B - Storage-Risk Alerts.

Problem: a farmer who books a slot 8 days out has to store harvested grain at
home in the meantime. If it rains, the grain gets wet, moisture content rises,
and the centre downgrades or rejects it at the gate. Nobody warns them.

This module looks at the forecast for the farmer's district over the waiting
window and raises a spoilage-risk alert with a suggestion to move earlier.

Data source: OpenWeatherMap 5-day forecast (free tier). If OWM_API_KEY is not
set, or the API call fails, we fall back to a deterministic mock forecast so
the demo never depends on the venue wifi. See DEMO_FORCE_RISK below for the
manual override the spec asks for.
"""

import os
from datetime import date, datetime, timedelta

from db import execute, query

OWM_API_KEY = os.environ.get("OWM_API_KEY", "").strip()
OWM_URL = "https://api.openweathermap.org/data/2.5/forecast"

# Slots further out than this trigger a storage-risk evaluation.
LEAD_DAYS_THRESHOLD = int(os.environ.get("STORAGE_RISK_LEAD_DAYS", "5"))

# Rule thresholds
RAIN_MM_HIGH = 5.0        # total forecast rain (mm) over the window
HUMIDITY_HIGH = 80        # average relative humidity %

# Demo control panel toggle - when True every risk check returns HIGH.
# Flipped from /admin/demo so a live demo can force the alert on stage.
DEMO_FORCE_RISK = {"on": False}

# Districts the mock forecast treats as being in a wet spell, and the full set
# of districts the mock knows about. Only used when no live API key is set.
MOCK_KNOWN_DISTRICTS = {"Karnal", "Kurukshetra", "Sirsa", "Ludhiana", "Patiala",
                        "Sangrur", "Hoshangabad", "Vidisha"}
MOCK_WET_DISTRICTS = {"Karnal", "Sangrur", "Hoshangabad"}


def _mock_forecast(district: str, days: int):
    """Deterministic pseudo-forecast so the same district always behaves the
    same way in a demo. Districts whose name hashes 'wet' get rain."""
    seed = sum(ord(c) for c in (district or "X"))
    # Only some districts sit in a wet spell at any one time, which is what keeps
    # the risk watchlist meaningful rather than flagging every booking. Karnal is
    # in the list on purpose: the walkthrough farmer is registered there, so the
    # storage-risk alert can be demonstrated without the manual override.
    # Districts outside the list fall back to a hash so new ones still vary.
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


def _live_forecast(district: str, days: int):
    """Query OpenWeatherMap. Returns None on any failure so callers fall back."""
    if not OWM_API_KEY:
        return None
    try:
        import requests
        r = requests.get(OWM_URL, params={
            "q": "%s,IN" % district, "appid": OWM_API_KEY, "units": "metric",
        }, timeout=6)
        if r.status_code != 200:
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
    except Exception:
        return None


def get_forecast(district: str, days: int = 5):
    """Returns (forecast_list, source) where source is 'live' or 'mock'."""
    live = _live_forecast(district, days)
    if live:
        return live, "live"
    return _mock_forecast(district, days), "mock"


def assess_risk(district: str, slot_date_str: str):
    """Evaluate spoilage risk for grain stored until `slot_date_str`.

    Returns dict: level (none|low|high), lead_days, reason, forecast, source.
    """
    try:
        slot_date = datetime.strptime(slot_date_str, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return {"level": "none", "lead_days": 0, "reason": "Invalid slot date.",
                "forecast": [], "source": "mock"}

    lead_days = (slot_date - date.today()).days
    window = max(1, min(lead_days, 5))       # OWM free tier gives 5 days
    forecast, source = get_forecast(district, window)

    if DEMO_FORCE_RISK["on"]:
        return {
            "level": "high", "lead_days": lead_days, "source": source, "forecast": forecast,
            "reason": "Demo override active: heavy rain and high humidity forecast for %s "
                      "during the %d-day wait before your slot." % (district, lead_days),
        }

    if lead_days < LEAD_DAYS_THRESHOLD:
        return {
            "level": "none", "lead_days": lead_days, "source": source, "forecast": forecast,
            "reason": "Slot is only %d day(s) away - storage exposure is minimal." % lead_days,
        }

    total_rain = sum(d["rain_mm"] for d in forecast)
    avg_hum = sum(d["humidity"] for d in forecast) / len(forecast)
    rainy_days = sum(1 for d in forecast if d["rain_mm"] > 0.5)

    if total_rain >= RAIN_MM_HIGH or avg_hum >= HUMIDITY_HIGH:
        level = "high"
        reason = ("%.1f mm rain expected across %d of the next %d days and average humidity "
                  "of %d%% in %s. Grain stored for %d days is at high risk of moisture damage "
                  "and quality downgrade at the gate."
                  % (total_rain, rainy_days, len(forecast), avg_hum, district, lead_days))
    elif rainy_days >= 1 or avg_hum >= 65:
        level = "low"
        reason = ("Light rain possible on %d of the next %d days in %s (avg humidity %d%%). "
                  "Keep produce covered and on raised platforms."
                  % (rainy_days, len(forecast), district, avg_hum))
    else:
        level = "none"
        reason = ("Dry weather forecast for %s (avg humidity %d%%). No storage risk identified."
                  % (district, avg_hum))

    return {"level": level, "lead_days": lead_days, "reason": reason,
            "forecast": forecast, "source": source}


def evaluate_booking(booking_id: int):
    """Assess one booking, persist the risk level, and alert the farmer if high."""
    row = query(
        "SELECT b.id, b.farmer_id, b.storage_risk, s.date AS slot_date, f.district, f.name,"
        "       c.name AS centre_name"
        "  FROM bookings b"
        "  JOIN slots s ON s.id = b.slot_id"
        "  JOIN farmers f ON f.id = b.farmer_id"
        "  JOIN procurement_centres c ON c.id = s.centre_id"
        " WHERE b.id = ?", (booking_id,), one=True)
    if row is None:
        return None

    result = assess_risk(row["district"], row["slot_date"])
    execute("UPDATE bookings SET storage_risk = ? WHERE id = ?", (result["level"], booking_id))

    if result["level"] == "high" and row["storage_risk"] != "high":
        from alerts import raise_alert
        msg = ("STORAGE RISK: Your slot at %s is %d days away and %s. "
               "Consider requesting an earlier slot, or store your produce on a raised, "
               "covered platform." % (row["centre_name"], result["lead_days"], result["reason"]))
        raise_alert(row["farmer_id"], "storage_risk", "app", msg, booking_id=booking_id)
        # Queued for the IVR module to pick up and place a voice call.
        raise_alert(row["farmer_id"], "storage_risk", "ivr",
                    "Voice call queued: storage risk warning for booking #%d." % booking_id,
                    booking_id=booking_id)
    return result


def rescan_all_upcoming():
    """Re-evaluate every future booking. Used by the demo control panel."""
    rows = query(
        "SELECT b.id FROM bookings b JOIN slots s ON s.id = b.slot_id"
        " WHERE b.status = 'booked' AND s.date >= ?", (date.today().isoformat(),))
    return [evaluate_booking(r["id"]) for r in rows]
