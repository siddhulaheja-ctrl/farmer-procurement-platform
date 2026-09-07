# Krishi Sutra

Slot booking system for government crop procurement centres.
Farmer pages work in Hindi and English.
SIH 2026, problem statement 26032.

## Setup

Needs Python 3.9 or newer.

```bash
pip install -r requirements.txt
```

Then on Windows just double click `start_demo.bat`.

On mac/linux:

```bash
./start_demo.sh
```

Or do it manually:

```bash
python seed.py
python app.py
```

Open http://localhost:5000

`seed.py` wipes the database and fills it with fake data again. Run it before
the presentation so everything is back to normal.

### mac note

macOS uses port 5000 for AirPlay so flask can't start on it. `start_demo.sh`
moves to 5001 by itself. If you run it manually use `PORT=5001 python app.py`.

## Logins

OTP is always `123456`.

| who | login |
|---|---|
| farmer (clean record) | 9000000001 |
| farmer (has data problems) | 9000000002 |
| staff, all centres | ADMIN / demo123 |
| staff, one centre | STAFF01 / demo123 |

## Sharing the demo

`share_demo.bat` (or `./share_demo.sh`) puts it on a public link using
cloudflared, which you need to install first:

```bash
winget install Cloudflare.cloudflared
```

The link only works while that window is open and changes every time.

There is no real login security, so anyone with the link can sign in as
anyone. Data is all fake so it doesn't matter, just re-run the seed after.

## Files

| file | what it does |
|---|---|
| app.py | routes |
| core.py | booking rules, capacity and the per farmer limits |
| validation.py | aadhaar / bank / land checks |
| weather.py | storage risk from the weather forecast |
| alerts.py | writes to alerts_log |
| db.py | sqlite helpers |
| schema.sql | tables |
| seed.py | fake data |
| i18n.py | hindi strings for the farmer pages |

## Phone calls

We ring the farmer. Storage risk warnings, booking confirmations and payment
updates are queued in `alerts_log` with channel `ivr`, and show up on the demo
page with a "Call now" button.

`voice.py` sends the whole spoken message inline with the Vonage request, so
there is no webhook and no second server. Everything runs on localhost.

To place real calls set `VONAGE_NUMBER` to our virtual number. Without it the
portal runs in dry run and shows exactly what it would have said, which is
useful for practising the demo without spending credit. The private key is read
from `farmer-ivr/private.key` and is never committed.

Farmers ringing *us* is parked until we have a number to publish. The half
built menu is in `farmer-ivr/`.

Aadhaar, bank and land details are all fake, nothing talks to a real
government API. Payment status is just a field we update.

Photos on the home page are from Wikimedia Commons and are CC BY-SA, credits
are in the footer and in static/img/credits.json.
