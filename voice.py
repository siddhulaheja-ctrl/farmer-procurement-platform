"""Outbound calls, we ring the farmer.

Vonage takes the whole message in the api request (inline ncco) so it never
calls back to us. That means no webhook and no server anywhere, it all runs
from here.

Staff screens ring the farmer's own number if it is a real one. The seeded
farmers have made up numbers so those go to DEMO_NUMBER instead. Running this
file directly dials whatever you type.

    python voice.py 9876543210 "Namaste, test" hi

Env vars, all optional:
    VOICE_DEMO_NUMBER   where the staff Call buttons ring
    VOICE_DRY_RUN=1     log instead of dialling
    VOICE_LEVEL         volume -1 to 1, default 1 (0 was too quiet)
    VOICE_LEAD_IN       seconds of silence first, default 2
    VOICE_RATE          speech rate, default slow
    VOICE_TOKEN_RATE    rate for the token, default x-slow
    VOICE_PREMIUM=1     better voice, costs more
    VONAGE_NUMBER       caller id, otherwise vonage picks a random US one
    VONAGE_APPLICATION_ID / VONAGE_PRIVATE_KEY / VONAGE_PRIVATE_KEY_PATH
"""

import os
import sys
from datetime import datetime

import env

env.load()

HERE = os.path.dirname(os.path.abspath(__file__))

# our app from the vonage dashboard
APP_ID = os.environ.get("VONAGE_APPLICATION_ID",
                        "fb926ccb-0da7-4d10-814f-9a3ae05428e3").strip()
# vonage wants this filled in even though it swaps in its own number
FROM_NUMBER = os.environ.get("VONAGE_NUMBER", "").strip() or "12345678901"
# every call from the ui lands here for now
DEMO_NUMBER = os.environ.get("VOICE_DEMO_NUMBER", "9876543210").strip()
KEY_PATH = os.environ.get("VONAGE_PRIVATE_KEY_PATH",
                          os.path.join(HERE, "farmer-ivr", "private.key"))

VOICE = {"en": "en-IN", "hi": "hi-IN"}

# talk has a volume setting but no speed one, so pacing comes from ssml
def _level():
    # a typo in the env var used to kill the whole app on startup
    try:
        v = float(os.environ.get("VOICE_LEVEL", "1"))
    except ValueError:
        return 1.0
    return max(-1.0, min(1.0, v))       # outside -1..1 vonage just rejects it


LEVEL = _level()
LEAD_IN = os.environ.get("VOICE_LEAD_IN", "2")
RATE = os.environ.get("VOICE_RATE", "slow")
TOKEN_RATE = os.environ.get("VOICE_TOKEN_RATE", "x-slow")
PREMIUM = os.environ.get("VOICE_PREMIUM", "").strip() in ("1", "true", "yes")


MONTHS_HI = ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई",
             "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]


def spoken_date(iso):
    """2026-09-14 -> '14 सितंबर'. Reading the raw date out loud sounds awful."""
    try:
        _y, m, d = str(iso)[:10].split("-")
        return "%d %s" % (int(d), MONTHS_HI[int(m) - 1])
    except Exception:
        return str(iso)


def spell_token(token):
    """Spaced out and slowed down, people write this down off the call."""
    if not token:
        return ""
    groups = [" ".join(part) for part in str(token).split("-")]
    spaced = ' <break time="400ms"/> '.join(groups)
    return '<prosody rate="%s">%s</prosody>' % (TOKEN_RATE, spaced)


def _escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def to_ssml(message, token=None):
    """Build the ssml. Escape first, then add our tags, otherwise a farmer
    called "A & B" breaks the xml. {{token}} is where the token goes."""
    body = _escape(message)
    if token:
        body = body.replace("{{token}}", spell_token(token))
    else:
        body = body.replace("{{token}}", "")
    return ('<speak><break time="%ss"/><prosody rate="%s">%s</prosody></speak>'
            % (LEAD_IN, RATE, body))


def plain(message, token=None):
    """Same thing without the tags, for the screen and the log."""
    text = str(message)
    if token:
        text = text.replace("{{token}}", ", ".join(" ".join(p)
                                                   for p in str(token).split("-")))
    return text.replace("{{token}}", "")


# the seeded demo farmers all have numbers in this block, see seed.py
PLACEHOLDER_PREFIX = "900000"


def target_for(phone):
    """Who do we actually ring. Seeded farmers have made up numbers so those
    go to the team phone, but anyone who registered with a real number gets
    rung on it. Returns (number, was_redirected)."""
    number = to_e164(phone)
    local = number[2:] if number.startswith("91") else number
    if not local or local.startswith(PLACEHOLDER_PREFIX):
        return to_e164(DEMO_NUMBER), True
    return number, False


def to_e164(phone):
    digits = "".join(c for c in str(phone or "") if c.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    return digits


def _private_key():
    key = os.environ.get("VONAGE_PRIVATE_KEY")
    if key:
        return key
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH) as f:
            return f.read()
    return None


def status():
    """What is set up, so the screens can say whether calls are real."""
    missing = []
    if not APP_ID:
        missing.append("VONAGE_APPLICATION_ID")
    if not _private_key():
        missing.append("a private key")
    forced = os.environ.get("VOICE_DRY_RUN", "").strip() in ("1", "true", "yes")
    return {"credentials_ok": not missing, "missing": missing,
            "demo_number": DEMO_NUMBER, "forced_dry_run": forced,
            "dry_run": forced or bool(missing),
            "from_number": FROM_NUMBER, "key_path": KEY_PATH}


def place_call(phone, message, lang="hi", token=None):
    """Ring the number and read out the message.

    Put {{token}} in the message and pass token= to have it read slowly.
    Returns (ok, detail) and never raises - a failed call should show up as a
    message, not a 500 in the middle of a demo.
    """
    number = to_e164(phone)
    if not number:
        return False, "No phone number on that record."

    st = status()
    if st["forced_dry_run"]:
        reason = "VOICE_DRY_RUN is set"
    elif st["missing"]:
        reason = "missing " + ", ".join(st["missing"])
    else:
        reason = None

    spoken = plain(message, token)
    if reason:
        print("[voice] DRY RUN (%s) -> +%s / %s\n         %s"
              % (reason, number, VOICE.get(lang, "hi-IN"), spoken))
        return True, "Dry run (%s). Would have said: %s" % (reason, spoken)

    try:
        from vonage import Auth, Vonage
        from vonage_voice import CreateCallRequest, Phone, Talk, ToPhone

        client = Vonage(Auth(application_id=APP_ID, private_key=_private_key()))
        response = client.voice.create_call(CreateCallRequest(
            to=[ToPhone(number=number)],
            from_=Phone(number=FROM_NUMBER),
            ncco=[Talk(text=to_ssml(message, token),
                       language=VOICE.get(lang, "hi-IN"),
                       level=LEVEL, premium=PREMIUM or None)],
        ))
        return True, "Calling +%s now. %s" % (number, response)
    except Exception as e:
        return False, "Vonage refused the call: %s" % e


def log_call(farmer_id, message, ok, detail, booking_id=None):
    """Keep a record on the alerts page of what we rang about."""
    from alerts import raise_alert
    prefix = "Call placed" if ok else "Call failed"
    raise_alert(farmer_id, "voice_call", "ivr",
                "%s at %s. %s" % (prefix, datetime.now().strftime("%H:%M"), detail),
                booking_id=booking_id)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print("current config:", status())
        sys.exit(1)
    ok, detail = place_call(sys.argv[1],
                            sys.argv[2] if len(sys.argv) > 2 else
                            "Namaste. This is a test call from Krishi Sutra.",
                            sys.argv[3] if len(sys.argv) > 3 else "en")
    print(("OK: " if ok else "FAILED: ") + detail)
