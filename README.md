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
| `VOICE_PREMIUM` | off | Vonage's neural voice. Much less robotic, costs more per call |
| `VOICE_STYLE` | unset | Which Hindi voice. 0, 1, 3, 4, 5, 6 exist; premium works on all but 0 |

The token is spelled out digit by digit with a pause between the groups, and
the slot reminder reads it twice.

To pick a voice, ring yourself once and listen to all of them:

```bash
python voice.py --voices 9876543210
```

That reads the same line in every Hindi voice, announcing each style number
first. Put the one you like in `.env` as `VOICE_STYLE`, with `VOICE_PREMIUM=1`.

Real IVRs like the gas booking line mostly play **recorded human audio** for
the fixed sentences and only use text to speech for the changing numbers.
Vonage can do that too with the `stream` NCCO action pointing at an mp3, which
is the route if premium still is not good enough.

Farmers ringing *us* is parked until we have a number to publish. The half
built menu is in `farmer-ivr/`.

## Local settings

Put keys and settings in a `.env` file in this folder, which is gitignored.
Saves fighting with environment variable syntax, which is different in
powershell, cmd and bash.

```
OWM_API_KEY=your_openweathermap_key
VOICE_DEMO_NUMBER=9876543210
DEMO_FARMER_PHONE_1=  team phone, seeded as Chandra Bhushan Kumar
DEMO_FARMER_PHONE_2=  team phone, seeded as Ravi Kumar
```

The team phone numbers are real people's, so they stay out of git. Without them
the seeder uses placeholders and those calls go to `VOICE_DEMO_NUMBER` instead.
Whichever numbers you use have to be verified in the Vonage dashboard first,
trial accounts refuse anything else.

Anything already set in the real environment still wins, so you can override
one value for a single run.

## Demo data

The farmer table is currently **empty**. We cleared out the fifty random seeded
farmers and are rebuilding with a small set of realistic Uttarakhand cases.

`python seed.py` gives you the scaffolding only:

- 5 procurement centres, all Uttarakhand (Rudrapur, Kichha, Haridwar,
  Vikasnagar, Haldwani)
- their slots, 3 days back and 14 days forward
- one staff login, `ADMIN` / `demo123`

Farmers are added through the portal, either self registration or
**Register Farmer** on the staff side.

The team phone numbers verified with Vonage are kept in `.env` so they are not
lost while the table is empty:

```
DEMO_FARMER_PHONE_1=   Chandra Bhushan Kumar
DEMO_FARMER_PHONE_2=   Ravi Kumar
```

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
| `VOICE_PREMIUM` | off | Vonage's neural voice. Much less robotic, costs more per call |
| `VOICE_STYLE` | unset | Which Hindi voice. 0, 1, 3, 4, 5, 6 exist; premium works on all but 0 |

The token is spelled out digit by digit with a pause between the groups, and
the slot reminder reads it twice.

To pick a voice, ring yourself once and listen to all of them:

```bash
python voice.py --voices 9876543210
```

That reads the same line in every Hindi voice, announcing each style number
first. Put the one you like in `.env` as `VOICE_STYLE`, with `VOICE_PREMIUM=1`.

Real IVRs like the gas booking line mostly play **recorded human audio** for
the fixed sentences and only use text to speech for the changing numbers.
Vonage can do that too with the `stream` NCCO action pointing at an mp3, which
is the route if premium still is not good enough.

Farmers ringing *us* is parked until we have a number to publish. The half
built menu is in `farmer-ivr/`.

## Local settings

Put keys and settings in a `.env` file in this folder, which is gitignored.
Saves fighting with environment variable syntax, which is different in
powershell, cmd and bash.

```
OWM_API_KEY=your_openweathermap_key
VOICE_DEMO_NUMBER=9876543210
DEMO_FARMER_PHONE_1=  team phone, seeded as Chandra Bhushan Kumar
DEMO_FARMER_PHONE_2=  team phone, seeded as Ravi Kumar
```

The team phone numbers are real people's, so they stay out of git. Without them
the seeder uses placeholders and those calls go to `VOICE_DEMO_NUMBER` instead.
Whichever numbers you use have to be verified in the Vonage dashboard first,
trial accounts refuse anything else.

Anything already set in the real environment still wins, so you can override
one value for a single run.

## Demo data

Most seeded farmers have a number in the `90000001xx` block. They are fake on
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
