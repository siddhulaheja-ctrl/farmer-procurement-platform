# Krishi Sutra

Slot booking system for government crop procurement centres.
Works in Hindi, English and Bengali.
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

Or just `python app.py`.

`procurement.db` isn't in git (real phone numbers and passwords), so copy it
into this folder first. `schema.sql` has the tables if you ever need an empty one.

Open http://localhost:5000

### mac note

macOS uses port 5000 for AirPlay so flask can't start on it. `start_demo.sh`
moves to 5001 by itself. If you run it manually use `PORT=5001 python app.py`.

## Logins

Farmers sign in with their mobile number, the OTP is always `123456` for now.

Members sign in at `/admin/login` (centre staff, e.g. `RUD01`) and the district
superadmin at `/super/login` (`ADMIN`). Passwords are changed from the
superadmin's Staff page. The login pages only show one-click demo buttons for
an account still on `demo123`.

## Local settings

Keys and settings go in a `.env` file in this folder (gitignored), see
`.env.example`. Real environment variables win over it.

```
OWM_API_KEY=            # live weather, otherwise a mock forecast
GEMINI_API_KEY=         # voice booking + help chat, otherwise the offline parser / FAQ
VOICE_DEMO_NUMBER=      # where calls to made up 900000xxxx numbers go
```

`STORAGE_RISK_FORCE=1` makes every booking high storage risk, for when the
forecast is dry and we still need to show the alert.

## Sharing the demo

`share_demo.bat` (or `./share_demo.sh`) puts it on a public link using
cloudflared, which you need to install first:

```bash
winget install Cloudflare.cloudflared
```

The link only works while that window is open and changes every time. The QR
on a gate pass has the address the page was opened from, so scan it from the
shared link, a phone can't open `localhost`.

## Phone calls

There is a **Call farmer** button on each booking in the member screens, and a
**Call** button on the high risk rows of the Storage Risk page. What gets said
depends on the booking - storage risk warning, held payment, or slot reminder.

Real numbers get rung directly. Made up `900000xxxx` numbers go to
`VOICE_DEMO_NUMBER`. Vonage trial accounts only call numbers verified in the
dashboard, so add each teammate's number there first. Real calls stop at
`CALLS_PER_DAY` (default 20).

```bash
python voice.py 9876543210 "Namaste, test call" hi
```

The message goes inline with the Vonage request, so no webhook. The private
key is read from `farmer-ivr/private.key` and is never committed. Without
`VONAGE_NUMBER` test calls come from a random US number.

Set `VOICE_DRY_RUN=1` to print what would be said instead of dialling. Do that
before testing anything that isn't the call itself.

### Voice tuning

| Variable | Default | |
|---|---|---|
| `VOICE_LEVEL` | 1 | Volume, -1 to 1 |
| `VOICE_LEAD_IN` | 2 | Seconds of silence before speaking |
| `VOICE_RATE` | slow | Speech rate |
| `VOICE_TOKEN_RATE` | x-slow | Rate for the token number |
| `VOICE_PREMIUM` | off | Neural voice, less robotic, costs more |
| `VOICE_STYLE` | unset | Hindi voice: 0, 1, 3, 4, 5, 6 (premium on all but 0) |

`python voice.py --voices 9876543210` reads the same line in every Hindi voice
on one call so you can pick.

Farmers ringing *us* isn't done yet, the start of it is in `farmer-ivr/`. It
reads `/ivr/status.json`, which needs `IVR_TOKEN` set on both sides.

## Book by speaking

Chrome, Edge and Safari do speech to text in the browser. Firefox can only
record, so the recording goes to the server and `faster-whisper` transcribes
it. That part is optional and not in requirements.txt:
`pip install faster-whisper==1.2.1`, then `python speech_to_text.py download`
(about 480 MB).

## Server

An Azure VM (Ubuntu 24.04, B1s), gunicorn behind Caddy for https.

```bash
# on the VM, once the domain points at it
curl -fsSLO https://raw.githubusercontent.com/siddhulaheja-ctrl/farmer-procurement-platform/main/deploy/setup.sh
sudo bash setup.sh your-domain.me
```

Then copy the files that aren't in git into `/srv/krishi`: `procurement.db`,
`.env`, `.secret_key` (same key, so passes already printed still verify) and
`farmer-ivr/private.key`. `sudo chown -R krishi:krishi /srv/krishi` and
`sudo systemctl restart krishi`.

After pushing new code: `sudo bash /srv/krishi/deploy/update.sh`.
Logs: `journalctl -u krishi -f`.

The database is backed up every night at 02:30 to `/var/backups/krishi`
(two weeks kept). Backup now: `sudo krishi-backup`. To pull the latest one
to this PC:

```bash
ssh -i ~/.ssh/krishi_azure azureuser@172.198.152.215 'sudo sh -c "cat \$(ls -t /var/backups/krishi/*.gz | head -1)"' > procurement-backup.db.gz
```

## Files

| file | what it does |
|---|---|
| app.py | routes |
| core.py | booking rules, capacity and per farmer limits |
| validation.py | aadhaar / bank / land checks |
| payments.py | payment stages and the mock bank |
| gate.py | gate pass scanning, check in and out |
| qr.py | signed QR codes for passes and receipts |
| weather.py | forecast and storage risk |
| voicebook.py, voice_ai.py | understanding spoken bookings |
| voice_register.py | registering by voice |
| assistant.py | help chat |
| voice.py | outbound calls |
| supervisor.py, audit.py | superadmin screens and the activity log |
| i18n.py, lang/ | translations (`python -m lang.check` lists missing ones) |
| db.py, schema.sql | sqlite |
