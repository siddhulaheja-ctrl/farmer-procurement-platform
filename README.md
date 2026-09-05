# Smart Farmer Procurement Platform

Slot booking and procurement management for government crop procurement centres.
Smart India Hackathon 2026, Problem Statement 26032.

Working prototype of the web channel described in
[the spec](Farmer_Procurement_Platform_Spec.md). The IVR channel is not built —
only its data feed and a webhook stub (see [Not built](#not-built)).

---

## Run it

Runs on Windows, macOS and Linux. Python 3.9+ is the only prerequisite.

**Windows** — double-click `start_demo.bat`.

**macOS / Linux**:

```bash
./start_demo.sh
```

Either script installs dependencies if they are missing, seeds the database on
first run, starts the server and opens a browser.

To do it by hand on any platform:

```bash
pip install -r requirements.txt && python seed.py && python app.py
```

Then open <http://localhost:5000>.

`seed.py` drops and rebuilds `procurement.db` with ~50 farmers, 8 centres, 480
slots and 82 bookings. Run it again any time to reset the demo to a clean state
(`reset_demo.bat` / `./reset_demo.sh`).

### macOS note: port 5000

macOS Monterey and later run **AirPlay Receiver** on port 5000, which is also
Flask's default. `start_demo.sh` detects this and moves to port 5001 by itself,
telling you it has done so. If you start the app by hand and see
`Address already in use`, either set the port:

```bash
PORT=5001 python app.py
```

or turn off System Settings → General → AirDrop & Handoff → AirPlay Receiver.

### Demo logins

| Role | Credentials | Why |
|---|---|---|
| Farmer | `9000000001`, OTP `123456` | Ramesh Kumar — clean record, one near slot and one 9 days out that is flagged for storage risk |
| Farmer | `9000000002`, OTP `123456` | Sunita Devi — five deliberate detail mismatches |
| Staff | `ADMIN` / `demo123` | District supervisor, sees every centre |
| Staff | `STAFF01` / `demo123` | Single-centre clerk |

---

## What works

### Core (spec §4.1)

- Self-service registration, and staff/CSC-assisted registration
- Browse centres, filter by district and crop, see live slot availability
- Book, reschedule and cancel a slot; printable e-gate-pass with token number
- Booking and payment status tracking for the farmer
- Staff dashboard filtered by centre, date and status
- Mark arrived → record weighed quantity and quality grade → auto-price against MSP
- Close transaction → payment status flow (pending → processing → completed/failed)
- Slot capacity management, view utilisation, create or resize slots
- Farmer record search and correction

**System logic**

- Capacity enforcement — a slot cannot be booked past `max_capacity`, and the
  count is decremented correctly on cancel and reschedule
- Fair access (P-PAS style) — one slot per farmer per day, three active
  bookings maximum
- Crop eligibility — a centre only accepts the crops it procures

### Novelty A — Data mismatch pre-validation (spec §4.2.A)

Runs at registration, not weeks later at payout. Checks in
[`validation.py`](validation.py):

| Check | Rule |
|---|---|
| Aadhaar | 12 digits, cannot start with 0 or 1, **and must pass the Verhoeff checksum** — the real scheme Aadhaar uses, so a mistyped number is caught |
| Bank account | 9–18 digits, present |
| IFSC | 4 letters + `0` + 6 alphanumerics |
| Name match | Registered name vs name on the bank account, fuzzy-matched; below 85% is flagged. This is the single most common cause of DBT failure |
| Land record | Present and in state format `DDD-NNNNNN-NN` |

Blocking flags (Aadhaar, bank) versus warnings (name match, land record).
The farmer sees a banner and can self-correct; staff get a queue at
**Data Flags**. Closing a transaction for a farmer with an open *blocking*
flag marks the payment **failed** — which is the exact failure this feature
exists to prevent, made visible.

### Novelty B — Storage-risk alerts (spec §4.2.B)

In [`weather.py`](weather.py). When a booking is more than 5 days out
(`STORAGE_RISK_LEAD_DAYS`), the forecast for the farmer's district is checked
across the waiting window:

- ≥5 mm total rain **or** ≥80% average humidity → **high** risk
- any rain, or ≥65% humidity → **low** risk

High risk raises an in-app alert, queues an IVR call, and shows a warning with
the day-by-day forecast on the booking page. Staff get a ranked watchlist at
**Storage Risk** so they can offer earlier slots.

**Weather data**: uses OpenWeatherMap when `OWM_API_KEY` is set, and falls back
to a deterministic mock forecast automatically if the key is missing or the call
fails. The demo runs on the mock by default, so it does not depend on venue wifi.

### Demo controls

`/admin/demo` — the manual override the spec asks for:

- Force every storage-risk check to return HIGH
- Re-scan all upcoming bookings
- Fetch and inspect a district forecast
- Re-run validation across every farmer
- Settle all in-flight payments, so the farmer-side payment view can be shown
  updating live

This screen would not exist in a deployed system. It is presentation
scaffolding.

---

## Not built

- **IVR / Twilio voice** — skipped for this build. Two hooks are in place so the
  module can be dropped in without touching the core app:
  - `GET /ivr/status.json?phone=9000000001` — slots, payments, open flags and
    queued voice calls for one farmer, as JSON
  - `POST /ivr/webhook` — Twilio keypress stub, returns TwiML, already handles
    press-1 (slot status) and press-2 (payment status)

  Every alert that would become a phone call is already written to `alerts_log`
  with `channel='ivr'`, so the IVR module has a work queue waiting for it.
- **Real SMS** — messages are logged to `alerts_log`, not sent.
- **Real Aadhaar / bank / land-record APIs** — mock data, per spec §4.3.
- **Real DBT payment** — status field only, per spec §4.3.
- **PDF gate pass** — rendered as a printable HTML page instead of ReportLab.
  `Ctrl+P` produces the same result with less code.

---

## Sharing it

**With teammates, right now** — `share_demo.bat` on Windows, `./share_demo.sh`
on macOS/Linux. It starts the server and opens a free Cloudflare quick tunnel,
printing an `https://….trycloudflare.com` link that works from anywhere, copying
it to your clipboard and saving it to `LAST_SHARE_LINK.txt`. The link is live
only while that window is open, and you get a different one each run.

Needs cloudflared: `winget install Cloudflare.cloudflared` on Windows,
`brew install cloudflared` on macOS.

**On the same wifi** — start the app and give people `http://<your-ip>:5000`
(`ipconfig` on Windows, `ipconfig getifaddr en0` on macOS). Windows Firewall
asks to allow Python on private networks the first time; macOS asks whether to
allow incoming connections.

Both routes expose the app with no real authentication: anyone with the link can
sign in as any farmer (OTP `123456`) or as `ADMIN`/`demo123`, and can change
bookings and payment statuses. The data is entirely fake, so nothing is at risk
— but run `reset_demo.bat` before presenting, in case someone has been clicking
around.

## Deploy

`render.yaml`, `Procfile` and `runtime.txt` are ready. On Render, point at the
repo and it will build, seed and start. Set `SECRET_KEY`, and `OWM_API_KEY` if
you want live weather.

Free-tier disks are ephemeral, so the database resets on restart. Acceptable for
a demo; move to PostgreSQL for anything real.

---

## Layout

| File | Purpose |
|---|---|
| [`app.py`](app.py) | Flask routes, auth, template filters |
| [`core.py`](core.py) | Booking rules — capacity, fair access, MSP pricing |
| [`validation.py`](validation.py) | Novelty A — the check rules and Verhoeff implementation |
| [`weather.py`](weather.py) | Novelty B — forecast fetch, risk rules, demo override |
| [`alerts.py`](alerts.py) | Alert dispatch and the `alerts_log` write path |
| [`db.py`](db.py) | SQLite helpers (no ORM — the schema stays readable) |
| [`schema.sql`](schema.sql) | All 7 tables from spec §3, plus `staff` |
| [`seed.py`](seed.py) | Faker-generated demo data |
| `templates/`, `static/css/gov.css` | Mobile-first farmer pages, desktop admin dashboard |
| `start_demo.*`, `share_demo.*`, `reset_demo.*` | Launchers — `.bat`/`.ps1` for Windows, `.sh` for macOS/Linux |

Auth is deliberately thin (spec guideline #7): phone + simulated OTP for
farmers, a shared demo password for staff. Everywhere something is mocked, the
code says so in a `TODO`.
