"""Krishi Sahayak help chat. Gemini answers from the facts built in _facts()
(never aadhaar / bank / phone). Falls back to the FAQ list when gemini is down.
"""

from datetime import date

import core
import payments
import voice_ai
import weather
from db import query
from i18n import get_lang, t
from voicebook import normalise, spoken_day

LANGUAGE_NAMES = {"hi": "Hindi, in Devanagari script", "bn": "Bengali, in Bengali script",
                  "en": "simple English"}

# pages the chat can link to
PAGES = {"/farmer/voice": "Book by speaking", "/farmer/centres": "Book a Slot", "/register": "Register",
         "/login": "Farmer Sign In", "/farmer/dashboard": "Dashboard", "/farmer/payments": "Payments",
         "/farmer/profile": "My Details", "/#weather": "Weather"}

INSTRUCTIONS = """You are Krishi Sahayak, the help assistant on Krishi Sutra, a government website where farmers in Uttarakhand register, book a time to bring their grain to a procurement centre, and follow their payment.

Most people asking are farmers, and many do not read well. Answer in LANGUAGE. Use short, plain sentences, at most four. No markdown, no bold, no bullet symbols; if steps are needed, write them as 1. 2. 3. on separate lines.

Use only the facts below. If the answer is not in them - other government schemes, loans, farming advice, anything personal - say you don't know and suggest calling the Kisan Call Centre on 1800-180-1551 or asking at the procurement centre. Never ask for or repeat an Aadhaar number, bank account, OTP or password. Never promise a date for a payment.

link: the one website page that helps most with this answer, or "none".
suggestions: up to three short follow-up questions the farmer might ask next, written in LANGUAGE.

FACTS
"""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "reply": {"type": "STRING"},
        "link": {"type": "STRING", "enum": list(PAGES) + ["none"]},
        "suggestions": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["reply", "link", "suggestions"],
}


def _facts(farmer):
    lines = [
        "Registering: once, with mobile number, Aadhaar, bank account, IFSC and land record ID; about five minutes. "
        "Any Common Service Centre (CSC) can register a farmer who has no smartphone. Signing in uses the "
        "registered mobile number and a one-time password (OTP).",
        "Booking: choose a centre, the crop and quantity, then a day and a two-hour slot: 8-10, 10-12, 12-2 or 2-4, "
        "up to two weeks ahead. One slot per farmer per day, at most three active bookings. A booking can be "
        "cancelled or moved to another slot from its page. Farmers can also book by speaking (Book by speaking), "
        "and the slot page shows the weather at the centre for each day.",
        "At the centre: bring the Aadhaar card, bank passbook, land record and the token number or printed gate "
        "pass. Centres weigh from 8 in the morning to 4 in the afternoon. The crop is weighed and graded at the "
        "gate; grade B is paid slightly less and rejected produce is not bought.",
        "Payment: after weighing, the centre closes the transaction and the money goes straight to the bank "
        "account registered with Aadhaar (direct benefit transfer). A failed payment is almost always a detail "
        "that does not match - Aadhaar, account number, IFSC or the name on the account - fixed on My Details.",
        "Weather: the home page has the five-day forecast for every district, and each centre page has it hour "
        "by hour. If rain is expected while grain waits at home, the farmer gets a storage-risk alert.",
        "The website is in English, Hindi and Bengali (chosen at the top of every page), and text can be made bigger.",
        "Help line: Kisan Call Centre 1800-180-1551, free, national.",
        "Minimum support prices per quintal, RMS 2025-26: "
        + ", ".join("%s Rs %d" % (crop, price) for crop, price in core.MSP.items()) + ".",
    ]
    centres = query("SELECT name, location, district, crop_types_accepted, daily_capacity "
                    "FROM procurement_centres ORDER BY name")
    lines.append("Procurement centres: " + "; ".join(
        "%s at %s, %s district, buys %s, weighs %d quintals a day"
        % (c["name"], c["location"], c["district"], c["crop_types_accepted"].replace(",", ", "), c["daily_capacity"])
        for c in centres) + ".")

    lines.append("Today is %s. The weather below is a five-day forecast: for any later day say the forecast "
                 "does not reach that far yet, and never invent one." % date.today().isoformat())
    districts = sorted({c["district"] for c in centres} | ({farmer["district"]} if farmer else set()))
    for district in districts:
        village = farmer["village"] if farmer and farmer["district"] == district else None
        days, place = weather.outlook(district, 5, village)
        lines.append("Weather in %s district, read at %s: %s." % (district, place, "; ".join(days)))
    lines.append("Advice when rain is coming: keep the grain covered, on a raised platform, away from the floor. "
                 "Damp grain loses a grade at the centre and is paid less.")

    if not farmer:
        lines.append("The person asking is not signed in, so their bookings can't be seen; they should sign in to check them.")
        return "\n".join(lines)

    lines.append("The person asking is signed in as a farmer from %s, %s district."
                 % (farmer["village"], farmer["district"]))
    rows = query(
        "SELECT b.token_no, s.date, s.time_window, c.name AS centre, b.status, b.crop_type, b.estimated_quantity,"
        "       t.payment_status, t.total_amount"
        "  FROM bookings b JOIN slots s ON s.id = b.slot_id"
        "  JOIN procurement_centres c ON c.id = s.centre_id"
        "  LEFT JOIN transactions t ON t.booking_id = b.id"
        " WHERE b.farmer_id = ? ORDER BY s.date DESC LIMIT 8", (farmer["id"],))
    if rows:
        lines.append("Their bookings, newest first: " + "; ".join(
            "token %s at %s on %s %s, %s %g quintals, booking %s%s" % (
                r["token_no"], r["centre"], r["date"], r["time_window"], r["crop_type"], r["estimated_quantity"],
                r["status"], ", payment %s of Rs %d" % (r["payment_status"], r["total_amount"] or 0)
                if r["payment_status"] else "")
            for r in rows) + ".")
    else:
        lines.append("They have no bookings yet.")
    today = date.today().isoformat()
    for r in [x for x in rows if x["status"] in ("booked", "arrived") and x["date"] >= today][:3]:
        risk = weather.assess_risk(farmer["district"], r["date"], farmer["village"])
        card = weather.day_card(farmer["district"], r["date"], farmer["village"])
        on_day = ("%s, rain %.1f mm, humidity %d%%" % (card["description"], card["rain_mm"], card["humidity"])
                  if card else "beyond the five-day forecast")
        lines.append("Their booking on %s (token %s): weather at home that day %s. Storage risk while the grain "
                     "waits: %s. %s" % (r["date"], r["token_no"], on_day, risk["level"], risk["reason"]))

    money = payments.farmer_lines(farmer["id"])
    if money:
        lines.append("Their payments, newest first (a bank reference is a UTR; a returned payment goes again once "
                     "the detail is fixed and the centre re-sends it): " + "; ".join(money) + ".")
    flags = query("SELECT field_flagged, severity FROM data_validation_flags "
                  "WHERE farmer_id = ? AND status = 'unresolved'", (farmer["id"],))
    lines.append("Problems in their registered details that can hold up a payment: "
                 + (", ".join("%s (%s)" % (f["field_flagged"], f["severity"]) for f in flags) if flags else "none")
                 + ".")
    return "\n".join(lines)


# offline fallback: (keywords, answer key, link)
FAQ = (
    (("otp", "sign in", "login", "log in", "लॉगिन", "লগইন"), "signin", "/login"),
    (("regist", "panjik", "पंजीकरण", "रजिस्टर", "নিবন্ধন"), "register", "/register"),
    (("cancel", "radd", "रद्द", "badal", "बदल", "reschedule", "বাতিল"), "change", "/farmer/dashboard"),
    (("kagaz", "kaagaz", "document", "kya lana", "दस्तावेज", "कागज", "क्या लाना", "কাগজ", "কী আনতে"), "documents", None),
    (("payment", "paisa", "paise", "bhugtan", "भुगतान", "पैसा", "पैसे", "টাকা", "পেমেন্ট"), "payment", "/farmer/payments"),
    (("msp", "bhav", "भाव", "कीमत", "daam", "दाम", "price", "rate", "দাম", "মূল্য"), "price", None),
    (("weather", "mausam", "मौसम", "barish", "बारिश", "rain", "আবহাওয়া", "বৃষ্টি"), "weather", "/#weather"),
    (("kab khul", "timing", "kitne baje", "कब खुल", "कितने बजे", "কখন খোলে"), "timings", None),
    (("book", "slot", "स्लॉट", "बुक", "বুক", "স্লট"), "book", "/farmer/voice"),
)
ANSWERS = {
    "signin": "Tap Farmer Sign In and enter your registered mobile number. You will get a one-time password (OTP). Never share the OTP with anyone.",
    "register": "To register, tap Register and enter your mobile number, Aadhaar, bank account and land record. It takes about five minutes. Any CSC centre can also register you.",
    "change": "Open your booking from the Dashboard, then tap Cancel booking or Reschedule this slot.",
    "documents": "Bring your Aadhaar card, bank passbook and land record, and your token number or gate pass.",
    "payment": "Your payment goes to your bank account after your crop is weighed and the transaction is closed. You can follow it on the Payments page.",
    "weather": "The home page shows the weather for every district for the next five days.",
    "timings": "Centres weigh from 8 in the morning to 4 in the afternoon. Please arrive at the start of your slot.",
    "book": "Tap Book a Slot, choose a centre, your crop and quantity, then a day and time. You can also book by speaking.",
}


def suggestions():
    return [t("How do I book a slot?"), t("What should I bring?"), t("When will I get paid?")]


def _package(text, link, follow_ups, source):
    link = link if link in PAGES else None
    follow_ups = [str(s).strip()[:80] for s in (follow_ups or []) if str(s).strip()][:3]
    return {"reply": text, "link": {"href": link, "label": t(PAGES[link])} if link else None,
            "suggestions": follow_ups, "source": source}


def _weather_text(farmer):
    district = farmer["district"] if farmer else "Udham Singh Nagar"
    village = farmer["village"] if farmer else None
    forecast, source, point = weather.get_forecast(district, 3, village)
    place = point["place"] if point else district
    parts = ["%s: %s, %s mm" % (spoken_day(d["date"]), t(d["description"]), "%g" % d["rain_mm"])
             for d in forecast]
    text = t("Weather at %s for the next three days:") % t(place) + " " + "; ".join(parts) + "."
    if any(d["rain_mm"] >= 0.5 for d in forecast):
        text += " " + t("Keep the grain covered and off the ground.")
    return text


def _offline(question, farmer=None):
    s = normalise(question)
    for phrases, key, link in FAQ:
        if any(normalise(p) in s for p in phrases):
            if key == "weather":
                return _package(_weather_text(farmer), link, suggestions(), "offline")
            if key == "price":
                text = t("Support prices per quintal:") + " " + ", ".join(
                    "%s ₹%s" % (t(crop), "{:,}".format(int(price))) for crop, price in core.MSP.items())
            else:
                text = t(ANSWERS[key])
            return _package(text, link, suggestions(), "offline")
    return _package(t("I could not answer that right now. Please call Kisan Call Centre on 1800-180-1551, "
                      "or ask at your procurement centre."), None, suggestions(), "offline")


def reply(messages, farmer=None):
    contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["text"]}]}
                for m in messages]
    instructions = (INSTRUCTIONS.replace("LANGUAGE", LANGUAGE_NAMES.get(get_lang(), LANGUAGE_NAMES["hi"]))
                    + _facts(farmer))
    try:
        answer = voice_ai.generate(instructions, contents, SCHEMA, label="help chat")
    except voice_ai.Unavailable:
        return _offline(messages[-1]["text"], farmer)
    text = str(answer.get("reply") or "").strip()
    if not text:
        return _offline(messages[-1]["text"], farmer)
    return _package(text[:1200], answer.get("link"), answer.get("suggestions"), "ai")
