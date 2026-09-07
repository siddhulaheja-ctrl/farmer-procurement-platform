"""Outbound calls through Vonage.

We only do outbound for now - the portal rings the farmer. Farmers ringing us
needs a number we can publish, so that is parked (see farmer-ivr/).

The nice thing about outbound is that we send the whole message in the api
request as an inline NCCO, so vonage never calls us back. No webhook, no public
url, no server on render. Everything runs on localhost.

Config, all optional:
    VONAGE_APPLICATION_ID    from the vonage dashboard
    VONAGE_NUMBER            our virtual number, used as the caller id
    VONAGE_PRIVATE_KEY       the key itself (for hosting), or
    VONAGE_PRIVATE_KEY_PATH  path to private.key (defaults to farmer-ivr/)
    VOICE_DRY_RUN=1          pretend to dial, log instead. Turns itself on
                             automatically when credentials are missing.
"""

import os
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))

# defaults to the application we already made in the vonage dashboard, so the
# only thing that normally needs setting is the number
APP_ID = os.environ.get("VONAGE_APPLICATION_ID",
                        "fb926ccb-0da7-4d10-814f-9a3ae05428e3").strip()
FROM_NUMBER = os.environ.get("VONAGE_NUMBER", "").strip()
KEY_PATH = os.environ.get("VONAGE_PRIVATE_KEY_PATH",
                          os.path.join(HERE, "farmer-ivr", "private.key"))

VOICE = {"en": "en-IN", "hi": "hi-IN"}


def _private_key():
    key = os.environ.get("VONAGE_PRIVATE_KEY")
    if key:
        return key
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH) as f:
            return f.read()
    return None


def status():
    """What's configured, so the demo page can show it honestly."""
    key = _private_key()
    missing = []
    if not APP_ID:
        missing.append("VONAGE_APPLICATION_ID")
    if not FROM_NUMBER:
        missing.append("VONAGE_NUMBER")
    if not key:
        missing.append("a private key")
    forced = os.environ.get("VOICE_DRY_RUN", "").strip() in ("1", "true", "yes")
    return {"ready": not missing, "missing": missing,
            "dry_run": forced or bool(missing),
            "forced_dry_run": forced,
            "from_number": FROM_NUMBER, "key_path": KEY_PATH}


def to_e164(phone):
    digits = "".join(c for c in str(phone or "") if c.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    return digits


def place_call(phone, message, lang="hi"):
    """Ring the farmer and read out `message`.

    Returns (ok, detail). Never raises - a failed call should show up as a
    message on the screen, not a 500 in the middle of a demo.
    """
    st = status()
    number = to_e164(phone)
    if not number:
        return False, "No phone number on that record."

    if st["dry_run"]:
        why = ("VOICE_DRY_RUN is set" if st["forced_dry_run"]
               else "not configured yet: missing " + ", ".join(st["missing"]))
        print("[voice] DRY RUN (%s) -> would call +%s in %s:\n         %s"
              % (why, number, VOICE.get(lang, "hi-IN"), message))
        return True, ("Dry run (%s). Would have called +%s and said: %s" % (why, number, message))

    try:
        from vonage import Auth, Vonage
        from vonage_voice import CreateCallRequest, Phone, Talk, ToPhone

        client = Vonage(Auth(application_id=APP_ID, private_key=_private_key()))
        response = client.voice.create_call(CreateCallRequest(
            to=[ToPhone(number=number)],
            from_=Phone(number=FROM_NUMBER),
            ncco=[Talk(text=message, language=VOICE.get(lang, "hi-IN"))],
        ))
        return True, "Calling +%s now (%s)" % (number, response)
    except Exception as e:
        return False, "Vonage refused the call: %s" % e


def log_call(farmer_id, message, ok, detail, booking_id=None):
    """Record what happened so there is a trail on the alerts page."""
    from alerts import raise_alert
    prefix = "Call placed" if ok else "Call failed"
    raise_alert(farmer_id, "voice_call", "ivr",
                "%s at %s. %s" % (prefix, datetime.now().strftime("%H:%M"), detail),
                booking_id=booking_id)
