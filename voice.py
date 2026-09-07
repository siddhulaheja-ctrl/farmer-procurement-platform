"""Outbound calls through Vonage.

We only do outbound for now - the portal rings the farmer. Farmers ringing us
needs a number we can publish, so that is parked (see farmer-ivr/).

The nice thing about outbound is that we send the whole message in the api
request as an inline NCCO, so vonage never calls us back. No webhook, no public
url, no server on render. Everything runs on localhost.

IMPORTANT: the seeded farmers have Faker generated phone numbers that look like
real indian mobiles, because that is what Faker does. So the Call now buttons
in the web ui only really dial numbers listed in VOICE_ALLOWLIST - otherwise
one stray click during a demo cold calls a stranger. Running this file from the
command line ignores the allowlist, because you typed the number yourself.

Config, all optional:
    VOICE_ALLOWLIST          comma separated numbers allowed to be really rung.
                             Empty (the default) means nothing is really rung.
    VONAGE_APPLICATION_ID    from the vonage dashboard
    VONAGE_NUMBER            caller id. If unset vonage picks one of its own,
                             which is why test calls show up as a US number.
    VONAGE_PRIVATE_KEY       the key itself (for hosting), or
    VONAGE_PRIVATE_KEY_PATH  path to private.key (defaults to farmer-ivr/)
    VOICE_DRY_RUN=1          never dial, whatever else is set

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
KEY_PATH = os.environ.get("VONAGE_PRIVATE_KEY_PATH",
                          os.path.join(HERE, "farmer-ivr", "private.key"))

VOICE = {"en": "en-IN", "hi": "hi-IN"}


def to_e164(phone):
    digits = "".join(c for c in str(phone or "") if c.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    return digits


def _allowlist():
    raw = os.environ.get("VOICE_ALLOWLIST", "")
    return {to_e164(n) for n in raw.replace(";", ",").split(",") if n.strip()}


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
    allow = _allowlist()
    forced = os.environ.get("VOICE_DRY_RUN", "").strip() in ("1", "true", "yes")
    return {"credentials_ok": not missing, "missing": missing,
            "allowlist": sorted(allow), "forced_dry_run": forced,
            "dry_run": forced or bool(missing) or not allow,
            "from_number": FROM_NUMBER, "key_path": KEY_PATH}


def place_call(phone, message, lang="hi", explicit=False):
    """Ring the farmer and read out `message`.

    explicit=True means a human typed this number on the command line, so we
    skip the allowlist. The allowlist is there to stop a stray click in the web
    ui dialling one of the seeded strangers, not to get in the way of testing.

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
    elif not explicit and number not in st["allowlist"]:
        reason = ("+%s is not in VOICE_ALLOWLIST" % number)
    else:
        reason = None

    if reason:
        print("[voice] DRY RUN (%s) -> +%s / %s\n         %s"
              % (reason, number, VOICE.get(lang, "hi-IN"), message))
        return True, "Dry run (%s). Would have said: %s" % (reason, message)

    try:
        from vonage import Auth, Vonage
        from vonage_voice import CreateCallRequest, Phone, Talk, ToPhone

        client = Vonage(Auth(application_id=APP_ID, private_key=_private_key()))
        response = client.voice.create_call(CreateCallRequest(
            to=[ToPhone(number=number)],
            from_=Phone(number=FROM_NUMBER),
            ncco=[Talk(text=message, language=VOICE.get(lang, "hi-IN"))],
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
                            sys.argv[3] if len(sys.argv) > 3 else "en",
                            explicit=True)
    print(("OK: " if ok else "FAILED: ") + detail)
