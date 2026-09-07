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

We ring the farmer. There is a **Call farmer** button on each booking in the
staff screens, and a **Call** button on the high risk rows of the Storage Risk
page. What gets said depends on the booking - a storage risk warning, a held
payment, or a plain slot reminder.

Farmers who registered with a real number are rung on it, so anyone on the team
who signs up gets their own call. The seeded demo farmers have made up numbers
(the `9000000xxx` block), so those calls go to `VOICE_DEMO_NUMBER` instead.

Note that Vonage trial accounts only call numbers verified in the dashboard, so
add each teammate's number there first or the call fails.

Testing straight from the command line, dials whatever you type:

```bash
python voice.py 9876543210 "Namaste, test call" hi
```

`voice.py` sends the whole spoken message inline with the Vonage request, so
there is no webhook and no second server. The private key is read from
`farmer-ivr/private.key` and is never committed. `VONAGE_NUMBER` is optional -
without it Vonage picks its own caller id, which is why test calls arrive from
a US number.

Set `VOICE_DRY_RUN=1` to print what would be said instead of dialling. Do that
before testing anything that isn't the call itself, or you will ring the phone
by accident.

### Voice tuning

Vonage's talk action has a volume setting but no speed one, so the pacing comes
from SSML we build in `to_ssml()`.

| Variable | Default | What it does |
|---|---|---|
| `VOICE_LEVEL` | 1 | Volume, -1 to 1. 1 is the loudest Vonage allows |
| `VOICE_LEAD_IN` | 2 | Seconds of silence before speaking, so the farmer can get the phone to their ear |
| `VOICE_RATE` | slow | Overall speech rate |
| `VOICE_TOKEN_RATE` | x-slow | Rate for the token number, which people write down |
| `VOICE_PREMIUM` | off | Vonage's neural voice. Sounds much better, costs more per call |

The token is spelled out digit by digit with a pause between the groups, and
the slot reminder reads it twice.

Farmers ringing *us* is parked until we have a number to publish. The half
built menu is in `farmer-ivr/`.

## Local settings

Put keys and settings in a `.env` file in this folder, which is gitignored.
Saves fighting with environment variable syntax, which is different in
powershell, cmd and bash.

```
OWM_API_KEY=your_openweathermap_key
VOICE_DEMO_NUMBER=9876543210
```

Anything already set in the real environment still wins, so you can override
one value for a single run.

## Demo data

Every seeded farmer has a number in the `90000001xx` block. They are fake on
purpose - Faker generates numbers that look real and could belong to an actual
person, which is a bad idea in something that can place calls.

`STORAGE_RISK_FORCE=1` makes every booking come back as high storage risk, for
when the forecast is dry and we still need to show the alert.

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

Quick test, dials straight away:

```bash
python voice.py 9876543210 "Namaste, test call" hi
```


The private key is read from `farmer-ivr/private.key` and is never committed.
`VONAGE_NUMBER` is optional - without it Vonage picks its own caller id, which
is why test calls arrive from a US number.

Farmers ringing *us* is parked until we have a number to publish. The half
built menu is in `farmer-ivr/`.

Aadhaar, bank and land details are all fake, nothing talks to a real
government API. Payment status is just a field we update.

Photos on the home page are from Wikimedia Commons and are CC BY-SA, credits
are in the footer and in static/img/credits.json.
