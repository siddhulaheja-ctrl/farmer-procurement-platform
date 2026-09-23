"""Village list per district, so village is picked not typed.
TODO: use the LGD village directory
"""

import difflib
import re

VILLAGES = {
    "Udham Singh Nagar": ["Bazpur", "Dineshpur", "Gadarpur", "Jaspur", "Kashipur", "Khatima", "Kichha",
                          "Nanakmatta", "Pantnagar", "Rudrapur", "Shaktigarh", "Sitarganj"],
    "Haridwar": ["Bahadrabad", "Bhagwanpur", "Jhabrera", "Jwalapur", "Khanpur", "Laksar", "Manglaur",
                 "Narsan", "Pathri", "Roorkee"],
    "Dehradun": ["Dhakrani", "Doiwala", "Herbertpur", "Kalsi", "Premnagar", "Raipur", "Rishikesh",
                 "Sahaspur", "Selaqui", "Vikasnagar"],
    "Nainital": ["Betalghat", "Bhimtal", "Bhowali", "Haldwani", "Kaladhungi", "Kathgodam", "Kotabagh",
                 "Lalkuan", "Mehragaon", "Ramnagar"],
}

# also used by i18n.py
NAMES = {
    "hi": {
        "Bazpur": "बाजपुर", "Dineshpur": "दिनेशपुर", "Gadarpur": "गदरपुर", "Jaspur": "जसपुर",
        "Kashipur": "काशीपुर", "Khatima": "खटीमा", "Kichha": "किच्छा", "Nanakmatta": "नानकमत्ता",
        "Pantnagar": "पंतनगर", "Rudrapur": "रुद्रपुर", "Shaktigarh": "शक्तिगढ़", "Sitarganj": "सितारगंज",
        "Bahadrabad": "बहादराबाद", "Bhagwanpur": "भगवानपुर", "Jhabrera": "झबरेड़ा", "Jwalapur": "ज्वालापुर",
        "Khanpur": "खानपुर", "Laksar": "लक्सर", "Manglaur": "मंगलौर", "Narsan": "नारसन", "Pathri": "पथरी",
        "Roorkee": "रुड़की",
        "Dhakrani": "ढकरानी", "Doiwala": "डोईवाला", "Herbertpur": "हर्बर्टपुर", "Kalsi": "कालसी",
        "Premnagar": "प्रेमनगर", "Raipur": "रायपुर", "Rishikesh": "ऋषिकेश", "Sahaspur": "सहसपुर",
        "Selaqui": "सेलाकुई", "Vikasnagar": "विकासनगर",
        "Betalghat": "बेतालघाट", "Bhimtal": "भीमताल", "Bhowali": "भवाली", "Haldwani": "हल्द्वानी",
        "Kaladhungi": "कालाढूंगी", "Kathgodam": "काठगोदाम", "Kotabagh": "कोटाबाग", "Lalkuan": "लालकुआं",
        "Mehragaon": "मेहरागांव", "Ramnagar": "रामनगर",
    },
    "bn": {
        "Bazpur": "বাজপুর", "Dineshpur": "দীনেশপুর", "Gadarpur": "গদরপুর", "Jaspur": "জসপুর",
        "Kashipur": "কাশীপুর", "Khatima": "খাটিমা", "Kichha": "কিচ্ছা", "Nanakmatta": "নানকমাত্তা",
        "Pantnagar": "পন্তনগর", "Rudrapur": "রুদ্রপুর", "Shaktigarh": "শক্তিগড়", "Sitarganj": "সিতারগঞ্জ",
        "Bahadrabad": "বাহাদরাবাদ", "Bhagwanpur": "ভগবানপুর", "Jhabrera": "ঝাবরেড়া", "Jwalapur": "জ্বালাপুর",
        "Khanpur": "খানপুর", "Laksar": "লক্সর", "Manglaur": "মঙ্গলৌর", "Narsan": "নারসন", "Pathri": "পাথরি",
        "Roorkee": "রুড়কি",
        "Dhakrani": "ঢাকরানি", "Doiwala": "ডোইওয়ালা", "Herbertpur": "হার্বার্টপুর", "Kalsi": "কালসি",
        "Premnagar": "প্রেমনগর", "Raipur": "রায়পুর", "Rishikesh": "ঋষিকেশ", "Sahaspur": "সহসপুর",
        "Selaqui": "সেলাকুই", "Vikasnagar": "বিকাশনগর",
        "Betalghat": "বেতালঘাট", "Bhimtal": "ভীমতাল", "Bhowali": "ভাওয়ালি", "Haldwani": "হলদোয়ানি",
        "Kaladhungi": "কালাঢুঙ্গি", "Kathgodam": "কাঠগোদাম", "Kotabagh": "কোটাবাগ", "Lalkuan": "লালকুয়াঁ",
        "Mehragaon": "মেহরাগাঁও", "Ramnagar": "রামনগর",
    },
}


def names(district=None):
    if district:
        return list(VILLAGES.get(district, []))
    return [v for vs in VILLAGES.values() for v in vs]


def valid(district, village):
    return bool(village) and village in VILLAGES.get(district, [])


def _key(text):
    return re.sub(r"[^a-z]", "", (text or "").lower())


def match(district, text):
    # fuzzy, speech recognition spells places all sorts of ways
    raw = str(text or "").strip()
    if not raw:
        return ""
    choices = names(district)

    for village in choices:
        for table in NAMES.values():
            local = table.get(village)
            if local and local in raw:
                return village

    low = raw.lower()
    for village in sorted(choices, key=len, reverse=True):
        if re.search(r"(?<![a-z])" + re.escape(village.lower()) + r"(?![a-z])", low):
            return village

    keys = {_key(v): v for v in choices}
    words = re.findall(r"[a-z]+", low)
    for candidate in [_key(raw)] + words + [a + b for a, b in zip(words, words[1:])]:
        if len(candidate) >= 4:
            close = difflib.get_close_matches(candidate, list(keys), n=1, cutoff=0.75)
            if close:
                return keys[close[0]]

    local = {}
    for village in choices:
        for table in NAMES.values():
            if table.get(village):
                local[table[village]] = village
    for token in raw.split():
        close = difflib.get_close_matches(token, list(local), n=1, cutoff=0.75)
        if close:
            return local[close[0]]
    return ""
