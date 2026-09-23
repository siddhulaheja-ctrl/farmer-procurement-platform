"""Registration by voice, one question at a time. Gemini first, the small
parsers here if it's down, and every answer goes through the same checks as
the form. State lives in the session, state["step"] is the pending question.
"""

import re

from werkzeug.datastructures import MultiDict

import agristack
import villages
import voice_ai
import voicebook
from db import query
from i18n import t
from validation import IFSC_RE, LAND_RE, verhoeff_valid

B, E = voicebook.B, voicebook.E
norm = voicebook.normalise

DISTRICTS = ["Udham Singh Nagar", "Haridwar", "Dehradun", "Nainital"]
DISTRICT_WORDS = dict(voicebook.DISTRICT_OF)
for _w in ("haridwar", "hardwar", "हरिद्वार", "হরিদ্বার"):
    DISTRICT_WORDS[norm(_w)] = "Haridwar"

ORDER = ["name", "phone", "district", "village", "aadhaar", "bank_account", "ifsc", "land"]
OPTIONAL = {"ifsc", "land"}          # "later" is fine: flagged, and added on My Details
YES_NO = {"confirm_found", "more_land", "confirm"}

QUESTIONS = {
    "farmer_id": "Do you have a Farmer ID? Say its number, or say no.",
    "confirm_found": "Your Farmer ID belongs to %(name)s of %(village)s. Is that you? Say yes or no.",
    "name": "Say your full name, the way it is written in your bank passbook.",
    "phone": "Say your 10 digit mobile number.",
    "district": "Which district is your land in: Udham Singh Nagar, Haridwar, Dehradun or Nainital?",
    "village": "Say the name of your village.",
    "aadhaar": "Say your 12 digit Aadhaar number.",
    "bank_account": "Say your bank account number.",
    "ifsc": "Say the IFSC code from your passbook, one letter at a time. Or say later.",
    "land": "Say the land record number from your khatauni. Or say later.",
    "more_land": "Do you have land anywhere else too? Say yes or no.",
    "more_land_found": "We found %(n)d land record(s) under your Farmer ID. Do you have any other land? Say yes or no.",
    "confirm": "%(name)s, mobile ending %(phone)s, %(lands)d land record(s). Shall I register you? Say yes or no.",
    "change": "What should I change? Say name, mobile, village, Aadhaar, bank, IFSC or land.",
    "done": "Registering you now.",
}

PROBLEMS = {
    "not_understood": "Sorry, I did not catch that.",
    "farmer_id_unknown": "That Farmer ID was not found.",
    "phone_bad": "A mobile number has 10 digits.",
    "phone_taken": "This mobile number is already registered. You can sign in with it instead.",
    "aadhaar_bad": "That Aadhaar number does not look right.",
    "aadhaar_taken": "This Aadhaar number is already registered. Sign in with that account and add your land on My Details.",
    "bank_bad": "An account number has 9 to 18 digits.",
    "ifsc_bad": "That IFSC code did not sound right.",
    "land_bad": "That land record number did not sound right.",
    "district_bad": "That district is not one of ours.",
}
INVALID = {"phone": "phone_bad", "aadhaar": "aadhaar_bad", "bank_account": "bank_bad", "ifsc": "ifsc_bad",
           "land": "land_bad", "district": "district_bad"}

# the change menu: button value, label, and the words that pick it. checked in
# this order, so "aadhaar number" is aadhaar before "number" can mean mobile
CHANGE = [
    ("aadhaar", "Aadhaar", ["aadhaar", "aadhar", "adhar", "आधार", "আধার"]),
    ("ifsc", "IFSC code", ["ifsc", "आईएफएससी"]),
    ("bank_account", "Bank account", ["bank", "account", "khata", "खाता", "बैंक", "ব্যাংক", "অ্যাকাউন্ট"]),
    ("land", "Land", ["land", "zameen", "jameen", "zamin", "khatauni", "जमीन", "खतौनी", "জমি"]),
    ("village", "Village", ["village", "gaon", "gaanv", "गांव", "গ্রাম"]),
    ("district", "District", ["district", "zila", "jila", "जिला", "জেলা"]),
    ("name", "Name", ["name", "naam", "नाम", "নাম"]),
    ("phone", "Mobile", ["mobile", "phone", "number", "मोबाइल", "फोन", "नंबर", "মোবাইল", "নম্বর"]),
]
CHANGE_BUTTONS = {"aadhaar": "aadhaar", "ifsc": "ifsc", "bank_account": "bank", "land": "land",
                  "village": "village", "district": "district", "name": "name", "phone": "mobile"}

SKIP = ["baad mein", "baad me", "bad me", "bad mein", "later", "skip", "pata nahi", "nahi pata", "abhi nahi",
        "बाद में", "पता नहीं", "अभी नहीं", "পরে", "জানি না"]
SKIP_RE = re.compile(B + "(%s)" % voicebook._alt(SKIP) + E)


# ---- reading what was said ----------------------------------------------------

DIGIT_WORDS = {
    0: ["zero", "shunya", "shoonya", "sunya", "sifar", "shunye", "शून्य", "जीरो", "सिफर", "শূন্য", "জিরো"],
    1: ["one", "ek", "एक", "এক"], 2: ["two", "do", "दो", "dui", "দুই"], 3: ["three", "teen", "tin", "तीन", "তিন"],
    4: ["four", "char", "chaar", "चार", "চার"], 5: ["five", "paanch", "panch", "पांच", "পাঁচ"],
    6: ["six", "chhe", "chhah", "che", "छह", "छः", "छे", "ছয়"], 7: ["seven", "saat", "सात", "সাত"],
    8: ["eight", "aath", "आठ", "আট"], 9: ["nine", "nau", "नौ", "নয়"],
}
DIGIT_OF = {norm(w): str(d) for d, words in DIGIT_WORDS.items() for w in words}
# "likh do", "kar do": there the "do" is a verb, not a two
VERBS = {norm(w) for w in ("kar", "likh", "bata", "le", "de", "daal", "dal", "कर", "लिख", "बता", "ले", "दे", "डाल")}
LETTER_NAMES = {norm(k): v for k, v in {
    "ए": "A", "बी": "B", "सी": "C", "डी": "D", "ई": "E", "एफ": "F", "एच": "H", "आई": "I", "जे": "J",
    "के": "K", "एल": "L", "एम": "M", "एन": "N", "ओ": "O", "पी": "P", "क्यू": "Q", "आर": "R", "एस": "S",
    "टी": "T", "यू": "U", "वी": "V", "डब्ल्यू": "W", "एक्स": "X", "वाई": "Y", "जेड": "Z"}.items()}


def spoken_digits(text):
    """"chaar do saat 1 2" -> "42712". Tens words count too ("das" is 10)."""
    out, previous, double = [], "", False
    for tok in norm(text).replace("-", " ").split():
        if tok in ("double", "डबल", "ডাবল"):
            double = True
            continue
        if tok == "do" and previous in VERBS:
            previous = tok
            continue
        digit = None
        if tok.isdigit():
            digit = tok
        elif tok in DIGIT_OF:
            digit = DIGIT_OF[tok]
        elif tok in voicebook.NUMBER_OF and float(voicebook.NUMBER_OF[tok]).is_integer():
            digit = str(int(voicebook.NUMBER_OF[tok]))
        previous = tok
        if digit is None:
            continue
        out.append(digit * 2 if double and len(digit) == 1 else digit)
        double = False
    return "".join(out)


def _code_tokens(text):
    """Letters and digits as spoken, single letters and digits run together:
    "u s n 104238 1 2" -> ["USN", "104238", "12"]."""
    pieces = []
    for tok in norm(text).replace("-", " ").replace("/", " ").split():
        if tok in DIGIT_OF:
            piece = DIGIT_OF[tok]
        elif tok in LETTER_NAMES:
            piece = LETTER_NAMES[tok]
        elif re.fullmatch(r"[a-z0-9]+", tok):
            piece = tok.upper()
        else:
            continue
        if pieces and len(piece) == 1 and len(pieces[-1][1]) and pieces[-1][0] == piece.isdigit() and pieces[-1][2]:
            pieces[-1] = (pieces[-1][0], pieces[-1][1] + piece, True)
        else:
            pieces.append((piece.isdigit(), piece, len(piece) == 1))
    return [p[1] for p in pieces]


def parse_ifsc(text):
    code = "".join(_code_tokens(text))
    if len(code) == 11 and code[4] == "O":
        code = code[:4] + "0" + code[5:]         # the fifth character is always the digit zero
    return code


def parse_land(text):
    tokens = _code_tokens(text)
    letters = "".join(x for x in tokens if x.isalpha())
    numbers = [x for x in tokens if x.isdigit()]
    if len(numbers) == 1 and len(numbers[0]) >= 5:
        numbers = [numbers[0][:-2], numbers[0][-2:]]
    if letters and len(numbers) >= 2:
        return "%s-%s-%s" % (letters, numbers[0], numbers[-1])
    return "-".join(tokens)


FILLER = [norm(w) for w in ("mera naam", "my name is", "naam", "name", "mera", "hai", "he", "h", "is", "गांव", "गाँव",
                             "मेरा नाम", "नाम", "मेरा", "है", "hamara", "हमारा", "गाँव का नाम", "gaon ka naam", "gaon",
                             "village", "আমার নাম", "নাম", "আমার", "গ্রাম", "hoon", "हूं", "ji", "जी")]


def parse_words(text):
    s = norm(text)
    for f in sorted(FILLER, key=len, reverse=True):
        s = re.sub(B + re.escape(f) + E, " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s.title() if re.fullmatch(r"[a-z .]+", s or "-") else s


def parse_district(text):
    s = norm(text)
    for word in sorted(DISTRICT_WORDS, key=len, reverse=True):
        if re.search(B + re.escape(word) + E, s):
            return DISTRICT_WORDS[word]
    return ""


PARSE = {"farmer_id": spoken_digits, "phone": spoken_digits, "aadhaar": spoken_digits,
         "bank_account": spoken_digits, "ifsc": parse_ifsc, "land": parse_land,
         "district": parse_district, "name": parse_words, "village": parse_words}


def valid(field, value):
    value = value or ""
    if field == "farmer_id":
        return len(value) == agristack.FARMER_ID_LENGTH and value.isdigit()
    if field == "phone":
        return bool(re.fullmatch(r"[6-9]\d{9}", value))
    if field == "aadhaar":
        return bool(re.fullmatch(r"[2-9]\d{11}", value)) and verhoeff_valid(value)
    if field == "bank_account":
        return bool(re.fullmatch(r"\d{9,18}", value))
    if field == "ifsc":
        return bool(IFSC_RE.match(value))
    if field == "land":
        return bool(LAND_RE.match(value))
    if field == "district":
        return value in DISTRICTS
    if field in ("name", "village"):
        return len(value.strip()) >= (3 if field == "name" else 2)
    return False


def _tidy(field, value):
    value = (value or "").strip()
    if field in ("farmer_id", "phone", "aadhaar", "bank_account"):
        return re.sub(r"\D", "", value)
    if field in ("ifsc", "land"):
        return re.sub(r"\s+", "", value.upper())
    return value


# ---- asking the AI --------------------------------------------------------------

AI_INSTRUCTIONS = """You help a farmer in Uttarakhand register on a government grain procurement website by speaking. They were asked one question and answered out loud, usually in Hindi or Hinglish (Hindi written in Latin letters), sometimes Bengali or English. The words come from speech recognition, so expect misheard words, and work out what was meant.

Give their answer to that one question only.

intent:
- "answer" when they gave the thing that was asked for
- "yes" or "no" for a yes/no question. When asked for a Farmer ID, saying they don't have one is "no".
- "skip" when they say later, skip, or that they don't know
- "unclear" when you can't tell

value, written the way the form needs it, or "" when there is none:
- farmer_id, phone, aadhaar, bank_account: only the digits 0-9. Turn spoken number words into digits ("chaar do saat" is 427, "double five" is 55). Never guess a digit that wasn't said.
- name, village: in English letters, Title Case, transliterated from Hindi or Bengali script if needed ("रमेश चंद्र" is "Ramesh Chandra"). Leave out words like "mera naam", "hai".
- district: exactly one of Udham Singh Nagar, Haridwar, Dehradun, Nainital.
- ifsc: 11 characters, uppercase: 4 letters, the digit 0, then 6 letters or digits. Letters may be spoken one by one.
- land: uppercase like USN-104238-12: letters, a hyphen, digits, a hyphen, digits.
"""

AI_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "intent": {"type": "STRING", "enum": ["answer", "yes", "no", "skip", "unclear"]},
        "value": {"type": "STRING"},
    },
    "required": ["intent", "value"],
}

FIELD_HELP = {
    "farmer_id": "their Farmer ID (Kisan Pehchaan Patra) number, 11 digits",
    "confirm_found": "yes or no: whether the name read out to them is them",
    "name": "their full name",
    "phone": "their 10 digit mobile number",
    "district": "the district their land is in",
    "village": "the name of their village",
    "aadhaar": "their 12 digit Aadhaar number",
    "bank_account": "their bank account number, 9 to 18 digits",
    "ifsc": "their bank's IFSC code",
    "land": "a land record (khatauni) number",
    "more_land": "yes or no: whether they have land anywhere else",
    "confirm": "yes or no: whether to register them with the details read out",
}

_cache = {}


def _ask_ai(field, question, text, guesses):
    key = (field, text, tuple(guesses))
    if key in _cache:
        return _cache[key]
    prompt = "Field: %s (%s)\nQuestion they were asked: %s\nWhat they said: %s" % (field, FIELD_HELP[field], question, text)
    if guesses:
        prompt += "\nOther ways the speech engine heard it: " + " | ".join(guesses)
    answer = voice_ai.generate(AI_INSTRUCTIONS, [{"role": "user", "parts": [{"text": prompt}]}], AI_SCHEMA,
                               label="voice register")
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = answer
    return answer


def _understand_village(text, guesses, question, district):
    # try the list first, then let the AI pick from it
    for candidate in [text] + list(guesses):
        found = villages.match(district, candidate)
        if found:
            return "answer", found, "parser"
    try:
        listed = ", ".join(villages.names(district))
        reply = _ask_ai("village", "%s (the villages they can pick from: %s)" % (question, listed), text, list(guesses))
        found = villages.match(district, reply.get("value"))
        if reply.get("intent") == "answer" and found:
            return "answer", found, "ai"
        return "unclear", "", "ai"
    except voice_ai.Unavailable:
        return "unclear", "", "parser"


def understand(field, text, guesses=(), question="", district=""):
    # -> (intent, value, source). intent: answer/yes/no/skip/invalid/unclear
    if field == "village":
        return _understand_village(text, guesses, question, district)
    source = "parser"
    if field in YES_NO:
        kind = voicebook.answer_kind(text)
        if kind:
            return kind, "", source
    if field in OPTIONAL and SKIP_RE.search(norm(text)):
        return "skip", "", source
    if field == "farmer_id" and voicebook.answer_kind(text) == "no" and not spoken_digits(text):
        return "no", "", source
    try:
        reply = _ask_ai(field, question, text, list(guesses))
        source = "ai"
        intent, value = reply.get("intent"), _tidy(field, reply.get("value"))
        if intent == "answer" and field not in YES_NO and valid(field, value):
            return "answer", value, source
        if intent in ("yes", "no") and (field in YES_NO or field == "farmer_id"):
            return intent, "", source
        if intent == "skip" and field in OPTIONAL:
            return "skip", "", source
    except voice_ai.Unavailable:
        pass
    if field in PARSE:
        for candidate in [text] + list(guesses):
            value = PARSE[field](candidate)
            if valid(field, value):
                return "answer", value, source
        best = PARSE[field](text)
        if best and field not in ("name", "village"):
            return "invalid", best, source
    return "unclear", "", source


# ---- the conversation ---------------------------------------------------------

def fresh():
    return {"step": "farmer_id", "data": {}, "lands": [], "farmer_id": "", "registry": False,
            "misses": 0, "back": False, "asked_more": False}


def _question(state):
    step, d = state["step"], state["data"]
    if step == "confirm_found":
        return t(QUESTIONS[step]) % {"name": d.get("name", ""), "village": t(d.get("village", ""))}
    if step == "more_land" and state["registry"] and not state["asked_more"]:
        return t(QUESTIONS["more_land_found"]) % {"n": len(state["lands"])}
    if step == "confirm":
        return t(QUESTIONS[step]) % {"name": d.get("name", ""), "phone": " ".join(d.get("phone", "")[-4:]),
                                     "lands": len(state["lands"])}
    return t(QUESTIONS[step])


def _buttons(state):
    step = state["step"]
    if step in YES_NO:
        return [("yes", t("Yes"), "yes-btn"), ("no", t("No"), "no-btn")]
    if step == "farmer_id":
        return [("no", t("I don't have one"), "secondary")]
    if step in OPTIONAL:
        return [("later", t("Later"), "secondary")]
    if step == "district":
        return [(x, t(x), "secondary") for x in DISTRICTS]
    if step == "village":
        return [(x, t(x), "secondary") for x in villages.names(state["data"].get("district"))]
    if step == "change":
        return [(CHANGE_BUTTONS[key], t(label), "secondary") for key, label, _ in CHANGE]
    return []


def current(state, problem=None, heard=None, source=None):
    say = _question(state)
    if problem:
        say = t(PROBLEMS[problem]) + " " + say
    return {"stage": state["step"], "say": say, "listen": None if state["step"] == "done" else "answer",
            "buttons": _buttons(state), "repeat": bool(problem), "heard": heard, "source": source, "url": None}


def _after(state, field):
    if field == "land":
        return "more_land"
    if state["back"]:
        state["back"] = False
        return "confirm"
    if field == "phone" and state["registry"]:
        return "more_land"
    i = ORDER.index(field)
    return ORDER[i + 1] if i + 1 < len(ORDER) else "more_land"


def _miss(state, problem, heard, source):
    state["misses"] += 1
    return current(state, problem, heard, source)


def advance(state, text, guesses=()):
    step = state["step"]
    if step == "done":
        return current(state)

    if step == "change":
        s = norm(text)
        for key, _, words in CHANGE:
            if any(re.search(B + re.escape(norm(w)) + E, s) for w in words):
                state["back"] = True
                if key in ("aadhaar", "bank_account", "ifsc"):
                    state["registry"] = False       # they want to give these themselves
                if key == "land":
                    state["lands"] = [x for x in state["lands"] if x.get("source") == "registry"]
                state["step"] = key
                state["misses"] = 0
                return current(state, heard=text)
        return _miss(state, "not_understood", text, "parser")

    intent, value, source = understand(step, text, guesses, _question(state),
                                       district=state["data"].get("district", ""))
    if intent == "unclear":
        return _miss(state, "not_understood", text, source)

    if step == "farmer_id":
        if intent == "no":
            state["step"] = "name"
        else:
            record = agristack.lookup(value) if intent == "answer" else None
            if record is None:
                state["misses"] += 1
                if state["misses"] >= 3:           # stop asking, carry on by hand
                    state["step"], state["misses"] = "name", 0
                return current(state, "farmer_id_unknown", text, source)
            state.update(farmer_id=record["farmer_id"], registry=True, step="confirm_found",
                         data={"name": record["name"], "village": record["village"], "district": record["district"]},
                         lands=[dict(x, source="registry") for x in record["lands"]])
    elif step == "confirm_found":
        if intent == "yes":
            state["step"] = "phone"
        elif intent == "no":
            state.update(farmer_id="", registry=False, data={}, lands=[], step="name")
        else:
            return _miss(state, "not_understood", text, source)
    elif step == "more_land":
        if intent not in ("yes", "no"):
            return _miss(state, "not_understood", text, source)
        state["asked_more"] = True
        state["step"] = "land" if intent == "yes" else "confirm"
    elif step == "confirm":
        if intent not in ("yes", "no"):
            return _miss(state, "not_understood", text, source)
        state["step"] = "done" if intent == "yes" else "change"
    else:
        if intent == "skip":
            state["step"] = "confirm" if step == "land" else _after(state, step)
        elif intent == "invalid":
            return _miss(state, INVALID.get(step, "not_understood"), text, source)
        elif intent == "answer":
            if step == "phone" and query("SELECT 1 FROM farmers WHERE phone_number = ?", (value,), one=True):
                return _miss(state, "phone_taken", text, source)
            if step == "aadhaar" and query("SELECT 1 FROM farmers WHERE aadhaar_number = ?", (value,), one=True):
                return _miss(state, "aadhaar_taken", text, source)
            if step == "land":
                if value not in [x["land_record_id"] for x in state["lands"]]:
                    state["lands"].append({"land_record_id": value, "village": state["data"].get("village", ""),
                                           "district": state["data"].get("district", ""), "area_acres": None,
                                           "source": "manual"})
            else:
                state["data"][step] = value
            if step == "district" and state["data"].get("village") and not villages.valid(value, state["data"]["village"]):
                del state["data"]["village"]        # the one they gave is in another district
                state["step"] = "village"
            else:
                state["step"] = _after(state, step)
        else:
            return _miss(state, "not_understood", text, source)

    state["misses"] = 0
    return current(state, heard=text, source=source)


def as_form(state):
    d = state["data"]
    pairs = [("name", d.get("name", "")), ("phone_number", d.get("phone", "")), ("village", d.get("village", "")),
             ("district", d.get("district", "")), ("aadhaar_number", d.get("aadhaar", "")),
             ("bank_account", d.get("bank_account", "")), ("ifsc_code", d.get("ifsc", "")),
             ("bank_name_on_account", ""), ("agristack_id", state.get("farmer_id", "")),
             ("use_registry", "1" if state["registry"] else "")]
    for land in state["lands"]:
        pairs += [("land_record_id", land["land_record_id"]), ("land_village", land.get("village") or ""),
                  ("land_area", "" if land.get("area_acres") is None else str(land["area_acres"])),
                  ("land_source", land.get("source", "manual"))]
    return MultiDict(pairs)


def failed(state, result):
    state["step"] = {"name": "name", "phone": "phone", "aadhaar": "aadhaar", "farmer_id": "farmer_id",
                     "district": "district", "village": "village", "land": "land"}.get(
        result.get("field"), "confirm")
    state["back"] = state["step"] != "farmer_id"
    step = current(state)
    step["say"] = result["error"] + " " + step["say"]
    step["repeat"] = True
    return step
