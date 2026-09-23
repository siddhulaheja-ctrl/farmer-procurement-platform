"""Gemini calls for the voice booking and the help chat.

It only fills in the same fields voicebook.parse() does, and _checked() throws
away anything that isn't a real centre / crop / date. Raises Unavailable on
any failure so the caller falls back to the parser.
"""

import json
import os
import threading
import time
from datetime import date, timedelta

import requests

import env

env.load()

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
# tried in order
MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_MODEL", "gemini-flash-lite-latest,gemini-3.5-flash-lite").split(",") if m.strip()]
URL = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
TIMEOUT = (3, 6)            # connect, read
STAY_AWAY = 45              # skip gemini this long after a network error

CENTRES = ["Rudrapur Mandi Samiti", "Kichha Kharid Kendra", "Haridwar Kharid Kendra",
           "Vikasnagar Grain Market", "Haldwani Mandi Centre"]
DISTRICTS = ["Udham Singh Nagar", "Haridwar", "Dehradun", "Nainital"]
CROPS = ["Wheat", "Paddy", "Mustard", "Gram", "Maize", "Bajra"]
WINDOWS = (8, 10, 12, 14)
QUESTION_TOPICS = ["directions", "travel_time", "distance", "documents", "timings", "price", "payment",
                   "weather", "other"]

INSTRUCTIONS = """You understand what an Indian farmer says to book a weighing slot at a government grain procurement centre in Uttarakhand. They usually speak Hindi or Hinglish (Hindi written in Latin letters), sometimes Bengali or English. The words come from speech recognition, so expect misspellings and misheard words, and work out what was meant.

Fill in only what the farmer actually said. Use "none", "" or null for anything not said. Never guess a centre, crop or quantity.

Centres (answer with the exact English name):
- Rudrapur Mandi Samiti: रुद्रपुर, rudrapur, rudarpur. District Udham Singh Nagar.
- Kichha Kharid Kendra: किच्छा, kichha, kicha. District Udham Singh Nagar.
- Haridwar Kharid Kendra: हरिद्वार, ज्वालापुर, haridwar, jwalapur. District Haridwar.
- Vikasnagar Grain Market: विकासनगर, vikasnagar. District Dehradun.
- Haldwani Mandi Centre: हल्द्वानी, haldwani. District Nainital.
If only a district is named (उधम सिंह नगर, देहरादून, नैनीताल), set district and leave centre "none".

Crops: Wheat = गेहूं, gehun, gehu. Paddy = धान, dhan, chawal, rice. Mustard = सरसों, sarson. Gram = चना, chana. Maize = मक्का, makka, makki. Bajra = बाजरा, bajra.

Quantity is in quintals. Hindi numbers: ek 1, do 2, teen 3, char 4, paanch 5, das 10, pandrah 15, bees 20, pachchees 25, tees 30, chalees 40, pachaas 50, sau 100; dedh 1.5, dhai 2.5, saadhe teen 3.5. 1 quintal is 100 kilo. A number with no unit next to a crop is the quantity.

Days: aaj is today. kal is tomorrow (for a booking it always means tomorrow). parson is the day after tomorrow. A weekday name means the next such day after today. "15 tarikh" means the next 15th. "agle hafte" (next week) with no day means from next Monday: give that date and set from_date true. Use the calendar you are given.

Slots start at 8, 10, 12 and 14 hours. subah or savere: [8, 10]. dopahar: [12, 14]. shaam, or dopahar ke baad: [14]. "8 baje": [8]. "11 baje": [10]. "2 baje": [14]. Leave start_hours empty when no time was said.

heard_centre, heard_day, heard_time, heard_crop, heard_quantity: the farmer's own few words for that detail, or "".

Sometimes the farmer asks something instead of booking or answering: how to reach the centre (kaise pahunchein, rasta, address, kahan hai), how far it is (kitni door), how long it takes to get there (kitna time lagega), what to bring (kya kagaz lana hai), when the centre opens (kitne baje khulta hai), the price (bhav, MSP), when they will be paid (paisa kab aayega), or the weather (mausam kaisa rahega, barish hogi kya, us din mausam kaisa hoga - "us din" means the day being booked). Then intent is "question" and question_topic says which; still fill centre or crop if the question names one. Any other question not about booking is question_topic "other". question_topic is "none" when there is no question.

intent: "cancel" when they want to undo a booking they already have. They rarely use the word cancel: "booking hata do", "slot nahi chahiye", "ab nahi aa paunga", "mujhe ab nahi aana hai", "meri booking radd kar do", "स्लॉट नहीं चाहिए" are all cancel. A sentence with no crop, no quantity and no new day, that asks for something to be removed or says they cannot come, is cancel, never booking - then still fill centre or date if they say which booking. "booking" for a request. When you are told the portal has just read a slot back or asked something, the reply is "yes" (haan, ha ji, theek hai, kar do, book karo) or "no" (nahi, mat karo, cancel) only when nothing is being changed; "change" when they give a new or missing detail, with only those details filled in; "question" as above; otherwise "unclear"."""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "intent": {"type": "STRING", "enum": ["booking", "cancel", "yes", "no", "change", "question", "unclear"]},
        "question_topic": {"type": "STRING", "enum": QUESTION_TOPICS + ["none"]},
        "centre": {"type": "STRING", "enum": CENTRES + ["none"]},
        "district": {"type": "STRING", "enum": DISTRICTS + ["none"]},
        "crop": {"type": "STRING", "enum": CROPS + ["none"]},
        "date": {"type": "STRING", "description": "YYYY-MM-DD, or empty when no day was said"},
        "from_date": {"type": "BOOLEAN", "description": "true when a start was given, like next week, not one day"},
        "start_hours": {"type": "ARRAY", "items": {"type": "INTEGER"}, "description": "any of 8, 10, 12, 14"},
        "quantity": {"type": "NUMBER", "nullable": True, "description": "quintals"},
        "heard_centre": {"type": "STRING"},
        "heard_day": {"type": "STRING"},
        "heard_time": {"type": "STRING"},
        "heard_crop": {"type": "STRING"},
        "heard_quantity": {"type": "STRING"},
    },
    "required": ["intent", "question_topic", "centre", "district", "crop", "date", "from_date",
                 "start_hours", "quantity"],
}

_session = requests.Session()
_cache = {}
_lock = threading.Lock()
_down_until = 0.0


class Unavailable(Exception):
    pass


def warm():
    # open the connection early so the first question doesn't wait on tls
    if not API_KEY or time.time() < _down_until:
        return

    def ping():
        try:
            _session.get("https://generativelanguage.googleapis.com/v1beta/models/" + MODELS[0],
                         headers={"x-goog-api-key": API_KEY}, timeout=TIMEOUT)
        except requests.RequestException:
            pass
    threading.Thread(target=ping, daemon=True).start()


def generate(instructions, contents, schema, label="voice ai"):
    global _down_until
    if not API_KEY:
        raise Unavailable("no GEMINI_API_KEY")
    if time.time() < _down_until:
        raise Unavailable("gemini couldn't be reached a moment ago")

    why = "no model answered"
    for model in MODELS:
        started = time.time()
        for thinking in (True, False):
            config = {"responseMimeType": "application/json", "responseSchema": schema, "temperature": 0}
            if thinking:
                config["thinkingConfig"] = {"thinkingLevel": "minimal"}
            body = {"systemInstruction": {"parts": [{"text": instructions}]},
                    "contents": contents, "generationConfig": config}
            try:
                r = _session.post(URL % model, headers={"x-goog-api-key": API_KEY}, json=body, timeout=TIMEOUT)
            except requests.RequestException as e:
                _down_until = time.time() + STAY_AWAY
                print("[%s] %s: %s, using the offline fallback for %ds" % (label, model, e.__class__.__name__, STAY_AWAY))
                raise Unavailable(str(e))
            if r.status_code == 400 and thinking:
                continue            # model doesn't support thinkingConfig
            break
        if r.status_code == 200:
            try:
                answer = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            except (KeyError, IndexError, ValueError, TypeError):
                why = "unreadable answer from %s" % model
                continue
            if isinstance(answer, dict):
                print("[%s] %s answered in %.2fs" % (label, model, time.time() - started))
                return answer
            why = "unexpected answer from %s" % model
            continue
        why = "%s from %s" % (r.status_code, model)
        print("[%s] %s" % (label, why))
    raise Unavailable(why)


def _prompt(text, alternatives, context, district, today):
    days = []
    for i in range(15):
        d = today + timedelta(days=i)
        label = {0: " (today, aaj)", 1: " (kal)", 2: " (parson)"}.get(i, "")
        days.append("%s %s%s" % (d.strftime("%a"), d.isoformat(), label))
    monday = today + timedelta(days=7 - today.weekday())
    lines = ["Today is %s %s. Next week starts Monday %s." % (today.strftime("%A"), today.isoformat(), monday.isoformat()),
             "Calendar: " + "; ".join(days) + "."]
    if district:
        lines.append("The farmer lives in %s district." % district)
    if context:
        lines.append("The portal has just said this to the farmer: " + context)
        lines.append("The farmer replied: " + text)
    else:
        lines.append("The farmer said: " + text)
    others = [a for a in alternatives if a and a != text]
    if others:
        lines.append("Speech recognition also heard it as: " + " | ".join(others))
    return "\n".join(lines)


def _checked(reply, today):
    out = {"centre": None, "district": None, "crop": None, "day": None, "day_kind": None, "hours": None,
           "quantity": None, "out_of_hours": False, "date_unclear": False, "heard": {}, "source": "ai"}

    def heard(field, fallback):
        words = str(reply.get("heard_" + field) or "").strip()[:60]
        out["heard"][field] = words or fallback

    if reply.get("centre") in CENTRES:
        out["centre"] = reply["centre"]
        heard("centre", reply["centre"])
    elif reply.get("district") in DISTRICTS:
        out["district"] = reply["district"]
        heard("centre", reply["district"])

    if reply.get("crop") in CROPS:
        out["crop"] = reply["crop"]
        heard("crop", reply["crop"])

    said_date = str(reply.get("date") or "").strip()
    if said_date:
        try:
            d = date.fromisoformat(said_date[:10])
        except ValueError:
            d = None
        if d and today <= d <= today + timedelta(days=60):
            out["day"] = d.isoformat()
            out["day_kind"] = "after" if reply.get("from_date") else "exact"
            heard("day", d.isoformat())
        else:
            out["date_unclear"] = True
            heard("day", said_date)

    hours = set()
    for h in reply.get("start_hours") or []:
        try:
            if int(h) in WINDOWS:
                hours.add(int(h))
        except (TypeError, ValueError):
            pass
    if hours:
        out["hours"] = sorted(hours)
        heard("time", ", ".join("%d:00" % h for h in sorted(hours)))

    try:
        quantity = float(reply.get("quantity"))
    except (TypeError, ValueError):
        quantity = None
    if quantity is not None and 0 < quantity <= 500:
        out["quantity"] = quantity
        heard("quantity", "%g" % quantity)

    intent = reply.get("intent")
    if intent not in ("booking", "cancel", "yes", "no", "change", "question", "unclear"):
        intent = "unclear"
    topic = None
    if intent == "question":
        topic = reply.get("question_topic") if reply.get("question_topic") in QUESTION_TOPICS else "other"
    return out, intent, topic


def understand(text, alternatives=(), context=None, district=None, today=None):
    # -> (parse() fields, intent, question topic or None)
    today = today or date.today()
    key = (text, tuple(alternatives), context, district, today.isoformat())
    with _lock:
        if key in _cache:
            return _cache[key]
    answer = generate(INSTRUCTIONS, [{"role": "user", "parts": [
        {"text": _prompt(text, alternatives, context, district, today)}]}], SCHEMA)
    result = _checked(answer, today)
    with _lock:
        if len(_cache) > 300:
            _cache.clear()
        _cache[key] = result
    return result
