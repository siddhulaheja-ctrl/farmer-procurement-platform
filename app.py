"""Main flask app - all the routes live here.

SIH 2026, PS 26032.

Outbound calls are in voice.py. Farmers ringing us is not built, the half
finished menu is in farmer-ivr/ and reads from /ivr/status.json.

Login is kept simple for now, OTP is hardcoded and staff share one password.
TODO: real OTP + hash the staff passwords
"""

import os
from datetime import date, datetime
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from markupsafe import Markup, escape

import env

env.load()          # has to run before the modules below read os.environ

import alerts as alerts_mod  # noqa: E402
import accounts
import audit
import core
import db
import qr
import supervisor
import voice
import weather
from core import BookingError
from db import execute, query
from i18n import t, get_lang
from validation import unresolved_flags, validate_and_flag

# hardcoded otp, shown on the login page
DEMO_OTP = "123456"

HERE = os.path.dirname(os.path.abspath(__file__))


def _last_updated():
    """Newest mtime across the code and templates. Gov footers always have a
    stale "last updated" because someone has to remember to change it. Work it
    out instead."""
    newest = 0
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in
                   (".git", "__pycache__", "farmer-ivr", "venv", ".venv")]
        for f in files:
            if f.endswith((".py", ".html", ".css", ".js", ".sql")):
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(root, f)))
                except OSError:
                    pass
    return date.fromtimestamp(newest) if newest else date.today()


LAST_UPDATED = _last_updated()

# Footer links. Real portals have these, and ours all go somewhere rather
# than being dead anchors.
POLICIES = {
    "terms": ("Terms of use", [
        "This is a prototype built for Smart India Hackathon 2026 against problem "
        "statement 26032. It is not a live government service and no part of it is "
        "connected to a real procurement system.",
        "Nothing entered here creates any entitlement, booking or payment obligation. "
        "Do not use real Aadhaar numbers, bank details or land record identifiers.",
    ]),
    "privacy": ("Privacy policy", [
        "The portal stores what you type into the registration form - your name, mobile "
        "number, village, district, and the identity and bank fields used by the "
        "validation checks. It is all held in a single SQLite file on the machine "
        "running the demo.",
        "Nothing is shared with a third party. The only outbound requests the portal "
        "makes are to OpenWeatherMap for the forecast in your district, which sends a "
        "place name and no personal data, and to Vonage when staff place a voice call, "
        "which sends the number being dialled and the words to be read out.",
        "There is no analytics, no advertising and no tracking cookie. The one cookie "
        "is the session that keeps you signed in.",
    ]),
    "copyright": ("Copyright policy", [
        "The source code is published at github.com/siddhulaheja-ctrl/farmer-procurement-platform.",
        "Photographs are from Wikimedia Commons and remain under their own CC BY-SA "
        "licences, credited in the page footer and in static/img/credits.json.",
        "The Minimum Support Price figures quoted are indicative published rates for "
        "RMS 2025-26 and are reproduced for demonstration only.",
    ]),
    "hyperlinking": ("Hyperlinking policy", [
        "Links to external sites are provided for convenience. We do not control their "
        "content and a link does not imply endorsement.",
        "You may link to any page on this portal without asking. We do not permit our "
        "pages to be loaded inside a frame on another site.",
    ]),
    "accessibility": ("Accessibility statement", [
        "The portal aims to meet WCAG 2.1 level AA. Text size can be set from the "
        "controls at the top of every page and is remembered in your browser.",
        "Every page can be reached with the keyboard alone, there is a skip link to the "
        "main content, form fields carry labels, and colour is never the only way "
        "something is communicated - status is always written out as well.",
        "This has not been through a formal audit. If you find something unusable, that "
        "is a defect and we want to hear about it.",
    ]),
}


def icon(name, cls=""):
    """{{ icon('calendar') }} in a template. Points into the one cached sprite
    rather than pasting the drawing into every page. Hidden from screen
    readers - every icon sits next to words that already say the same thing."""
    return Markup('<svg class="ic %s" aria-hidden="true" focusable="false">'
                  '<use href="%s#%s"></use></svg>'
                  % (escape(cls), url_for("static", filename="img/icons.svg"), escape(name)))


# App factory

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "sih-2026-ps26032-demo-key")
    app.teardown_appcontext(db.close_db)
    db.migrate()
    app.jinja_env.globals["t"] = t
    app.jinja_env.globals["lang"] = get_lang
    app.jinja_env.globals["icon"] = icon
    register_routes(app)
    register_filters(app)
    return app


def register_filters(app):
    @app.template_filter("nicedate")
    def nicedate(value):
        try:
            d = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return value
        return d.strftime("%d %b %Y")

    @app.template_filter("dayname")
    def dayname(value):
        try:
            d = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return ""
        delta = (d - date.today()).days
        if delta == 0:
            return t("Today")
        if delta == 1:
            return t("Tomorrow")
        return t(d.strftime("%A"))

    @app.template_filter("daysaway")
    def daysaway(value):
        try:
            d = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return "-"
        return (d - date.today()).days

    @app.template_filter("rupee")
    def rupee(value):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "-"
        # Indian digit grouping: 12,34,567.00
        whole, dec = ("%.2f" % v).split(".")
        neg = whole.startswith("-")
        whole = whole.lstrip("-")
        if len(whole) > 3:
            head, tail = whole[:-3], whole[-3:]
            parts = []
            while len(head) > 2:
                parts.insert(0, head[-2:])
                head = head[:-2]
            if head:
                parts.insert(0, head)
            whole = ",".join(parts) + "," + tail
        return ("-" if neg else "") + "₹" + whole + "." + dec

    @app.template_filter("mask")
    def mask(value, keep=4):
        """Hide all but the last few characters of an id number.

        A gate clerk needs to check the number against the card in the
        farmer's hand, which the last four digits do. The whole number on a
        screen at a busy gate is a copy of someone's aadhaar waiting to be
        photographed."""
        digits = "".join(str(value or "").split())
        if not digits:
            return "—"
        if len(digits) <= keep:
            return digits
        return "•" * (len(digits) - keep) + digits[-keep:]

    @app.template_filter("stamp")
    def stamp(value):
        try:
            return datetime.fromisoformat(str(value)).strftime("%d %b %Y, %H:%M")
        except (TypeError, ValueError):
            return value


# Auth decorators

def farmer_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("farmer_id"):
            flash(t("Please sign in to continue."), "warning")
            return redirect(url_for("login", next=request.path))
        return fn(*a, **kw)
    return wrapper


def staff_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        # g.staff, not the session: a switched-off account stops working on
        # its next click, not whenever the cookie happens to expire
        if not g.get("staff"):
            session.pop("staff_id", None)
            flash("Staff sign-in required.", "warning")
            return redirect(url_for("admin_login"))
        return fn(*a, **kw)
    return wrapper


def superadmin_required(fn):
    """Supervisor screens. Centre staff get a 403 rather than a redirect -
    they are signed in, they just can't open this."""
    @wraps(fn)
    @staff_required
    def wrapper(*a, **kw):
        if g.staff["role"] != "superadmin":
            abort(403)
        return fn(*a, **kw)
    return wrapper


def current_farmer():
    fid = session.get("farmer_id")
    return query("SELECT * FROM farmers WHERE id = ?", (fid,), one=True) if fid else None


def current_staff():
    sid = session.get("staff_id")
    if not sid:
        return None
    return query(
        "SELECT s.*, c.name AS centre_name FROM staff s"
        " LEFT JOIN procurement_centres c ON c.id = s.centre_id WHERE s.id = ? AND s.active = 1",
        (sid,), one=True)


# Routes

def register_routes(app):

    @app.before_request
    def _load_user():
        g.farmer = current_farmer()
        g.staff = current_staff()
        g.unread = alerts_mod.unread_count(g.farmer["id"]) if g.farmer else 0
        g.today = date.today()

    @app.context_processor
    def _footer_context():
        # staff screens need to know where calls go, every page needs the
        # footer bits
        ctx = {"call_to": voice.DEMO_NUMBER, "last_updated": LAST_UPDATED,
               "visits": _visits(), "policies": POLICIES, "my_centre": _my_centre()}
        # the count beside "Needs attention" in the supervisor's menu
        if g.get("staff") and g.staff["role"] == "superadmin":
            ctx["attention_count"] = supervisor.attention_count()
        return ctx

    def _visits(bump=False):
        """Read (and optionally bump) the footer counter. Wrapped so an old
        database without this table doesn't 500 the site."""
        try:
            if bump:
                execute("UPDATE site_counters SET value = value + 1 WHERE name = 'visits'")
            row = query("SELECT value FROM site_counters WHERE name = 'visits'", one=True)
            return row["value"] if row else 0
        except Exception:
            return 0

    # public

    @app.route("/")
    def home():
        _visits(bump=True)
        # Public weather lookup. A plain GET form, so the chosen district ends
        # up in the url and the page can be linked or reloaded.
        districts = _districts()
        picked = request.args.get("district", "")
        forecast = place = source = None
        if picked in districts:
            forecast, source, point = weather.get_forecast(picked, 5)
            place = point["place"] if point else picked
        return render_template("home.html", msp=core.MSP, districts=districts, picked=picked,
                               forecast=forecast, place=place, source=source)

    @app.route("/t/<token>")
    def token_lookup(token):
        """Where the QR on a gate pass lands.

        Staff at that centre get the booking screen, the farmer it belongs to
        gets their own copy, anyone else is sent to sign in having been shown
        nothing, so a photographed pass is worth nothing to whoever took it.
        """
        b = query("SELECT b.id, b.farmer_id, s.centre_id FROM bookings b JOIN slots s ON s.id = b.slot_id"
                  " WHERE b.token_no = ?", (token,), one=True)
        if b is None:
            flash("No booking found for token %s." % token, "error")
            return redirect(url_for("admin_login"))
        if g.staff:
            if not _in_my_centre(b["centre_id"]):
                flash("Token %s belongs to another centre." % token, "error")
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("admin_booking", booking_id=b["id"]))
        if g.farmer and g.farmer["id"] == b["farmer_id"]:
            return redirect(url_for("farmer_booking", booking_id=b["id"]))
        # the same message whoever you are - a farmer opening someone else
        # pass learns nothing they did not already hold
        flash("Sign in to open token %s." % token, "info")
        return redirect(url_for("admin_login"))

    @app.route("/policy/<slug>")
    def policy(slug):
        if slug not in POLICIES:
            abort(404)
        title, paragraphs = POLICIES[slug]
        return render_template("policy.html", title=title, paragraphs=paragraphs)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            phone = (request.form.get("phone") or "").strip()
            farmer = query("SELECT * FROM farmers WHERE phone_number = ?", (phone,), one=True)
            if farmer is None:
                flash(t("No farmer is registered with %s. Please register first.") % phone, "error")
                return render_template("login.html", phone=phone)
            session["pending_phone"] = phone
            # TODO: actually send the otp
            return redirect(url_for("verify_otp"))
        return render_template("login.html", phone="")

    @app.route("/verify-otp", methods=["GET", "POST"])
    def verify_otp():
        phone = session.get("pending_phone")
        if not phone:
            return redirect(url_for("login"))
        farmer = query("SELECT * FROM farmers WHERE phone_number = ?", (phone,), one=True)
        if request.method == "POST":
            if (request.form.get("otp") or "").strip() != DEMO_OTP:
                flash(t("Incorrect OTP. For this demo the OTP is always %s.") % DEMO_OTP, "error")
            else:
                session.pop("pending_phone", None)
                session["farmer_id"] = farmer["id"]
                flash(t("Signed in as %s.") % farmer["name"], "success")
                return redirect(request.args.get("next") or url_for("farmer_dashboard"))
        return render_template("otp.html", phone=phone, demo_otp=DEMO_OTP, farmer=farmer)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        """Self-service registration (the assisted/CSC path is /admin/register-farmer)."""
        if request.method == "POST":
            result = _create_farmer(request.form, registered_via="self")
            if result["error"]:
                flash(result["error"], "error")
                return render_template("register.html", form=request.form,
                                       districts=_districts(), crops=core.CROPS)
            session["farmer_id"] = result["farmer_id"]
            problems = result["problems"]
            if problems:
                flash(t("Registered, but we found %d issue(s) in your details. "
                        "See the notice on your dashboard.") % len(problems), "warning")
            else:
                flash(t("Registration complete. Your details passed all verification checks."),
                      "success")
            return redirect(url_for("farmer_dashboard"))
        return render_template("register.html", form={}, districts=_districts(), crops=core.CROPS)

    @app.route("/lang/<code>")
    def set_lang(code):
        if code in ("en", "hi"):
            session["lang"] = code
        return redirect(request.referrer or url_for("home"))

    @app.route("/logout")
    def logout():
        session.clear()
        flash(t("Signed out."), "success")
        return redirect(url_for("home"))

    # farmer

    @app.route("/farmer/dashboard")
    @farmer_required
    def farmer_dashboard():
        fid = g.farmer["id"]
        upcoming = query(
            "SELECT b.*, s.date, s.time_window, s.centre_id, s.max_capacity, s.booked_count,"
            " c.name AS centre_name, c.location, c.district AS centre_district,"
            " f.name AS farmer_name, f.phone_number, f.village, f.district AS farmer_district,"
            " t.payment_status, t.total_amount, t.actual_quantity, t.quality_grade"
            " FROM bookings b"
            " JOIN slots s ON s.id = b.slot_id"
            " JOIN procurement_centres c ON c.id = s.centre_id"
            " JOIN farmers f ON f.id = b.farmer_id"
            " LEFT JOIN transactions t ON t.booking_id = b.id"
            " WHERE b.farmer_id = ? AND b.status IN ('booked','arrived')"
            " ORDER BY s.date, s.time_window", (fid,))
        history = query(_BOOKING_SELECT + " WHERE b.farmer_id = ? AND b.status IN ('completed','cancelled')"
                        " ORDER BY s.date DESC LIMIT 10", (fid,))
        pending_amount = query(
            "SELECT COALESCE(SUM(t.total_amount),0) c FROM transactions t"
            " JOIN bookings b ON b.id = t.booking_id"
            " WHERE b.farmer_id = ? AND t.payment_status IN ('pending','processing')",
            (fid,), one=True)["c"]
        paid_amount = query(
            "SELECT COALESCE(SUM(t.total_amount),0) c FROM transactions t"
            " JOIN bookings b ON b.id = t.booking_id"
            " WHERE b.farmer_id = ? AND t.payment_status = 'completed'", (fid,), one=True)["c"]
        return render_template("farmer/dashboard.html",
                               upcoming=upcoming, history=history,
                               flags=unresolved_flags(fid),
                               alerts=alerts_mod.farmer_alerts(fid, 5),
                               pending_amount=pending_amount, paid_amount=paid_amount)

    @app.route("/farmer/centres")
    @farmer_required
    def farmer_centres():
        district = request.args.get("district", "")
        crop = request.args.get("crop", "")
        # "311 open slots" answers a question nobody asked. What a farmer wants
        # to know is when they can next turn up.
        sql = ("SELECT c.*, "
               " (SELECT MIN(s.date || ' ' || s.time_window) FROM slots s"
               "   WHERE s.centre_id = c.id AND s.date >= ?"
               "     AND s.booked_count < s.max_capacity) AS next_free"
               " FROM procurement_centres c WHERE 1=1")
        args = [date.today().isoformat()]
        if district:
            sql += " AND c.district = ?"
            args.append(district)
        if crop:
            sql += " AND c.crop_types_accepted LIKE ?"
            args.append("%" + crop + "%")
        sql += " ORDER BY (c.district = ?) DESC, c.name"
        args.append(g.farmer["district"])
        centres = query(sql, tuple(args))
        return render_template("farmer/centres.html", centres=centres,
                               districts=_districts(), crops=core.CROPS,
                               sel_district=district, sel_crop=crop)

    @app.route("/farmer/centre/<int:centre_id>")
    @farmer_required
    def farmer_centre(centre_id):
        centre = query("SELECT * FROM procurement_centres WHERE id = ?", (centre_id,), one=True)
        if centre is None:
            abort(404)
        slots = query(
            "SELECT * FROM slots WHERE centre_id = ? AND date >= ? ORDER BY date, time_window",
            (centre_id, date.today().isoformat()))
        by_date = {}
        for s in slots:
            by_date.setdefault(s["date"], []).append(s)
        accepted = [c.strip() for c in centre["crop_types_accepted"].split(",")]
        return render_template("farmer/centre.html", centre=centre, by_date=by_date,
                               accepted=accepted, reschedule_id=request.args.get("reschedule"))

    @app.route("/farmer/book", methods=["POST"])
    @farmer_required
    def farmer_book():
        slot_id = request.form.get("slot_id")
        try:
            booking_id = core.book_slot(g.farmer["id"], int(slot_id),
                                        request.form.get("crop_type"),
                                        request.form.get("estimated_quantity"))
        except (BookingError, TypeError, ValueError) as e:
            flash(str(e) if isinstance(e, BookingError) else t("Invalid booking request."), "error")
            return redirect(request.form.get("back") or url_for("farmer_centres"))

        b = query(_BOOKING_SELECT + " WHERE b.id = ?", (booking_id,), one=True)
        alerts_mod.raise_alert(
            g.farmer["id"], "booking_confirmed", "app",
            "Slot confirmed at %s on %s, %s. Token %s. Bring this token and your "
            "registration ID to the centre." % (b["centre_name"], b["date"], b["time_window"],
                                                b["token_no"]),
            booking_id=booking_id,
            message_hi="स्लॉट पक्का: %s, %s, %s बजे। टोकन %s।"
                       % (alerts_mod.hi(b["centre_name"]), voice.spoken_date(b["date"]),
                          b["time_window"], b["token_no"]))
        # for the ivr module to pick up later
        alerts_mod.raise_alert(
            g.farmer["id"], "booking_confirmed", "ivr",
            "नमस्ते %s जी। आपका खरीद स्लॉट %s को %s बजे, %s पर बुक हो गया है। "
            "आपका टोकन नंबर %s है। कृपया आधार कार्ड और बैंक पासबुक साथ लाएं। धन्यवाद।"
            % (g.farmer["name"], b["date"], b["time_window"], b["centre_name"],
               ", ".join(" ".join(part) for part in str(b["token_no"]).split("-"))),
            booking_id=booking_id)

        # check storage risk now that we know the slot date
        risk = weather.evaluate_booking(booking_id)
        if risk and risk["level"] == "high":
            flash(t("Booking confirmed - but a storage risk was detected. See the warning on "
                  "your booking."), "warning")
        else:
            flash(t("Booking confirmed. Your token is %s.") % b["token_no"], "success")
        return redirect(url_for("farmer_booking", booking_id=booking_id))

    @app.route("/farmer/booking/<int:booking_id>")
    @farmer_required
    def farmer_booking(booking_id):
        b = _owned_booking(booking_id)
        txn = query("SELECT * FROM transactions WHERE booking_id = ?", (booking_id,), one=True)
        risk = None
        if b["status"] == "booked":
            risk = weather.assess_risk(g.farmer["district"], b["date"], g.farmer["village"])
        return render_template("farmer/booking.html", b=b, txn=txn, risk=risk,
                               queue=core.queue_position(booking_id),
                               delay=core.centre_delay(b["centre_id"]))

    @app.route("/farmer/booking/<int:booking_id>/cancel", methods=["POST"])
    @farmer_required
    def farmer_cancel(booking_id):
        try:
            core.cancel_booking(booking_id, g.farmer["id"])
            flash(t("Booking cancelled. The slot has been released for other farmers."), "success")
        except BookingError as e:
            flash(str(e), "error")
        return redirect(url_for("farmer_dashboard"))

    @app.route("/farmer/booking/<int:booking_id>/reschedule", methods=["POST"])
    @farmer_required
    def farmer_reschedule(booking_id):
        try:
            core.reschedule_booking(booking_id, int(request.form.get("slot_id")), g.farmer["id"])
            weather.evaluate_booking(booking_id)
            b = query(_BOOKING_SELECT + " WHERE b.id = ?", (booking_id,), one=True)
            alerts_mod.raise_alert(
                g.farmer["id"], "slot_reminder", "app",
                "Your slot was moved to %s, %s at %s. New token %s."
                % (b["date"], b["time_window"], b["centre_name"], b["token_no"]),
                booking_id=booking_id,
                message_hi="आपका स्लॉट बदलकर %s, %s बजे, %s कर दिया गया। नया टोकन %s।"
                           % (voice.spoken_date(b["date"]), b["time_window"],
                              alerts_mod.hi(b["centre_name"]), b["token_no"]))
            flash(t("Slot rescheduled to %s, %s.") % (b["date"], b["time_window"]), "success")
        except (BookingError, TypeError, ValueError) as e:
            flash(str(e) if isinstance(e, BookingError) else t("Invalid slot."), "error")
        return redirect(url_for("farmer_booking", booking_id=booking_id))

    @app.route("/farmer/booking/<int:booking_id>/gatepass")
    @farmer_required
    def farmer_gatepass(booking_id):
        b = _owned_booking(booking_id)
        # absolute - it gets scanned from a different phone
        target = url_for("token_lookup", token=b["token_no"], _external=True)
        return render_template("farmer/gatepass.html", b=b, farmer=g.farmer,
                               issued=datetime.now(), qr_svg=qr.gatepass_svg(target),
                               qr_target=target)

    @app.route("/farmer/alerts")
    @farmer_required
    def farmer_alerts_page():
        rows = alerts_mod.farmer_alerts(g.farmer["id"])
        alerts_mod.mark_all_read(g.farmer["id"])
        return render_template("farmer/alerts.html", alerts=rows)

    @app.route("/farmer/payments")
    @farmer_required
    def farmer_payments():
        rows = query(
            "SELECT t.*, b.crop_type, b.token_no, s.date, c.name AS centre_name"
            "  FROM transactions t"
            "  JOIN bookings b ON b.id = t.booking_id"
            "  JOIN slots s ON s.id = b.slot_id"
            "  JOIN procurement_centres c ON c.id = s.centre_id"
            " WHERE b.farmer_id = ? ORDER BY s.date DESC", (g.farmer["id"],))
        return render_template("farmer/payments.html", rows=rows)

    @app.route("/farmer/profile", methods=["GET", "POST"])
    @farmer_required
    def farmer_profile():
        fid = g.farmer["id"]
        if request.method == "POST":
            execute(
                "UPDATE farmers SET name=?, aadhaar_number=?, bank_account=?, ifsc_code=?,"
                " bank_name_on_account=?, land_record_id=?, village=?, district=? WHERE id=?",
                ((request.form.get("name") or "").strip(),
                 (request.form.get("aadhaar_number") or "").strip(),
                 (request.form.get("bank_account") or "").strip(),
                 (request.form.get("ifsc_code") or "").strip().upper(),
                 (request.form.get("bank_name_on_account") or "").strip(),
                 (request.form.get("land_record_id") or "").strip().upper(),
                 (request.form.get("village") or "").strip(),
                 (request.form.get("district") or "").strip(), fid))
            problems = validate_and_flag(fid)
            if problems:
                flash(t("Saved. %d issue(s) still need attention.") % len(problems), "warning")
            else:
                flash(t("Saved. All verification checks passed - your payment will not be held up."),
                      "success")
            return redirect(url_for("farmer_profile"))
        return render_template("farmer/profile.html", farmer=g.farmer,
                               flags=unresolved_flags(fid), districts=_districts())

    # admin

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            code = (request.form.get("staff_code") or "").strip().upper()
            pwd = request.form.get("password") or ""
            s = query("SELECT * FROM staff WHERE staff_code = ?", (code,), one=True)
            # one message for a wrong code, a wrong password and a switched-off
            # account, so the form can't be used to find out which codes exist
            if s is None or not s["active"] or not accounts.check_password(s["password"], pwd):
                flash("Invalid staff code or password.", "error")
                return render_template("admin/login.html", code=code)
            session["staff_id"] = s["id"]
            execute("UPDATE staff SET last_login = ? WHERE id = ?",
                    (datetime.now().isoformat(timespec="seconds"), s["id"]))
            audit.record(s, "sign_in")
            flash("Signed in as %s." % s["name"], "success")
            if s["role"] == "superadmin":
                return redirect(url_for("super_overview"))
            return redirect(url_for("admin_dashboard"))
        return render_template("admin/login.html", code="")

    @app.route("/admin/dashboard")
    @staff_required
    def admin_dashboard():
        centre_id = _my_centre() or request.args.get("centre_id") or ""
        dt = request.args.get("date", "")
        status = request.args.get("status", "")

        sql = _BOOKING_SELECT + " WHERE 1=1"
        args = []
        if centre_id:
            sql += " AND c.id = ?"
            args.append(centre_id)
        if dt:
            sql += " AND s.date = ?"
            args.append(dt)
        if status:
            sql += " AND b.status = ?"
            args.append(status)
        sql += " ORDER BY s.date, s.time_window, b.id"
        bookings = query(sql, tuple(args))

        scope = "AND c.id = %s" % int(centre_id) if centre_id else ""
        counts = query(
            "SELECT b.status, COUNT(*) c FROM bookings b"
            " JOIN slots s ON s.id = b.slot_id"
            " JOIN procurement_centres c ON c.id = s.centre_id"
            " WHERE 1=1 %s GROUP BY b.status" % scope)
        summary = {r["status"]: r["c"] for r in counts}
        fscope, fargs = _farmer_scope("f")
        summary["flags"] = query(
            "SELECT COUNT(*) c FROM data_validation_flags d JOIN farmers f ON f.id = d.farmer_id"
            " WHERE d.status = 'unresolved' AND " + fscope, fargs, one=True)["c"]
        summary["risk"] = query(
            "SELECT COUNT(*) c FROM bookings b JOIN slots s ON s.id = b.slot_id"
            " WHERE b.storage_risk = 'high' AND b.status = 'booked'"
            + (" AND s.centre_id = ?" if centre_id else ""),
            (int(centre_id),) if centre_id else (), one=True)["c"]

        return render_template("admin/dashboard.html", bookings=bookings,
                               centres=_centres_visible(),
                               sel_centre=str(centre_id), sel_date=dt, sel_status=status,
                               summary=summary)

    @app.route("/admin/booking/<int:booking_id>")
    @staff_required
    def admin_booking(booking_id):
        b = _scoped_booking(booking_id)
        txn = query("SELECT * FROM transactions WHERE booking_id = ?", (booking_id,), one=True)
        farmer = query("SELECT * FROM farmers WHERE id = ?", (b["farmer_id"],), one=True)
        return render_template("admin/booking.html", b=b, txn=txn, farmer=farmer,
                               flags=unresolved_flags(b["farmer_id"]),
                               grades=core.GRADES, msp=core.MSP)

    @app.route("/admin/booking/<int:booking_id>/arrive", methods=["POST"])
    @staff_required
    def admin_arrive(booking_id):
        b = _scoped_booking(booking_id)
        if b["status"] != "booked":
            flash("Only a booked entry can be marked as arrived.", "error")
            return redirect(url_for("admin_booking", booking_id=booking_id))
        try:
            actual = float(request.form.get("actual_quantity"))
        except (TypeError, ValueError):
            flash("Enter the actual weighed quantity in quintals.", "error")
            return redirect(url_for("admin_booking", booking_id=booking_id))
        grade = request.form.get("quality_grade")
        if grade not in core.GRADES:
            flash("Select a quality grade.", "error")
            return redirect(url_for("admin_booking", booking_id=booking_id))

        rate, total = core.compute_amount(b["crop_type"], actual, grade)
        execute("UPDATE bookings SET status = 'arrived' WHERE id = ?", (booking_id,))
        if query("SELECT id FROM transactions WHERE booking_id = ?", (booking_id,), one=True):
            execute("UPDATE transactions SET actual_quantity=?, quality_grade=?,"
                    " price_per_unit=?, total_amount=? WHERE booking_id=?",
                    (actual, grade, rate, total, booking_id))
        else:
            execute("INSERT INTO transactions (booking_id, actual_quantity, quality_grade,"
                    " price_per_unit, total_amount, payment_status)"
                    " VALUES (?,?,?,?,?, 'pending')", (booking_id, actual, grade, rate, total))

        alerts_mod.raise_alert(
            b["farmer_id"], "payment_update", "app",
            "Produce weighed at the centre: %.1f quintals of %s, grade %s. "
            "Provisional value %.2f. Awaiting transaction completion."
            % (actual, b["crop_type"], grade, total), booking_id=booking_id,
            message_hi="आपकी उपज तौली गई: %.1f क्विंटल %s, ग्रेड %s। अनुमानित राशि ₹%d।"
                       % (actual, alerts_mod.hi(b["crop_type"]), grade, int(total)))
        audit.record(g.staff, "weigh", farmer_id=b["farmer_id"], booking_id=booking_id,
                     centre_id=b["centre_id"],
                     detail="%.1f quintals of %s, grade %s" % (actual, b["crop_type"], grade))
        flash("Recorded: %.1f quintals, grade %s." % (actual, grade), "success")
        return _after_write(booking_id)

    @app.route("/admin/booking/<int:booking_id>/call", methods=["POST"])
    @staff_required
    def admin_call(booking_id):
        """Ring the farmer about this booking.

        Which of the four messages they hear depends on the booking state.
        Rings their own number - only the fake 900000 block gets diverted."""
        b = _scoped_booking(booking_id)

        # order matters. status first, or a cancelled booking gets read out
        # as "your slot is booked, please come" - which it did for a while.
        if b["status"] == "cancelled":
            flash("That booking was cancelled, so there is nothing to tell them. "
                  "Ring them from the farmer's page instead.", "error")
            return redirect(request.referrer
                            or url_for("admin_booking", booking_id=booking_id))

        if b["payment_status"] == "failed":
            message = ("नमस्ते %s जी। आपका भुगतान रुका हुआ है क्योंकि आपके दस्तावेज़ों में "
                       "गड़बड़ी है। कृपया अपने खरीद केंद्र पर आधार कार्ड और बैंक पासबुक "
                       "लेकर आएं। धन्यवाद।" % b["farmer_name"])
        elif b["status"] == "completed":
            message = ("नमस्ते %s जी। आपकी उपज की खरीद पूरी हो गई है। %d रुपये का भुगतान "
                       "प्रक्रिया में है और दो से तीन दिन में आपके बैंक खाते में जमा हो "
                       "जाएगा। धन्यवाद।"
                       % (b["farmer_name"], int(b["total_amount"] or 0)))
        elif b["storage_risk"] == "high":
            message = ("नमस्ते %s जी। कृषि सूत्र से सूचना। %s पर आपका स्लॉट %s को है और "
                       "आपके क्षेत्र में बारिश का अनुमान है। अपनी उपज को ढककर ऊंची जगह रखें, "
                       "या अपने केंद्र से पहले का स्लॉट मांगें। धन्यवाद।"
                       % (b["farmer_name"], b["centre_name"], voice.spoken_date(b["date"])))
        else:
            message = ("नमस्ते %s जी। आपका खरीद स्लॉट %s को %s बजे, %s पर बुक है। "
                       "आपका टोकन नंबर {{token}} है। मैं इसे दोबारा बोलती हूं। "
                       "टोकन नंबर {{token}}। धन्यवाद।"
                       % (b["farmer_name"], voice.spoken_date(b["date"]), b["time_window"],
                          b["centre_name"]))

        to, redirected = voice.target_for(b["phone_number"])
        ok, detail = voice.place_call(to, message, "hi", token=b["token_no"])
        if redirected:
            detail = "(demo number, %s has a placeholder) %s" % (b["farmer_name"], detail)
        voice.log_call(b["farmer_id"], message, ok, detail, booking_id=booking_id)
        topic = ("Payment held" if b["payment_status"] == "failed" else
                 "Payment update" if b["status"] == "completed" else
                 "Rain warning" if b["storage_risk"] == "high" else "Slot and token")
        audit.record(g.staff, "call", farmer_id=b["farmer_id"], booking_id=booking_id,
                     centre_id=b["centre_id"], detail=topic if ok else topic + " (did not connect)")
        flash(detail, "success" if ok else "error")
        return redirect(request.referrer or url_for("admin_booking", booking_id=booking_id))

    @app.route("/admin/booking/<int:booking_id>/complete", methods=["POST"])
    @staff_required
    def admin_complete(booking_id):
        b = _scoped_booking(booking_id)
        txn = query("SELECT * FROM transactions WHERE booking_id = ?", (booking_id,), one=True)
        if txn is None:
            flash("Record the weighed quantity before completing the transaction.", "error")
            return redirect(url_for("admin_booking", booking_id=booking_id))

        # don't pay out if their details are still wrong
        blocking = [f for f in unresolved_flags(b["farmer_id"]) if f["severity"] == "blocking"]
        if blocking:
            execute("UPDATE bookings SET status='completed' WHERE id=?", (booking_id,))
            execute("UPDATE transactions SET payment_status='failed' WHERE booking_id=?",
                    (booking_id,))
            alerts_mod.raise_alert(
                b["farmer_id"], "payment_update", "app",
                "Procurement completed but PAYMENT HELD: %d unresolved detail(s) - %s. "
                "Visit the centre with correct documents to release the payment."
                % (len(blocking), ", ".join(f["field_flagged"] for f in blocking)),
                booking_id=booking_id,
                message_hi="खरीद पूरी हुई, पर भुगतान रुका है। %d जानकारी ठीक करनी है। "
                           "सही दस्तावेज़ लेकर अपने केंद्र जाएं।" % len(blocking))
            audit.record(g.staff, "payment_held", farmer_id=b["farmer_id"], booking_id=booking_id,
                         centre_id=b["centre_id"], detail="%d blocking flag(s) open" % len(blocking))
            flash("Transaction closed, but payment marked FAILED - farmer has %d unresolved "
                  "blocking flag(s)." % len(blocking), "warning")
            return _after_write(booking_id)

        execute("UPDATE bookings SET status='completed' WHERE id=?", (booking_id,))
        execute("UPDATE transactions SET payment_status='processing' WHERE booking_id=?",
                (booking_id,))
        alerts_mod.raise_alert(
            b["farmer_id"], "payment_update", "app",
            "Transaction complete. %.2f is being credited to your registered bank account. "
            "Expect credit within 48-72 hours." % txn["total_amount"], booking_id=booking_id,
            message_hi="लेनदेन पूरा। ₹%d आपके बैंक खाते में 2-3 दिन में जमा होगा।"
                       % int(txn["total_amount"] or 0))
        alerts_mod.raise_alert(
            b["farmer_id"], "payment_update", "ivr",
            "नमस्ते। आपकी उपज की खरीद पूरी हो गई है। %d रुपये का भुगतान प्रक्रिया में है "
            "और दो से तीन दिन में आपके बैंक खाते में जमा हो जाएगा। धन्यवाद।"
            % int(txn["total_amount"] or 0), booking_id=booking_id)
        audit.record(g.staff, "close", farmer_id=b["farmer_id"], booking_id=booking_id,
                     centre_id=b["centre_id"], detail="Rs %s to be paid" % format(int(txn["total_amount"] or 0), ","))
        flash("Transaction completed. Payment moved to 'processing'.", "success")
        return _after_write(booking_id)

    @app.route("/admin/transactions")
    @staff_required
    def admin_transactions():
        status = request.args.get("payment_status", "")
        sql = ("SELECT t.*, b.crop_type, b.token_no, b.farmer_id, f.name AS farmer_name,"
               " f.phone_number, s.date, c.name AS centre_name"
               " FROM transactions t"
               " JOIN bookings b ON b.id = t.booking_id"
               " JOIN farmers f ON f.id = b.farmer_id"
               " JOIN slots s ON s.id = b.slot_id"
               " JOIN procurement_centres c ON c.id = s.centre_id WHERE 1=1")
        args = []
        if status:
            sql += " AND t.payment_status = ?"
            args.append(status)
        if _my_centre():
            sql += " AND c.id = ?"
            args.append(_my_centre())
        sql += " ORDER BY s.date DESC, t.id DESC"
        return render_template("admin/transactions.html", rows=query(sql, tuple(args)),
                               sel_status=status)

    @app.route("/admin/transaction/<int:txn_id>/payment", methods=["POST"])
    @staff_required
    def admin_payment(txn_id):
        new = request.form.get("payment_status")
        if new not in ("pending", "processing", "completed", "failed"):
            abort(400)
        t = query("SELECT t.*, b.farmer_id, s.centre_id FROM transactions t"
                  " JOIN bookings b ON b.id = t.booking_id JOIN slots s ON s.id = b.slot_id"
                  " WHERE t.id = ?", (txn_id,), one=True)
        if t is None or not _in_my_centre(t["centre_id"]):
            abort(404)
        pdate = datetime.now().isoformat(timespec="seconds") if new == "completed" else None
        execute("UPDATE transactions SET payment_status=?, payment_date=? WHERE id=?",
                (new, pdate, txn_id))
        msg = {
            "completed": "Payment of %.2f has been credited to your bank account." % (t["total_amount"] or 0),
            "processing": "Your payment of %.2f is being processed." % (t["total_amount"] or 0),
            "failed": "Your payment could not be processed. Please contact your procurement centre.",
            "pending": "Your payment is queued for processing.",
        }[new]
        amount = int(t["total_amount"] or 0)
        msg_hi = {
            "completed": "₹%d आपके बैंक खाते में जमा हो गए।" % amount,
            "processing": "₹%d का भुगतान प्रक्रिया में है।" % amount,
            "failed": "आपका भुगतान नहीं हो सका। अपने खरीद केंद्र से संपर्क करें।",
            "pending": "आपका भुगतान कतार में है।",
        }[new]
        alerts_mod.raise_alert(t["farmer_id"], "payment_update", "app", msg,
                               booking_id=t["booking_id"], message_hi=msg_hi)
        if new != t["payment_status"]:
            audit.record(g.staff, "payment_manual", farmer_id=t["farmer_id"],
                         booking_id=t["booking_id"], ref_id=txn_id, centre_id=t["centre_id"],
                         detail="Rs %s" % format(amount, ","), before=t["payment_status"], after=new)
        flash("Payment status set to '%s'." % new, "success")
        return redirect(request.referrer or url_for("admin_transactions"))

    @app.route("/admin/flags")
    @staff_required
    def admin_flags():
        show = request.args.get("status", "unresolved")
        fscope, fargs = _farmer_scope("f")
        sql = ("SELECT d.*, f.name AS farmer_name, f.phone_number, f.district"
               " FROM data_validation_flags d JOIN farmers f ON f.id = d.farmer_id"
               " WHERE " + fscope)
        args = list(fargs)
        if show in ("unresolved", "resolved"):
            sql += " AND d.status = ?"
            args.append(show)
        sql += " ORDER BY CASE d.severity WHEN 'blocking' THEN 0 ELSE 1 END, d.farmer_id"
        return render_template("admin/flags.html", flags=query(sql, tuple(args)), sel_status=show)

    @app.route("/admin/flag/<int:flag_id>/resolve", methods=["POST"])
    @staff_required
    def admin_resolve_flag(flag_id):
        f = query("SELECT * FROM data_validation_flags WHERE id = ?", (flag_id,), one=True)
        if f is None or not _farmer_visible(f["farmer_id"]):
            abort(404)
        execute("UPDATE data_validation_flags SET status='resolved', resolved_at=? WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"), flag_id))
        alerts_mod.raise_alert(f["farmer_id"], "data_mismatch", "app",
                               "Your '%s' detail has been verified and corrected by centre staff."
                               % f["field_flagged"],
                               message_hi="आपकी %s की जानकारी केंद्र ने जांचकर सही कर दी है।"
                               % {"aadhaar": "आधार", "bank": "बैंक", "land": "भूमि रिकॉर्ड",
                                  "name_match": "नाम"}.get(f["field_flagged"], f["field_flagged"]))
        audit.record(g.staff, "flag_verified", farmer_id=f["farmer_id"], ref_id=flag_id,
                     detail="%s: %s" % (f["field_flagged"], f["detail"]))
        flash("Flag marked resolved.", "success")
        return redirect(request.referrer or url_for("admin_flags"))

    @app.route("/admin/farmer/<int:farmer_id>", methods=["GET", "POST"])
    @staff_required
    def admin_farmer(farmer_id):
        farmer = query("SELECT * FROM farmers WHERE id = ?", (farmer_id,), one=True)
        if farmer is None or not _farmer_visible(farmer_id):
            abort(404)
        if request.method == "POST":
            execute(
                "UPDATE farmers SET name=?, aadhaar_number=?, bank_account=?, ifsc_code=?,"
                " bank_name_on_account=?, land_record_id=?, village=?, district=? WHERE id=?",
                ((request.form.get("name") or "").strip(),
                 (request.form.get("aadhaar_number") or "").strip(),
                 (request.form.get("bank_account") or "").strip(),
                 (request.form.get("ifsc_code") or "").strip().upper(),
                 (request.form.get("bank_name_on_account") or "").strip(),
                 (request.form.get("land_record_id") or "").strip().upper(),
                 (request.form.get("village") or "").strip(),
                 (request.form.get("district") or "").strip(), farmer_id))
            changed, before, after = audit.farmer_diff(farmer, request.form)
            if changed:
                audit.record(g.staff, "id_edit" if audit.touches_id(changed) else "record_edit",
                             farmer_id=farmer_id, before=before, after=after,
                             detail=", ".join(audit.FIELD_LABELS[k] for k in changed))
            problems = validate_and_flag(farmer_id)
            flash("Details updated. %s" % ("%d issue(s) remain." % len(problems) if problems
                                           else "All checks now pass."),
                  "warning" if problems else "success")
            return redirect(url_for("admin_farmer", farmer_id=farmer_id))
        bookings = query(_BOOKING_SELECT + " WHERE b.farmer_id = ? ORDER BY s.date DESC",
                         (farmer_id,))
        return render_template("admin/farmer.html", farmer=farmer, bookings=bookings,
                               flags=unresolved_flags(farmer_id), districts=_districts())

    @app.route("/admin/farmers")
    @staff_required
    def admin_farmers():
        q = (request.args.get("q") or "").strip()
        fscope, fargs = _farmer_scope("f")
        sql = ("SELECT f.*, "
               " (SELECT COUNT(*) FROM data_validation_flags d WHERE d.farmer_id = f.id"
               "   AND d.status='unresolved') AS flag_count,"
               " (SELECT COUNT(*) FROM bookings b WHERE b.farmer_id = f.id) AS booking_count"
               " FROM farmers f WHERE " + fscope)
        args = list(fargs)
        if q:
            sql += " AND (f.name LIKE ? OR f.phone_number LIKE ? OR f.village LIKE ?)"
            args += ["%" + q + "%"] * 3
        sql += " ORDER BY flag_count DESC, f.name LIMIT 200"     # add paging later
        return render_template("admin/farmers.html", farmers=query(sql, tuple(args)), q=q)

    @app.route("/admin/register-farmer", methods=["GET", "POST"])
    @staff_required
    def admin_register_farmer():
        """Assisted / CSC registration path (spec 4.1)."""
        if request.method == "POST":
            result = _create_farmer(request.form,
                                    registered_via=request.form.get("registered_via") or "staff")
            if result["error"]:
                flash(result["error"], "error")
                return render_template("admin/register_farmer.html", form=request.form,
                                       districts=_districts())
            audit.record(g.staff, "register_farmer", farmer_id=result["farmer_id"],
                         detail="CSC operator" if request.form.get("registered_via") == "csc"
                         else "At the counter")
            n = len(result["problems"])
            flash("Farmer registered. %s" % ("%d verification issue(s) flagged for follow-up." % n
                                             if n else "All verification checks passed."),
                  "warning" if n else "success")
            return redirect(url_for("admin_farmer", farmer_id=result["farmer_id"]))
        return render_template("admin/register_farmer.html", form={}, districts=_districts())

    @app.route("/admin/slots", methods=["GET", "POST"])
    @staff_required
    def admin_slots():
        if request.method == "POST":
            try:
                centre_id = int(request.form.get("centre_id"))
                cap = int(request.form.get("max_capacity"))
                on = request.form.get("date")
                datetime.strptime(on, "%Y-%m-%d")
            except (TypeError, ValueError):
                flash("Fill in centre, date and capacity correctly.", "error")
                return redirect(url_for("admin_slots"))
            if not _in_my_centre(centre_id):
                abort(403)
            tw = request.form.get("time_window")
            existing = query("SELECT id, max_capacity FROM slots"
                             " WHERE centre_id=? AND date=? AND time_window=?",
                             (centre_id, on, tw), one=True)
            if existing:
                execute("UPDATE slots SET max_capacity=? WHERE id=?", (cap, existing["id"]))
                if existing["max_capacity"] != cap:
                    audit.record(g.staff, "capacity_change", ref_id=existing["id"],
                                 centre_id=centre_id, detail="%s, %s" % (on, tw),
                                 before=existing["max_capacity"], after=cap)
                flash("Capacity updated for that slot.", "success")
            else:
                slot_id = execute("INSERT INTO slots (centre_id, date, time_window, max_capacity,"
                                  " booked_count) VALUES (?,?,?,?,0)", (centre_id, on, tw, cap))
                audit.record(g.staff, "slot_create", ref_id=slot_id, centre_id=centre_id,
                             detail="%s, %s, %d farmers" % (on, tw, cap))
                flash("Slot created.", "success")
            return redirect(url_for("admin_slots", centre_id=centre_id, date=on))

        centre_id = _my_centre() or request.args.get("centre_id") or ""
        on = request.args.get("date") or date.today().isoformat()
        args = [on]
        sql = ("SELECT s.*, c.name AS centre_name FROM slots s"
               " JOIN procurement_centres c ON c.id = s.centre_id WHERE s.date = ?")
        if centre_id:
            sql += " AND s.centre_id = ?"
            args.append(centre_id)
        sql += " ORDER BY c.name, s.time_window"
        return render_template("admin/slots.html", slots=query(sql, tuple(args)),
                               centres=_centres_visible(),
                               sel_centre=str(centre_id), sel_date=on,
                               windows=["08:00 - 10:00", "10:00 - 12:00",
                                        "12:00 - 14:00", "14:00 - 16:00", "16:00 - 18:00"])

    @app.route("/admin/centre/<int:centre_id>/delay", methods=["POST"])
    @staff_required
    def admin_set_delay(centre_id):
        """One number, set by hand when someone notices. Farmers see it with
        its age, so an old one can be judged."""
        try:
            mins = int(request.form.get("delay_minutes") or 0)
        except ValueError:
            flash("Enter the delay in whole minutes.", "error")
            return redirect(request.referrer or url_for("admin_slots"))
        mins = max(0, min(600, mins))
        if not _in_my_centre(centre_id):
            abort(403)
        old = query("SELECT delay_minutes FROM procurement_centres WHERE id = ?",
                    (centre_id,), one=True)
        if old is None:
            abort(404)
        execute("UPDATE procurement_centres SET delay_minutes = ?, delay_set_at = ?"
                " WHERE id = ?",
                (mins, datetime.now().isoformat(timespec="seconds") if mins else None,
                 centre_id))
        audit.record(g.staff, "delay_set", ref_id=centre_id, centre_id=centre_id,
                     before=old["delay_minutes"], after=mins)
        flash("Running %d minutes behind." % mins if mins else "Marked as running on time.",
              "success")
        return redirect(request.referrer or url_for("admin_slots"))

    @app.route("/admin/storage-risk")
    @staff_required
    def admin_storage_risk():
        rows = query(
            "SELECT b.*, s.date, s.time_window, s.centre_id, s.max_capacity, s.booked_count,"
            " c.name AS centre_name, c.location, c.district AS centre_district,"
            " f.name AS farmer_name, f.phone_number, f.village, f.district AS farmer_district,"
            " t.payment_status, t.total_amount, t.actual_quantity, t.quality_grade"
            " FROM bookings b"
            " JOIN slots s ON s.id = b.slot_id"
            " JOIN procurement_centres c ON c.id = s.centre_id"
            " JOIN farmers f ON f.id = b.farmer_id"
            " LEFT JOIN transactions t ON t.booking_id = b.id"
            " WHERE b.status = 'booked' AND s.date >= ?"
            + (" AND s.centre_id = ?" if _my_centre() else "") +
            " ORDER BY CASE b.storage_risk WHEN 'high' THEN 0 WHEN 'low' THEN 1 ELSE 2 END,"
            " s.date",
            (date.today().isoformat(),) + ((_my_centre(),) if _my_centre() else ()))
        return render_template("admin/storage_risk.html", rows=rows)

    # supervisor

    @app.route("/super/overview")
    @superadmin_required
    def super_overview():
        return render_template("super/overview.html", **supervisor.overview())

    @app.route("/super/attention")
    @superadmin_required
    def super_attention():
        return render_template("super/attention.html", sections=supervisor.needs_attention())

    @app.route("/super/staff", methods=["GET", "POST"])
    @superadmin_required
    def super_staff():
        form = {}
        if request.method == "POST":
            form = request.form
            error = _staff_form_error(form, new=True)
            if error:
                flash(error, "error")
            else:
                centre_id = int(form["centre_id"]) if form.get("centre_id") else None
                code = form["staff_code"].strip().upper()
                sid = execute(
                    "INSERT INTO staff (name, staff_code, password, centre_id, role, active)"
                    " VALUES (?,?,?,?,?,1)",
                    (form["name"].strip(), code, accounts.hash_password(form["password"]),
                     centre_id, form["role"]))
                audit.record(g.staff, "staff_create", ref_id=sid, centre_id=centre_id,
                             detail="%s (%s)" % (form["name"].strip(), code))
                flash("Account %s created." % code, "success")
                return redirect(url_for("super_staff_detail", staff_id=sid))
        return render_template("super/staff.html", staff=supervisor.staff_rows(),
                               centres=_centres_visible(), roles=accounts.ROLES, form=form)

    @app.route("/super/staff/<int:staff_id>", methods=["GET", "POST"])
    @superadmin_required
    def super_staff_detail(staff_id):
        person = query("SELECT st.*, c.name AS centre_name FROM staff st"
                       " LEFT JOIN procurement_centres c ON c.id = st.centre_id WHERE st.id = ?",
                       (staff_id,), one=True)
        if person is None:
            abort(404)
        if request.method == "POST":
            if request.form.get("do") == "password":
                pwd = request.form.get("password") or ""
                if len(pwd) < 6:
                    flash("A password needs at least 6 characters.", "error")
                else:
                    execute("UPDATE staff SET password = ? WHERE id = ?",
                            (accounts.hash_password(pwd), staff_id))
                    audit.record(g.staff, "password_reset", ref_id=staff_id,
                                 centre_id=person["centre_id"],
                                 detail="%s (%s)" % (person["name"], person["staff_code"]))
                    flash("Password reset for %s." % person["staff_code"], "success")
            else:
                error = _staff_form_error(request.form, new=False, person=person)
                if error:
                    flash(error, "error")
                else:
                    new = {"centre_id": int(request.form["centre_id"]) if request.form.get("centre_id") else None,
                           "role": request.form["role"],
                           "active": 1 if request.form.get("active") else 0}
                    names = {r["id"]: r["name"] for r in query("SELECT id, name FROM procurement_centres")}
                    shown = {"centre_id": lambda v: names.get(v, "No centre"),
                             "role": lambda v: "Supervisor" if v == "superadmin" else "Centre staff",
                             "active": lambda v: "On" if v else "Off"}
                    labels = {"centre_id": "Centre", "role": "Role", "active": "Account"}
                    before = {labels[k]: shown[k](person[k]) for k in new if person[k] != new[k]}
                    after = {labels[k]: shown[k](new[k]) for k in new if person[k] != new[k]}
                    if before:
                        execute("UPDATE staff SET centre_id = ?, role = ?, active = ? WHERE id = ?",
                                (new["centre_id"], new["role"], new["active"], staff_id))
                        audit.record(g.staff, "staff_update", ref_id=staff_id,
                                     centre_id=new["centre_id"], before=before, after=after,
                                     detail="%s (%s)" % (person["name"], person["staff_code"]))
                        flash("Saved.", "success")
            return redirect(url_for("super_staff_detail", staff_id=staff_id))
        return render_template("super/staff_detail.html", person=person,
                               stats=supervisor.staff_stats(staff_id),
                               entries=supervisor.activity(staff_id=staff_id, limit=100),
                               centres=_centres_visible(), roles=accounts.ROLES)

    @app.route("/super/activity")
    @superadmin_required
    def super_activity():
        def as_int(name):
            try:
                return int(request.args.get(name) or 0) or None
            except ValueError:
                return None
        days = as_int("days")
        entries = supervisor.activity(centre_id=as_int("centre_id"), staff_id=as_int("staff_id"),
                                      action=request.args.get("action") or None,
                                      days=days if days in (1, 7, 30) else None,
                                      sensitive_only=bool(request.args.get("sensitive")))
        return render_template("super/activity.html", entries=entries,
                               centres=_centres_visible(), actions=audit.ACTIONS,
                               staff=query("SELECT id, name, staff_code FROM staff ORDER BY name"),
                               sel=request.args)

    @app.route("/admin/logout")
    def admin_logout():
        session.pop("staff_id", None)
        flash("Staff signed out.", "success")
        return redirect(url_for("admin_login"))

    # The IVR runs as its own service (see farmer-ivr/). It has no database,
    # it reads everything from this feed.

    @app.route("/ivr/status.json")
    def ivr_status():
        """Everything the IVR needs about one farmer, looked up by phone."""
        phone = request.args.get("phone", "")
        farmer = query("SELECT * FROM farmers WHERE phone_number = ?", (phone,), one=True)
        if farmer is None:
            return jsonify({"found": False, "phone": phone}), 404
        bookings = query(
            _BOOKING_SELECT + " WHERE b.farmer_id = ? AND b.status IN ('booked','arrived')"
            " ORDER BY s.date", (farmer["id"],))
        txns = query(
            "SELECT t.payment_status, t.total_amount, b.token_no FROM transactions t"
            " JOIN bookings b ON b.id = t.booking_id WHERE b.farmer_id = ?"
            " ORDER BY t.id DESC LIMIT 5", (farmer["id"],))
        return jsonify({
            "found": True,
            "farmer": {"id": farmer["id"], "name": farmer["name"], "district": farmer["district"]},
            "bookings": [dict(b) for b in bookings],
            "payments": [dict(t) for t in txns],
            "open_flags": [dict(f) for f in unresolved_flags(farmer["id"])],
            "pending_voice_calls": [dict(a) for a in query(
                "SELECT * FROM alerts_log WHERE farmer_id = ? AND channel = 'ivr'"
                " ORDER BY id DESC LIMIT 10", (farmer["id"],))],
        })


    # errors

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404,
                               message="The page you asked for does not exist."), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403,
                               message="Your account can't open this page."), 403

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error.html", code=500,
                               message="Something went wrong at our end."), 500


# Shared helpers

_BOOKING_SELECT = (
    "SELECT b.*, s.date, s.time_window, s.centre_id, s.max_capacity, s.booked_count,"
    " c.name AS centre_name, c.location, c.district AS centre_district,"
    " f.name AS farmer_name, f.phone_number, f.village, f.district AS farmer_district,"
    " t.payment_status, t.total_amount, t.actual_quantity, t.quality_grade"
    " FROM bookings b"
    " JOIN slots s ON s.id = b.slot_id"
    " JOIN procurement_centres c ON c.id = s.centre_id"
    " JOIN farmers f ON f.id = b.farmer_id"
    " LEFT JOIN transactions t ON t.booking_id = b.id")


def _districts():
    return [r["district"] for r in
            query("SELECT DISTINCT district FROM procurement_centres ORDER BY district")]


def _after_write(booking_id):
    """Where to go after recording something on a booking."""
    return redirect(url_for("admin_booking", booking_id=booking_id))


def _my_centre():
    """The centre a centre-staff account is locked to. None for a supervisor,
    who sees every centre."""
    s = g.get("staff")
    if s is None or s["role"] == "superadmin":
        return None
    return s["centre_id"]


def _in_my_centre(centre_id):
    mine = _my_centre()
    return mine is None or int(centre_id) == mine


def _scoped_booking(booking_id):
    """A booking this account may act on, or a 404. Another centre's booking
    looks exactly like one that doesn't exist."""
    b = query(_BOOKING_SELECT + " WHERE b.id = ?", (booking_id,), one=True)
    if b is None or not _in_my_centre(b["centre_id"]):
        abort(404)
    return b


def _farmer_scope(alias="f"):
    """SQL limiting farmers to the ones a centre deals with: its district,
    anyone booked there, and anyone registered at its counter."""
    mine = _my_centre()
    if mine is None:
        return "1=1", ()
    return ("(%(a)s.district = (SELECT district FROM procurement_centres WHERE id = ?)"
            " OR EXISTS (SELECT 1 FROM bookings bx JOIN slots sx ON sx.id = bx.slot_id"
            "            WHERE bx.farmer_id = %(a)s.id AND sx.centre_id = ?)"
            " OR EXISTS (SELECT 1 FROM audit_log ax WHERE ax.farmer_id = %(a)s.id"
            "            AND ax.action = 'register_farmer' AND ax.centre_id = ?))" % {"a": alias},
            (mine, mine, mine))


def _farmer_visible(farmer_id):
    scope, args = _farmer_scope("f")
    return query("SELECT 1 FROM farmers f WHERE f.id = ? AND " + scope,
                 (farmer_id,) + tuple(args), one=True) is not None


def _centres_visible():
    mine = _my_centre()
    if mine is None:
        return query("SELECT * FROM procurement_centres ORDER BY name")
    return query("SELECT * FROM procurement_centres WHERE id = ?", (mine,))


def _staff_form_error(form, new, person=None):
    """What's wrong with a staff account form, or None."""
    role = form.get("role")
    if role not in accounts.ROLES:
        return "Choose a role."
    if role == "staff" and not form.get("centre_id"):
        return "Centre staff need a centre."
    if new:
        name = (form.get("name") or "").strip()
        code = (form.get("staff_code") or "").strip().upper()
        if len(name) < 3:
            return "Enter the person's name."
        if not (3 <= len(code) <= 12 and code.isalnum()):
            return "A staff code is 3 to 12 letters and numbers."
        if query("SELECT 1 FROM staff WHERE staff_code = ?", (code,), one=True):
            return "%s is already taken." % code
        if len(form.get("password") or "") < 6:
            return "A password needs at least 6 characters."
    elif person is not None and person["id"] == g.staff["id"]:
        # nobody locks themselves out of the only screen that can let them back in
        if role != "superadmin" or not form.get("active"):
            return "You can't remove your own supervisor access or switch off your own account."
    return None


def _owned_booking(booking_id):
    b = query(_BOOKING_SELECT + " WHERE b.id = ?", (booking_id,), one=True)
    if b is None or b["farmer_id"] != session.get("farmer_id"):
        abort(404)
    return b


def _create_farmer(form, registered_via):
    """Shared by self-registration and staff-assisted registration.
    Returns {error, farmer_id, problems}."""
    name = (form.get("name") or "").strip()
    phone = (form.get("phone_number") or "").strip()
    if not name or len(name) < 3:
        return {"error": "Enter the farmer's full name.", "farmer_id": None, "problems": []}
    if not phone.isdigit() or len(phone) != 10:
        return {"error": "Enter a valid 10-digit mobile number.", "farmer_id": None,
                "problems": []}
    if query("SELECT id FROM farmers WHERE phone_number = ?", (phone,), one=True):
        return {"error": "%s is already registered. Please sign in instead." % phone,
                "farmer_id": None, "problems": []}

    farmer_id = execute(
        "INSERT INTO farmers (name, phone_number, aadhaar_number, bank_account, ifsc_code,"
        " bank_name_on_account, land_record_id, village, district, registered_via, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (name, phone,
         (form.get("aadhaar_number") or "").replace(" ", "").strip(),
         (form.get("bank_account") or "").strip(),
         (form.get("ifsc_code") or "").strip().upper(),
         (form.get("bank_name_on_account") or "").strip() or name,
         (form.get("land_record_id") or "").strip().upper(),
         (form.get("village") or "").strip(),
         (form.get("district") or "").strip(),
         registered_via, datetime.now().isoformat(timespec="seconds")))

    # the checks run here, at registration - not weeks later at payout
    problems = validate_and_flag(farmer_id)
    return {"error": None, "farmer_id": farmer_id, "problems": problems}


app = create_app()

if __name__ == "__main__":
    if not os.path.exists(db.DB_PATH):
        print("No database found. Run:  python seed.py")
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
