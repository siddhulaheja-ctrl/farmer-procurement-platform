"""Voice booking: word-list parser for centre / day / time / crop / quantity
(english, hinglish, hindi, bengali) and picking a free slot for it.

Works offline. voice_ai.py tries gemini first and this fills in the gaps.
Nothing here books, propose() only suggests.
"""

import re
import unicodedata
from datetime import date, datetime, timedelta

from db import query
from i18n import t

# a "letter" for word boundaries. \w alone misses the vowel signs and viramas
# inside hindi and bengali words, so "कल" would match inside "कलम"
LETTERS = r"\wऀ-ॿঀ-৿"
B = r"(?<![%s])" % LETTERS
E = r"(?![%s])" % LETTERS

DIGITS = str.maketrans("०१२३४५६७८९০১২৩৪৫৬৭৮৯", "01234567890123456789")


def normalise(text):
    s = unicodedata.normalize("NFC", text or "").translate(DIGITS).lower()
    s = s.replace("़", "")                  # hindi nukta: हफ़्ते and हफ्ते are the same word
    s = s.replace("ँ", "ं")            # chandrabindu and anusvara: गेहूँ, गेहूं
    s = re.sub(r"[।॥,!?;\"'()]", " ", s)   # dandas and punctuation
    return re.sub(r"\s+", " ", s).strip()


# ---- near misses -------------------------------------------------------------
# "rudarpoor", "haldvani", "kicha", "कुंटल"... compare by rough sound, longer
# words can be a letter or two off. short ones must match exactly ("do", "se")

ROMAN_SOUNDS = (("ph", "f"), ("sh", "s"), ("ch", "\x01"), ("kh", "k"), ("gh", "g"), ("th", "t"),
                ("dh", "d"), ("bh", "b"), ("ck", "k"), ("q", "k"), ("c", "k"), ("w", "v"), ("z", "j"),
                ("aa", "a"), ("ee", "i"), ("oo", "u"), ("ou", "u"), ("\x01", "ch"))
INDIC_SOUNDS = str.maketrans({"्": None, "্": None, "ी": "ि", "ू": "ु", "ई": "इ", "ऊ": "उ",
                              "श": "स", "ष": "स", "ण": "न", "ী": "ি", "ূ": "ু", "ঈ": "ই", "ঊ": "উ",
                              "শ": "স", "ষ": "স", "ণ": "ন"})


def sound(word):
    # crude phonetic key
    w = word.translate(INDIC_SOUNDS)
    for a, b in ROMAN_SOUNDS:
        w = w.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", w)


def _distance(a, b, limit):
    # levenshtein with early exit
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


# ---- word lists --------------------------------------------------------------
# keys must match the db (procurement_centres.name etc)

CENTRES = {
    "Rudrapur Mandi Samiti": ["rudrapur", "rudarpur", "rudra pur", "रुद्रपुर", "रुद्रपूर", "রুদ্রপুর"],
    "Kichha Kharid Kendra": ["kichha", "kichcha", "kicha", "किच्छा", "किछा", "किच्चा", "কিচ্ছা", "কিছা"],
    "Haridwar Kharid Kendra": ["haridwar", "hardwar", "jwalapur", "हरिद्वार", "ज्वालापुर",
                               "হরিদ্বার", "জ্বালাপুর"],
    "Vikasnagar Grain Market": ["vikasnagar", "vikas nagar", "विकासनगर", "विकास नगर",
                                "বিকাশনগর", "বিকাশ নগর"],
    "Haldwani Mandi Centre": ["haldwani", "haldwaani", "हल्द्वानी", "हलद्वानी", "हल्दवानी",
                              "হলদোয়ানি", "হলদুয়ানি"],
}

DISTRICTS = {
    "Udham Singh Nagar": ["udham singh nagar", "udhamsingh nagar", "usn", "उधम सिंह नगर",
                          "ऊधम सिंह नगर", "উধম সিং নগর"],
    "Dehradun": ["dehradun", "dehra dun", "देहरादून", "দেহরাদুন"],
    "Nainital": ["nainital", "नैनीताल", "নৈনিতাল"],
}

CROPS = {
    "Wheat": ["wheat", "gehu", "gehun", "gehoon", "gehum", "गेहूं", "गेहू", "गेंहू", "গম"],
    "Paddy": ["paddy", "dhan", "dhaan", "rice", "chawal", "chaawal", "धान", "चावल", "ধান", "চাল"],
    "Maize": ["maize", "corn", "makka", "makki", "makai", "मक्का", "मक्की", "मकई", "ভুট্টা"],
    "Gram": ["gram", "chana", "channa", "chickpea", "chickpeas", "चना", "ছোলা"],
    "Mustard": ["mustard", "sarson", "sarso", "सरसों", "सरसो", "সরষে", "সরিষা"],
    "Bajra": ["bajra", "bajara", "millet", "बाजरा", "বাজরা"],
}

# days from today
RELATIVE_DAYS = {
    0: ["aaj", "today", "आज", "আজ", "আজকে"],
    1: ["kal", "kaal", "tomorrow", "कल", "কাল", "কালকে", "আগামীকাল"],
    2: ["parso", "parson", "parsho", "day after tomorrow", "परसों", "परसो", "পরশু"],
}

NEXT_WEEK = ["agle hafte", "agle hafta", "agle week", "next week", "agle saptah",
             "अगले हफ्ते", "अगले हफ्ता", "अगले सप्ताह", "পরের সপ্তাহে", "পরের সপ্তাহ", "আগামী সপ্তাহে"]

WEEKDAYS = {   # monday is 0, like date.weekday()
    0: ["monday", "somvar", "somwar", "सोमवार", "সোমবার"],
    1: ["tuesday", "mangalvar", "mangalwar", "मंगलवार", "মঙ্গলবার"],
    2: ["wednesday", "budhvar", "budhwar", "बुधवार", "বুধবার"],
    3: ["thursday", "guruvar", "guruwar", "brihaspativar", "veervar", "virvar", "गुरुवार",
        "बृहस्पतिवार", "वीरवार", "বৃহস্পতিবার"],
    4: ["friday", "shukravar", "shukrawar", "sukravar", "शुक्रवार", "শুক্রবার"],
    5: ["saturday", "shanivar", "shaniwar", "शनिवार", "শনিবার"],
    6: ["sunday", "ravivar", "raviwar", "itvar", "etwar", "रविवार", "इतवार", "রবিবার"],
}

MONTHS = {
    1: ["january", "jan", "janvari", "janwari", "जनवरी", "জানুয়ারি"],
    2: ["february", "feb", "farvari", "farwari", "फरवरी", "ফেব্রুয়ারি"],
    3: ["march", "mar", "maarch", "मार्च", "মার্চ"],
    4: ["april", "apr", "aprail", "अप्रैल", "এপ্রিল"],
    # not "mai": in hinglish that is "in", as in "rudrapur mai 15 tarikh"
    5: ["may", "मई", "মে"],
    6: ["june", "jun", "joon", "जून", "জুন"],
    7: ["july", "jul", "julai", "जुलाई", "জুলাই"],
    8: ["august", "aug", "agast", "अगस्त", "আগস্ট"],
    9: ["september", "sep", "sept", "sitambar", "sitamber", "सितंबर", "सितम्बर", "সেপ্টেম্বর"],
    10: ["october", "oct", "aktubar", "aktoobar", "अक्टूबर", "অক্টোবর"],
    11: ["november", "nov", "navambar", "नवंबर", "नवम्बर", "নভেম্বর"],
    12: ["december", "dec", "disambar", "दिसंबर", "दिसम्बर", "ডিসেম্বর"],
}
# "ko" too, straight after a number: "15 ko" is the 15th
DATE_WORDS = ["tarikh", "tareekh", "tarik", "tareek", "date", "तारीख", "তারিখ", "তারিখে", "ko", "को"]

# centres weigh from 08:00 to 16:00 in two-hour windows, keyed by start hour
PARTS_OF_DAY = {
    "morning": ["subah", "subha", "subeh", "savere", "sawere", "सुबह", "सवेरे", "morning",
                "সকাল", "সকালে"],
    "afternoon": ["dopahar", "dopaher", "dophar", "दोपहर", "afternoon", "noon", "দুপুর", "দুপুরে"],
    "evening": ["shaam", "sham", "शाम", "evening", "বিকেল", "বিকালে", "সন্ধ্যা", "সন্ধ্যায়"],
}
PART_HOURS = {"morning": [8, 10], "afternoon": [12, 14], "evening": [14]}
TIME_UNITS = ["baje", "bajay", "baaje", "बजे", "বাজে", "am", "pm", "a.m.", "p.m.", "o clock", "oclock"]
RANGE_WORDS = ["se", "से", "to", "থেকে", "-"]

QUINTAL = ["quintal", "quintals", "kuintal", "kwintal", "kvintal", "kintal", "quental", "qtl",
           "क्विंटल", "क्विन्टल", "कुंतल", "कुन्तल", "क्वींटल", "কুইন্টাল", "কুইন্টল"]

NUMBERS = {
    1: ["one", "ek", "एक", "এক"], 2: ["two", "do", "दो", "dui", "দুই"],
    3: ["three", "teen", "tin", "तीन", "তিন"], 4: ["four", "char", "chaar", "चार", "চার"],
    5: ["five", "paanch", "panch", "पांच", "পাঁচ"], 6: ["six", "chhe", "chhah", "छह", "छः", "छे", "ছয়"],
    7: ["seven", "saat", "सात", "সাত"], 8: ["eight", "aath", "आठ", "আট"],
    9: ["nine", "nau", "नौ", "নয়"], 10: ["ten", "das", "dus", "dosh", "दस", "দশ"],
    11: ["eleven", "gyarah", "ग्यारह"], 12: ["twelve", "barah", "बारह"],
    13: ["terah", "तेरह"], 14: ["chaudah", "चौदह"],
    15: ["fifteen", "pandrah", "पंद्रह", "पन्द्रह", "পনেরো"], 16: ["solah", "सोलह"],
    17: ["satrah", "सत्रह"], 18: ["atharah", "अठारह"], 19: ["unnis", "उन्नीस"],
    20: ["twenty", "bees", "bis", "kuri", "बीस", "বিশ", "কুড়ি"],
    25: ["pachchees", "pachis", "पच्चीस", "পঁচিশ"],
    30: ["thirty", "tees", "tis", "तीस", "তিরিশ", "ত্রিশ"], 35: ["paintees", "पैंतीस"],
    40: ["forty", "chalees", "chalis", "चालीस", "চল্লিশ"], 45: ["paintalees", "पैंतालीस"],
    50: ["fifty", "pachaas", "pachas", "पचास", "পঞ্চাশ"], 60: ["sixty", "saath", "साठ", "ষাট"],
    70: ["seventy", "sattar", "सत्तर", "সত্তর"], 80: ["eighty", "assi", "अस्सी", "আশি"],
    90: ["ninety", "nabbe", "नब्बे", "নব্বই"], 100: ["hundred", "sau", "सौ", "একশো"],
    1.5: ["dedh", "डेढ़"], 2.5: ["dhai", "ढाई"],
}
HALF_MORE = ["saadhe", "sadhe", "साढ़े"]      # saadhe teen = 3.5


def _lookup(table):
    out = {}
    for value, words in table.items():
        for w in words:
            out[normalise(w)] = value
    return out, "|".join(re.escape(w) for w in sorted(out, key=len, reverse=True))


def _alt(words):
    return "|".join(re.escape(normalise(w)) for w in sorted(words, key=len, reverse=True))


CENTRE_OF, CENTRE_ALT = _lookup(CENTRES)
DISTRICT_OF, DISTRICT_ALT = _lookup(DISTRICTS)
CROP_OF, CROP_ALT = _lookup(CROPS)
REL_OF, REL_ALT = _lookup(RELATIVE_DAYS)
WEEKDAY_OF, WEEKDAY_ALT = _lookup(WEEKDAYS)
MONTH_OF, MONTH_ALT = _lookup(MONTHS)
PART_OF, PART_ALT = _lookup(PARTS_OF_DAY)
NUMBER_OF, NUMBER_ALT = _lookup(NUMBERS)

NUM = r"\d+(?:\.\d+)?|" + NUMBER_ALT

QUANTITY_RE = re.compile(
    B + r"(?:(?P<half>%s)\s*)?(?P<a>%s)(?:\s*(?P<b>%s))?\s*(?P<unit>%s)" % (_alt(HALF_MORE), NUM, NUM, _alt(QUINTAL)) + E)
TIME_RANGE_RE = re.compile(
    B + r"(?P<h>%s)(?::\d\d)?\s*(?:%s)?\s*(?:%s)\s*(?P<h2>%s)(?::\d\d)?\s*(?P<unit>%s)" % (
        NUM, _alt(TIME_UNITS), _alt(RANGE_WORDS), NUM, _alt(TIME_UNITS)) + E)
TIME_RE = re.compile(B + r"(?P<h>%s)(?::\d\d)?\s*(?P<unit>%s)" % (NUM, _alt(TIME_UNITS)) + E)
DATE_MONTH_RE = re.compile(
    B + r"(?:(?P<d>\d{1,2})(?:st|nd|rd|th)?\s*(?:%s)?\s*(?P<m>%s)|(?P<m2>%s)\s*(?P<d2>\d{1,2})(?:st|nd|rd|th)?)" % (
        _alt(DATE_WORDS), MONTH_ALT, MONTH_ALT) + E)
DATE_WORD_RE = re.compile(B + r"(?P<d>\d{1,2})(?:st|nd|rd|th)?\s*(?:%s)" % _alt(DATE_WORDS) + E)
DATE_SLASH_RE = re.compile(B + r"(?P<d>\d{1,2})\s*/\s*(?P<m>\d{1,2})" + E)
REL_RE = re.compile(B + "(%s)" % REL_ALT + E)
NEXT_WEEK_RE = re.compile(B + "(%s)" % _alt(NEXT_WEEK) + E)
WEEKDAY_RE = re.compile(B + "(%s)" % WEEKDAY_ALT + E)
PART_RE = re.compile(B + "(%s)" % PART_ALT + E)
CENTRE_RE = re.compile(B + "(%s)" % CENTRE_ALT + E)
DISTRICT_RE = re.compile(B + "(%s)" % DISTRICT_ALT + E)
CROP_RE = re.compile(B + "(%s)" % CROP_ALT + E)


def _sounds_like(tables):
    out = []
    for table, most in tables:
        words = [w for ws in table.values() for w in ws] if isinstance(table, dict) else table
        for w in words:
            w = normalise(w)
            out.append((len(w.split(" ")), " ".join(sound(t) for t in w.split(" ")), w, most))
    return out


# numbers, months and date words aren't matched loosely at all: "do", "mar" and
# "date" are everyday words. day words must sound exactly right - one letter
# turns "person" into "parson" - though "call" still sounds like "kal"
SOUNDS_LIKE = _sounds_like([(CENTRES, 2), (DISTRICTS, 2), (CROPS, 2), (WEEKDAYS, 2),
                            (RELATIVE_DAYS, 0), (PARTS_OF_DAY, 2), (NEXT_WEEK, 2), (QUINTAL, 2)])


def _correct(text):
    # "rudarpoor" -> "rudrapur"
    tokens = text.split(" ")
    out, i = [], 0
    while i < len(tokens):
        for n in (3, 2, 1):
            chunk = tokens[i:i + n]
            if len(chunk) < n or any(re.search(r"[\d.:/]", tok) for tok in chunk):
                continue
            key = " ".join(sound(tok) for tok in chunk)
            best, best_d = None, None
            for words, alias_key, alias, most in SOUNDS_LIKE:
                if words != n:
                    continue
                limit = min(most, 0 if len(alias_key) <= 4 else 1 if len(alias_key) <= 7 else 2)
                d = _distance(key, alias_key, limit)
                if d <= limit and (best_d is None or d < best_d):
                    best, best_d = alias, d
            if best:
                out.append(best)
                i += n
                break
        else:
            out.append(tokens[i])
            i += 1
    return " ".join(out)


def _number(token):
    return float(token) if re.fullmatch(r"\d+(?:\.\d+)?", token) else float(NUMBER_OF[token])


def _start_hour(hour, pm, part):
    if (pm or part in ("afternoon", "evening")) and hour < 12:
        hour += 12
    elif hour <= 7:
        hour += 12          # "3 baje" at a mandi is the afternoon, nobody weighs at 3am
    if 8 <= hour < 16:
        return 8 + 2 * ((hour - 8) // 2)
    return None


def _day_of_month(day, month, today):
    if month:
        for year in (today.year, today.year + 1):
            try:
                d = date(year, month, day)
            except ValueError:
                return None
            if d >= today:
                return d
        return None
    year, month = today.year, today.month
    for _ in range(2):
        try:
            d = date(year, month, day)
            if d >= today:
                return d
        except ValueError:
            pass
        month, year = (1, year + 1) if month == 12 else (month + 1, year)
    return None


def parse(text, today=None):
    # heard = the words each field came from, shown as "(heard: kal)"
    today = today or date.today()
    work = _correct(normalise(text))
    out = {"centre": None, "district": None, "crop": None, "day": None, "day_kind": None,
           "hours": None, "quantity": None, "out_of_hours": False, "date_unclear": False,
           "heard": {}}

    def take(m):
        # blank what was used, so "20 quintal" can't also be read as the 20th
        nonlocal work
        work = work[:m.start()] + " " * (m.end() - m.start()) + work[m.end():]
        return m.group(0).strip()

    # quantity first: it's the one number with a unit that can't mean anything else
    m = QUANTITY_RE.search(work)
    if m:
        qty = _number(m.group("a"))
        if m.group("b"):
            second = _number(m.group("b"))
            # "twenty five" adds up, anything else means the farmer corrected themselves
            qty = qty + second if qty >= 20 and qty % 10 == 0 and second < 10 else second
        if m.group("half"):
            qty += 0.5
        out["quantity"] = qty
        out["heard"]["quantity"] = take(m)

    m = PART_RE.search(work)
    part = PART_OF[m.group(1)] if m else None
    if m:
        out["heard"]["time"] = m.group(1)

    m = TIME_RANGE_RE.search(work) or TIME_RE.search(work)
    if m:
        try:
            hour = int(_number(m.group("h")))
        except (KeyError, ValueError):
            hour = None
        if hour is not None and hour <= 24:
            start = _start_hour(hour, m.group("unit") in ("pm", "p.m."), part)
            phrase = take(m)
            out["heard"]["time"] = (out["heard"].get("time", "") + " " + phrase).strip()
            if start is None:
                out["out_of_hours"] = True
            else:
                out["hours"] = [start]
    # "shaam 5 baje" is after closing: say so rather than quietly picking 14:00
    if out["hours"] is None and part and not out["out_of_hours"]:
        out["hours"] = list(PART_HOURS[part])

    # the day: a written-out date beats kal/parso, which beats a weekday
    m = DATE_MONTH_RE.search(work)
    if m:
        day_no = int(m.group("d") or m.group("d2"))
        month = MONTH_OF[m.group("m") or m.group("m2")]
        found = _day_of_month(day_no, month, today)
        out["heard"]["day"] = take(m)
    else:
        # 15/10 before "10 ko", or "15/10 ko" reads as the 10th
        m = DATE_SLASH_RE.search(work) or DATE_WORD_RE.search(work)
        if m:
            month = int(m.group("m")) if "m" in m.groupdict() and m.group("m") else None
            found = _day_of_month(int(m.group("d")), month, today) if not month or 1 <= month <= 12 else None
            out["heard"]["day"] = take(m)
        else:
            found = None
    if m:
        if found:
            out["day"], out["day_kind"] = found, "exact"
        else:
            out["date_unclear"] = True
    else:
        next_week = NEXT_WEEK_RE.search(work)
        monday = today + timedelta(days=7 - today.weekday())
        rel = REL_RE.search(work)
        wd = WEEKDAY_RE.search(work)
        if rel:
            out["day"], out["day_kind"] = today + timedelta(days=REL_OF[rel.group(1)]), "exact"
            out["heard"]["day"] = rel.group(1)
        elif wd:
            target = WEEKDAY_OF[wd.group(1)]
            if next_week:
                out["day"] = monday + timedelta(days=target)
            else:
                out["day"] = today + timedelta(days=(target - today.weekday()) % 7 or 7)
            out["day_kind"] = "exact"
            out["heard"]["day"] = " ".join(x.group(1) for x in (next_week, wd) if x)
        elif next_week:
            out["day"], out["day_kind"] = monday, "after"
            out["heard"]["day"] = next_week.group(1)

    # "gehun 20": farmers drop the unit. one number left over, once times and
    # dates have taken theirs, is the quantity. the form shows it to correct
    if out["quantity"] is None:
        left = re.findall(B + r"(\d+(?:\.\d+)?)" + E, work)
        if len(left) == 1 and 0 < float(left[0]) <= 500:
            out["quantity"] = float(left[0])
            out["heard"]["quantity"] = left[0]

    m = CENTRE_RE.search(work)
    if m:
        out["centre"] = CENTRE_OF[m.group(1)]
        out["heard"]["centre"] = m.group(1)
    else:
        m = DISTRICT_RE.search(work)
        if m:
            out["district"] = DISTRICT_OF[m.group(1)]
            out["heard"]["centre"] = m.group(1)

    m = CROP_RE.search(work)
    if m:
        out["crop"] = CROP_OF[m.group(1)]
        out["heard"]["crop"] = m.group(1)

    if out["day"]:
        out["day"] = out["day"].isoformat()
    return out


def best_parse(candidates, today=None):
    # candidates[0] is the text box, so it wins ties
    def found(p):
        return sum(1 for f in ("crop", "day", "hours", "quantity") if p[f]) \
            + (1 if p["centre"] or p["district"] else 0) - (1 if p["date_unclear"] else 0)

    best = None
    for text in candidates:
        if not text or not text.strip():
            continue
        p = parse(text, today)
        p["text"] = text.strip()
        if best is None or found(p) > found(best):
            best = p
    return best


def window_label(start_hour):
    return "%02d:00 - %02d:00" % (start_hour, start_hour + 2)


def propose(parsed, farmer):
    # exact day+time, then same day, then same time, then anything. notes say which
    from core import ACTIVE_STATUSES, MAX_ACTIVE_BOOKINGS

    result = {"slot": None, "notes": [], "problem": None, "accepted": []}
    ph = ",".join("?" * len(ACTIVE_STATUSES))
    active = query("SELECT s.date FROM bookings b JOIN slots s ON s.id = b.slot_id"
                   " WHERE b.farmer_id = ? AND b.status IN (%s)" % ph,
                   (farmer["id"],) + ACTIVE_STATUSES)
    if len(active) >= MAX_ACTIVE_BOOKINGS:
        result["problem"] = "limit"
        return result
    busy = {r["date"] for r in active}

    centres = query("SELECT * FROM procurement_centres ORDER BY name")
    if parsed["centre"]:
        pool = [c for c in centres if c["name"] == parsed["centre"]]
    elif parsed["district"]:
        pool = [c for c in centres if c["district"] == parsed["district"]]
    else:
        pool = [c for c in centres if c["district"] == farmer["district"]] or list(centres)
        result["notes"].append("own_district")

    def accepts(c, crop):
        return crop in [x.strip() for x in c["crop_types_accepted"].split(",")]

    if parsed["crop"]:
        buying = [c for c in pool if accepts(c, parsed["crop"])]
        if not buying:
            result["problem"] = "crop_not_bought"
            result["accepted"] = sorted({x.strip() for c in pool for x in c["crop_types_accepted"].split(",")})
            return result
        pool = buying
    if not pool:
        result["problem"] = "no_centre"
        return result

    if parsed["day"] and parsed["day_kind"] == "exact" and parsed["day"] in busy:
        result["notes"].append("already_booked_that_day")

    ids = [c["id"] for c in pool]
    rows = query(
        "SELECT s.*, c.name AS centre_name, c.location, c.district AS centre_district,"
        "       c.crop_types_accepted"
        "  FROM slots s JOIN procurement_centres c ON c.id = s.centre_id"
        " WHERE s.centre_id IN (%s) AND s.date >= ? AND s.booked_count < s.max_capacity"
        " ORDER BY s.date, s.time_window, (c.district = ?) DESC, c.name" % ",".join("?" * len(ids)),
        tuple(ids) + (date.today().isoformat(), farmer["district"]))
    # today's windows that have already closed can't be turned up to
    now = datetime.now()
    today_iso = now.date().isoformat()
    rows = [r for r in rows if r["date"] not in busy
            and not (r["date"] == today_iso and int(r["time_window"][-5:-3]) <= now.hour)]

    def fits(r, keep_day, keep_time):
        if keep_day and parsed["day"]:
            if parsed["day_kind"] == "exact" and r["date"] != parsed["day"]:
                return False
            if parsed["day_kind"] == "after" and r["date"] < parsed["day"]:
                return False
        if keep_time and parsed["hours"] and int(r["time_window"][:2]) not in parsed["hours"]:
            return False
        return True

    for keep_day, keep_time in ((True, True), (True, False), (False, True), (False, False)):
        slot = next((r for r in rows if fits(r, keep_day, keep_time)), None)
        if slot:
            if not keep_day and parsed["day"]:
                result["notes"].append("other_day")
            if not keep_time and parsed["hours"]:
                result["notes"].append("other_time")
            break

    if slot is None:
        result["problem"] = "no_slot"
        return result
    result["slot"] = slot
    result["accepted"] = [x.strip() for x in slot["crop_types_accepted"].split(",")]
    return result


# ---- replies -----------------------------------------------------------------
# "no, 30 quintals" is a correction, not a no

YES = ["haan", "han", "haa", "ha", "haanji", "haan ji", "ha ji", "hanji", "ji haan", "ji", "yes", "yeah",
       "yep", "ok", "okay", "theek hai", "thik hai", "thik he", "theek he", "sahi hai", "kar do", "kardo",
       "kar dijiye", "kar dijie", "book karo", "book kar do", "bilkul", "zaroor", "jarur",
       "हां", "हा", "जी", "जी हां", "हांजी", "ठीक है", "ठीक हे", "सही है", "कर दो", "कर दीजिए", "कर दीजिये",
       "बुक करो", "बुक कर दो", "बिल्कुल", "ज़रूर", "ओके",
       "হ্যাঁ", "হ্যা", "হাঁ", "ঠিক আছে", "করুন", "করে দিন", "বুক করুন", "আচ্ছা", "hya", "hyan", "thik ache"]
NO = ["nahi", "nahin", "nai", "no", "nope", "cancel", "mat karo", "mat", "rehne do", "ruko",
      "नहीं", "नही", "मत", "मत करो", "रहने दो", "रद्द", "रुको", "कैंसिल",
      "নাহ", "বাতিল", "করবেন না", "থাক", "দরকার নেই"]
# on its own "na" is no, but "kar do na" means please do, so only as the first word
SOFT_NO = {normalise(w) for w in ("na", "naa", "ना", "না")}
YES_RE = re.compile(B + "(%s)" % _alt(YES) + E)
NO_RE = re.compile(B + "(%s)" % _alt(NO) + E)


# ---- cancelling ----------------------------------------------------------------
# only checked on the first sentence, in a reply these words just mean "no"
CANCEL = ["cancel", "cancle", "cancil", "kensal", "kainsil", "radd", "rad kar", "rad kardo", "nirast",
          "रद्द", "कैंसिल", "कैन्सिल", "निरस्त",
          "বাতিল", "ক্যানসেল", "ক্যানসিল"]
# said when they simply cannot come; the AI catches more of these than a list can
NOT_COMING = ["nahi aa paunga", "nahi aa paungi", "nahi aa sakta", "nahi aa sakti", "nahi aaunga",
              "nahi aaungi", "nahi aana", "not coming", "cant come", "नहीं आ पाऊंगा", "नहीं आ पाऊंगी",
              "नहीं आ सकता", "नहीं आ सकती", "नहीं आऊंगा", "नहीं आना", "আসতে পারব না",
              # asking for it to go away, without the word cancel
              "hata do", "hata den", "hata dijiye", "hata dijie", "booking hata", "slot hata",
              "nahi chahiye", "nai chahiye", "nahin chahiye", "band kar do",
              "हटा दो", "हटा दें", "हटा दीजिए", "नहीं चाहिए", "नही चाहिए", "बंद कर दो",
              "সরিয়ে দিন", "লাগবে না", "দরকার নেই"]
CANCEL_RE = re.compile(B + "(%s)" % _alt(CANCEL) + E)
NOT_COMING_RE = re.compile(_alt(NOT_COMING))

# which of the bookings read out. only plain ordinals: "do" in "kar do" is not a 2
ORDINALS = {"1": 1, "pehli": 1, "pehla": 1, "pahli": 1, "first": 1, "पहली": 1, "पहला": 1, "प्रथम": 1, "প্রথম": 1,
            "2": 2, "dusri": 2, "dusra": 2, "doosri": 2, "doosra": 2, "second": 2, "दूसरी": 2, "दूसरा": 2, "দ্বিতীয়": 2,
            "3": 3, "teesri": 3, "teesra": 3, "tisri": 3, "third": 3, "तीसरी": 3, "तीसरा": 3, "তৃতীয়": 3}


def wants_cancel(text):
    s = normalise(text)
    return bool(CANCEL_RE.search(s) or NOT_COMING_RE.search(s))


def which_one(text, most):
    # "dusri wali" -> 2
    for word in normalise(text).split(" "):
        n = ORDINALS.get(word)
        if n and n <= most:
            return n
    return None


def answer_kind(text):
    # no wins a tie
    s = normalise(text)
    if not s:
        return None
    if NO_RE.search(s) or s.split(" ")[0] in SOFT_NO:
        return "no"
    if YES_RE.search(s):
        return "yes"
    return None


def merge(request, reply):
    out = dict(request)
    out["heard"] = dict(request["heard"])
    if reply["crop"]:
        out["crop"] = reply["crop"]
    if reply["quantity"] is not None:
        out["quantity"] = reply["quantity"]
    if reply["centre"] or reply["district"]:
        out["centre"], out["district"] = reply["centre"], reply["district"]
    if reply["day"] or reply["date_unclear"]:
        out["day"], out["day_kind"], out["date_unclear"] = reply["day"], reply["day_kind"], reply["date_unclear"]
    if reply["hours"] or reply["out_of_hours"]:
        out["hours"], out["out_of_hours"] = reply["hours"], reply["out_of_hours"]
    out["heard"].update(reply["heard"])
    return out


# questions a farmer asks in the middle of booking, for when the AI can't be
# asked. whole phrases, so "pata nahi" (don't know) isn't taken for "address"
QUESTIONS = {
    "directions": ["kaise pahunch", "kaise pahuch", "kaise jaun", "kaise jaaun", "kaise jaye", "kaise jaaye",
                   "rasta", "raasta", "address", "kahan hai", "kaha hai", "location", "how do i reach",
                   "how to reach", "where is", "कैसे पहुंच", "कैसे पहुँच", "कैसे जाऊं", "कैसे जाएं", "रास्ता",
                   "कहां है", "कहाँ है", "पता क्या", "কীভাবে যাব", "ঠিকানা", "কোথায়"],
    "travel_time": ["kitna time", "kitna samay", "kitni der", "kitna waqt", "how long", "कितना समय",
                    "कितना टाइम", "कितनी देर", "কত সময়", "কতক্ষণ"],
    "distance": ["kitni door", "kitna door", "kitni dur", "how far", "कितनी दूर", "कितना दूर", "কত দূর"],
    "documents": ["kagaz", "kaagaz", "kya lana", "kya laana", "kya leke", "documents", "दस्तावेज", "कागज",
                  "क्या लाना", "কী আনতে", "কাগজ"],
    "timings": ["kab khul", "kitne baje khul", "kab tak khula", "opening time", "कब खुल", "कितने बजे खुल",
                "কখন খোলে"],
    "price": ["bhav", "msp", "kimat", "keemat", "daam", "भाव", "कीमत", "दाम", "দাম"],
    "payment": ["paisa kab", "paise kab", "payment kab", "bhugtan kab", "पैसा कब", "पैसे कब", "भुगतान कब",
                "টাকা কবে"],
    "weather": ["mausam", "mosam", "mausham", "barish", "baarish", "barsat", "weather", "rain", "मौसम",
                "बारिश", "बरसात", "আবহাওয়া", "বৃষ্টি"],
}
_QUESTION_PHRASES = [(normalise(p), topic) for topic, phrases in QUESTIONS.items() for p in phrases]


def question_topic(text):
    s = normalise(text)
    for phrase, topic in _QUESTION_PHRASES:
        if phrase in s:
            return topic
    return None


def fill_gaps(primary, backup):
    out = dict(primary)
    out["heard"] = dict(primary["heard"])

    def take(fields, heard_field):
        for f in fields:
            out[f] = backup[f]
        if heard_field in backup["heard"]:
            out["heard"][heard_field] = backup["heard"][heard_field]

    if out["crop"] is None and backup["crop"]:
        take(("crop",), "crop")
    if out["quantity"] is None and backup["quantity"] is not None:
        take(("quantity",), "quantity")
    if not out["centre"] and not out["district"] and (backup["centre"] or backup["district"]):
        take(("centre", "district"), "centre")
    if not out["day"] and not out["date_unclear"] and (backup["day"] or backup["date_unclear"]):
        take(("day", "day_kind", "date_unclear"), "day")
    if not out["hours"] and not out["out_of_hours"] and (backup["hours"] or backup["out_of_hours"]):
        take(("hours", "out_of_hours"), "time")
    return out


MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December"]
WINDOW_SPOKEN = {8: "8 to 10 in the morning", 10: "10 to 12 in the morning",
                 12: "12 to 2 in the afternoon", 14: "2 to 4 in the afternoon"}


def spoken_day(iso, today=None):
    d = date.fromisoformat(str(iso)[:10])
    ahead = (d - (today or date.today())).days
    name = t("Today") if ahead == 0 else t("Tomorrow") if ahead == 1 else t(d.strftime("%A"))
    return "%s, %d %s" % (name, d.day, t(MONTH_NAMES[d.month - 1]))


def spoken_window(time_window):
    start = int(str(time_window)[:2])
    return t(WINDOW_SPOKEN[start]) if start in WINDOW_SPOKEN else str(time_window)


def spoken_token(token):
    return ", ".join(" ".join(part) for part in str(token).split("-"))


def confirm_sentence(slot, crop, quantity):
    return t("%(centre)s. %(day)s, %(time)s. %(crop)s, %(qty)s quintals. Shall I book it? Say yes or no.") % {
        "centre": t(slot["centre_name"]), "day": spoken_day(slot["date"]),
        "time": spoken_window(slot["time_window"]), "crop": t(crop), "qty": "%g" % quantity}
