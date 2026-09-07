"""Outbound calls through Vonage.

We only do outbound for now - the portal rings the farmer. Farmers ringing us
needs a number we can publish, so that is parked (see farmer-ivr/).

The nice thing about outbound is that we send the whole message in the api
request as an inline NCCO, so vonage never calls us back. No webhook, no public
url, no server on render. Everything runs on localhost.

Every call from the staff screens goes to DEMO_NUMBER, not to the farmer's own
number. The seeded farmers are fake, so there is nobody real to ring, and it
means a stray click can never dial a stranger. Running this file from the
command line dials whatever number you type.

Config, all optional:
    VOICE_DEMO_NUMBER        where the staff Call buttons ring. Defaults to the
                             team phone we test with.
    VONAGE_APPLICATION_ID    from the vonage dashboard
    VONAGE_NUMBER            caller id. If unset vonage picks one of its own,
                             which is why test calls show up as a US number.
    VONAGE_PRIVATE_KEY       the key itself (for hosting), or
    VONAGE_PRIVATE_KEY_PATH  path to private.key (defaults to farmer-ivr/)
    VOICE_DRY_RUN=1          never dial, whatever else is set
    VOICE_LEVEL              volume, -1 to 1. Default 1, the loudest vonage
                             allows, because the default was too quiet.
    VOICE_LEAD_IN            seconds of silence before speaking, so the farmer
                             has time to get the phone to their ear. Default 2.
    VOICE_RATE               overall speech rate. Default slow.
    VOICE_TOKEN_RATE         rate for the token number, which people write
                             down. Default x-slow.
    VOICE_PREMIUM=1          use vonage's premium (neural) voice. Sounds much
                             better, costs more per call.

Quick test from the command line - a number typed here is dialled straight
away, the allowlist only guards the buttons in the web ui:
    python voice.py 9876543210 "Namaste, this is a test" hi
"""

import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))

# defaults to the application we already made in the vonage dashboard, so the
# only thing that normally needs setting is the allowlist
APP_ID = os.environ.get("VONAGE_APPLICATION_ID",
                        "fb926ccb-0da7-4d10-814f-9a3ae05428e3").strip()
# vonage wants the field populated even when it substitutes its own caller id
FROM_NUMBER = os.environ.get("VONAGE_NUMBER", "").strip() or "12345678901"
# Calls from the staff screens always land here while we are testing.
DEMO_NUMBER = os.environ.get("VOICE_DEMO_NUMBER", "9876543210").strip()
KEY_PATH = os.environ.get("VONAGE_PRIVATE_KEY_PATH",
                          os.path.join(HERE, "farmer-ivr", "private.key"))

VOICE = {"en": "en-IN", "hi": "hi-IN"}

# Vonage's talk action has a volume knob but no speed one, so the pacing has to
# come from SSML in the text itself.
LEVEL = float(os.environ.get("VOICE_LEVEL", "1"))
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
    """PC01-S017-001 -> the digits spaced out, read extra slowly, with a pause
    between the groups. People write this number down off the call."""
    groups = [" ".join(part) for part in str(token or "").split("-")]
    spaced = ' <break time="400ms"/> '.join(groups)
    return '<prosody rate="%s">%s</prosody>' % (TOKEN_RATE, spaced)


def _escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def to_ssml(message, token=None):
    """Wrap the message for the text to speech engine.

    Escapes the text first and only then puts our own tags in, so a farmer
    called "A & B" can't break the markup. {{token}} in the message is where
    the slowed down token number goes.
    """
    body = _escape(message)
    if token:
        body = body.replace("{{token}}", spell_token(token))
    else:
        body = body.replace("{{token}}", "")
    return ('<speak><break time="%ss"/><prosody rate="%s">%s</prosody></speak>'
            % (LEAD_IN, RATE, body))


def plain(message, token=None):
    """The same message without markup, for logging and the screen."""
    text = str(message)
    if token:
        text = text.replace("{{token}}", ", ".join(" ".join(p)
                                                   for p in str(token).split("-")))
    return text.replace("{{token}}", "")


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
    """What's configured, so the demo page can be honest about it."""
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
    """Ring `phone` and read out `message`.

    Put {{token}} in the message where the token number should go and pass it
    as `token`, so it gets read slowly enough to write down.

    Returns (ok, detail). Never raises - a failed call belongs on the screen,
    not as a 500 in the middle of a demo.
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
    """Record what happened so there is a trail on the alerts page.
    alert_type voice_call is filtered out of the dial queue in app.py."""
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
