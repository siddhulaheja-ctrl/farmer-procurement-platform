# Smart Farmer Procurement Platform — Technical & Feature Spec
### SIH 2026 | Problem Statement 26032

---

## 1. Project Overview

A slot-booking and procurement management platform for government crop procurement centres, layered with three gap-filling features (storage-risk alerts, data mismatch pre-validation, and interactive IVR) that address documented shortcomings in existing state systems (e-Kharid, e-Uparjan, P-PAS).

**Two user types:**
- **Farmer** — registers, books a slot, tracks status
- **Centre Admin/Staff** — manages slots, verifies produce, updates transaction/payment status

**Two access channels to the same backend:**
- Web app (smartphone/desktop users)
- IVR phone system (feature-phone/no-internet users)

---

## 2. Tech Stack Recommendation

| Layer | Tool | Why |
|---|---|---|
| Backend | **Flask (Python)** | Team already knows Python; fast to prototype REST APIs |
| Database | **SQLite** (dev) → PostgreSQL if time permits | Zero-config for hackathon; easy to inspect/debug |
| Frontend | **HTML/CSS/JS**, or React if a team member is comfortable | Keep it simple unless someone already knows React |
| CSS Framework | **Tailwind CSS** or **Bootstrap** | Fast, clean, mobile-responsive styling without custom design work |
| IVR/Voice | **Twilio** (or **Exotel** for India-specific trial terms) | Free trial tier, well-documented, verified-number calling works for demos |
| SMS (optional/simulated) | **Fast2SMS** or **Twilio SMS** | Free-tier SMS for real demo messages, or just log to console/db |
| Weather data (for storage-risk feature) | **OpenWeatherMap API** (free tier) | Simple REST API, generous free quota |
| Hosting (for demo) | **Render / Railway / PythonAnywhere** (free tiers) | Quick deploy so the app is accessible via a live link, not just localhost |
| Version control | **GitHub** | Team collaboration, also shows up well if you want to link a repo in your PPT |
| PDF/Certificate generation (if needed) | **ReportLab** (Python) | For generating e-gate-pass/token documents |

---

## 3. Database Schema (Core Tables)

1. **farmers**
   `id, name, phone_number, aadhaar_number (mock), bank_account (mock), land_record_id (mock), village/district, registered_via (self/CSC/staff), created_at`

2. **procurement_centres**
   `id, name, location, district, daily_capacity, crop_types_accepted`

3. **slots**
   `id, centre_id, date, time_window, max_capacity, booked_count`

4. **bookings**
   `id, farmer_id, slot_id, crop_type, estimated_quantity, status (booked/completed/cancelled), created_at`

5. **transactions**
   `id, booking_id, actual_quantity, quality_grade, price_per_unit, total_amount, payment_status (pending/processing/completed/failed), payment_date`

6. **data_validation_flags**
   `id, farmer_id, field_flagged (aadhaar/bank/land), status (unresolved/resolved), flagged_at`

7. **alerts_log**
   `id, farmer_id, alert_type (storage_risk/slot_reminder/payment_update), channel (app/ivr/sms), message, sent_at`

---

## 4. Feature List

### 4.1 Core Features (MUST WORK — build first)

**Farmer-facing:**
- [ ] Registration (self-service on web, or assisted entry by staff/CSC operator — build both entry points)
- [ ] View available procurement centres + upcoming slot availability
- [ ] Book a slot (select centre, date, crop type, estimated quantity)
- [ ] View booking status (upcoming/completed) and basic transaction/payment status
- [ ] Cancel/reschedule a booking

**Admin/Staff-facing:**
- [ ] Dashboard: view all bookings for a centre, filter by date/status
- [ ] Mark a booking as "arrived" → record actual quantity + quality grade
- [ ] Mark transaction as complete → trigger payment status update
- [ ] Manually register a farmer (for assisted/CSC registration flow)
- [ ] View/resolve flagged data mismatches

**System logic:**
- [ ] Slot capacity enforcement (don't allow overbooking beyond `max_capacity`)
- [ ] Basic queue/priority logic (first-come-first-served, or fair-access cap per farmer per day — reference Odisha's P-PAS model if time allows)

---

### 4.2 Novelty Features (differentiators — build second)

**A. Data Mismatch Pre-Validation**
- On registration, check farmer's Aadhaar/bank/land record fields (mock data) against a simple validation rule set (e.g., name-match check, field-not-empty check, format check)
- If mismatch found → flag it in `data_validation_flags`, notify farmer (app banner + IVR call) *before* their slot date
- Admin dashboard shows unresolved flags so staff can proactively help fix them

**B. Storage-Risk Alerts**
- When a slot is booked more than X days out (configurable, e.g., >5 days), call OpenWeatherMap API for the farmer's district
- Simple rule-based logic: if forecast shows rain/high humidity in the waiting window → flag as high spoilage risk
- Trigger alert via app notification + IVR call: "Your slot is 8 days away and rain is expected — consider requesting an earlier slot"
- (For demo reliability: allow a manual override/mock toggle to force-trigger this condition live, in case real weather doesn't cooperate on demo day)

**C. Interactive IVR System** *(build as a standalone module — does not block on main app being finished)*
- Twilio number + TwiML/Studio flow
- Call triggers:
  1. Slot confirmation call (on booking)
  2. Data verification call (pre-slot — "press 1 to confirm your bank details")
  3. Storage-risk warning call (if flagged by feature B)
- Inbound: farmer can call back the number anytime → IVR menu → check slot status / payment status via keypress, pulled from `bookings`/`transactions` tables (or mock JSON if built before main DB is ready)
- Webhook endpoint in Flask backend to receive Twilio's keypress callbacks and update records accordingly

---

### 4.3 Explicitly Out of Scope for the Demo (mention only in PPT/roadmap)

- Real Aadhaar/bank/land-record API integration (use mock/sample data only)
- Real payment/DBT processing (just update a status field)
- Production-scale SMS gateway integration
- Native Android app (web app only, framed as "mobile-ready")
- Multi-state/multi-language scaling claims (describe in architecture slide, don't build)

---

## 5. Development Guidelines

1. **Build the core booking flow first, end-to-end, before touching novelty features.** A working simple version beats a broken ambitious one.
2. **Use mock/seeded data generously.** Use Python's `Faker` library to generate realistic-looking fake farmers, bookings, and transactions early so every feature has data to work with during development — don't wait for real data.
3. **Keep the IVR module decoupled.** It should read from the same database/schema eventually, but can be developed and tested against a local JSON file in parallel by one person, without blocking on the main app.
4. **Mobile-first CSS.** Since farmers are the primary users and many will access via phone browsers, design and test the farmer-facing pages at mobile width first, admin dashboard can be desktop-oriented.
5. **Version control from day one.** Use a shared GitHub repo, branch per feature, merge frequently to avoid last-minute integration disasters.
6. **Have a fallback for every live-demo element.** Record a video of the IVR call, the booking flow, and the alert triggers *in advance*, in case venue wifi fails during the actual presentation.
7. **Don't over-engineer auth.** A simple login (even just phone number + OTP-simulated, or no real auth at all for the hackathon demo) is fine — don't burn time on production-grade security.
8. **Document your "future scope" clearly in the code/comments** where you've mocked something (e.g., `# TODO: replace with real Aadhaar API in production`) — makes it easy to explain to judges what's real vs. simulated if asked.

---

## 6. Suggested Task Split (6-person team)

| Person | Focus |
|---|---|
| 1-2 | Backend: Flask APIs, database, booking/slot logic |
| 1-2 | Frontend: farmer-facing pages + admin dashboard (HTML/CSS/JS or React) |
| 1 | IVR module (Twilio) + storage-risk/weather integration + data validation logic |
| 1 | PPT, demo script, testing/QA, presentation polish |

(Adjust based on who ends up most comfortable with backend vs frontend once you start — roles can overlap.)
