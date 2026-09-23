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
import agristack
import audit
import core
import db
import gate
import payments
import qr
import supervisor
import villages
import voice
import weather
from core import BookingError
from db import execute, query
from i18n import t, get_lang, LANGUAGES
import voicebook
import speech_to_text
import voice_ai
import voice_register
import assistant
from urllib.parse import quote_plus
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
        "place name and no personal data, and to Vonage when members place a voice call, "
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

def _secret_key():
    """The key that signs login cookies and the gate pass QR codes.

    SECRET_KEY in .env if it is set. Otherwise one is made at random the first
    time and kept in .secret_key (never committed), so it stays the same from
    one start to the next: a pass printed yesterday still checks out at the
    gate today. The old fixed key was public on github, which let anyone
    forge a login or a gate pass on the share link."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret_key")
    if os.path.exists(path):
        with open(path) as f:
            key = f.read().strip()
        if key:
            return key
    key = os.urandom(32).hex()
    with open(path, "w") as f:
        f.write(key)
    return key


def create_app():
    app = Flask(__name__)
    # behind share_demo's cloudflare tunnel the QR codes have to carry the
    # public https address, not localhost
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    app.secret_key = _secret_key()
    # pick up edited templates without a restart. debug mode used to do this,
    # but debug is off now (its debugger must never reach the share link) and
    # a server left running kept serving the page as it was when it started
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.teardown_appcontext(db.close_db)
    db.migrate()
    app.jinja_env.globals["t"] = t
    app.jinja_env.globals["lang"] = get_lang
    app.jinja_env.globals["languages"] = LANGUAGES
    app.jinja_env.globals["icon"] = icon
    # {district: [[village, its name in the page's language], ...]} for _village_select.html
    app.jinja_env.globals["village_options"] = lambda: {
        d: [[v, t(v)] for v in names] for d, names in villages.VILLAGES.items()}
    # only base.html calls this, so a fragment rendered in between can't use it up
    app.jinja_env.globals["take_celebration"] = lambda: session.pop("celebrate", None)
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
        return "%s %s %d" % (d.strftime("%d"), t(d.strftime("%b")), d.year)

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
        # whole rupees read as whole rupees - paise only when there are some
        return ("-" if neg else "") + "₹" + whole + ("" if dec == "00" else "." + dec)

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
            dt = datetime.fromisoformat(str(value))
            return "%s %s %d, %s" % (dt.strftime("%d"), t(dt.strftime("%b")), dt.year, dt.strftime("%H:%M"))
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
            flash(t("Member sign-in required."), "warning")
            return redirect(url_for("admin_login"))
        return fn(*a, **kw)
    return wrapper


def superadmin_required(fn):
    """Supervisor screens. Centre staff get a 403 rather than a redirect -
    they are signed in, they just can't open this."""
    @wraps(fn)
    def wrapper(*a, **kw):
        if not g.get("staff"):
            session.pop("staff_id", None)
            flash(t("Superadmin sign-in required."), "warning")
            return redirect(url_for("super_login"))
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
        g.today = date.today()
        # the mock bank answers on the next page load after its delay, so
        # nothing has to run in the background
        if request.endpoint != "static":
            payments.settle_due()
        g.unread = alerts_mod.unread_count(g.farmer["id"]) if g.farmer else 0

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
        forecast = place = source = hours = None
        outlook = []
        day = request.args.get("day", "")
        if picked in districts:
            forecast, source, point = weather.get_forecast(picked, 5)
            place = point["place"] if point else picked
            # a day card was clicked: that day hour by hour, under the cards
            if forecast and day in [d["date"] for d in forecast]:
                hours = weather.get_hours(picked, day)[0]
            else:
                day = ""
        else:
            # nothing picked yet: every district at a glance instead of an empty box
            for d in districts:
                days, src, point = weather.get_forecast(d, 3)
                if not days:
                    continue
                outlook.append({"district": d, "place": point["place"] if point else d, "source": src,
                                "today": days[0], "rain_3d": round(sum(x["rain_mm"] for x in days), 1),
                                "wet_days": sum(1 for x in days if x["rain_mm"] > 0.5)})
            source = "live" if outlook and all(o["source"] == "live" for o in outlook) else ("mock" if outlook else None)
        # design_lab.py renders the same data into a trial design instead
        return render_template(g.get("home_template", "home.html"), msp=core.MSP, msp_prev=core.MSP_PREVIOUS, districts=districts, picked=picked,
                               forecast=forecast, place=place, source=source, outlook=outlook,
                               day=day, hours=hours)

    @app.route("/t/<token>")
    def token_lookup(token):
        """Where the QR on a gate pass lands when a normal camera app opens it.

        Staff get the gate screen's verdict for it, the farmer it belongs to
        gets their booking. Anyone else learns only whether the pass is
        genuine - no name, no slot - so a photographed pass tells a stranger
        nothing.
        """
        sig = request.args.get("s")
        if g.staff:
            return redirect(url_for("admin_gate", code=request.url))
        b = query("SELECT b.*, s.centre_id FROM bookings b JOIN slots s ON s.id = b.slot_id"
                  " WHERE b.token_no = ?", (token.upper(),), one=True)
        if b is not None and g.farmer and g.farmer["id"] == b["farmer_id"]:
            return redirect(url_for("farmer_booking", booking_id=b["id"]))
        return render_template("verify.html", kind="pass", genuine=qr.pass_ok(b, sig))

    @app.route("/r/<number>")
    def receipt_lookup(number):
        """Where the QR on a purchase receipt lands. Same rule as a pass."""
        txn = query("SELECT t.*, b.farmer_id FROM transactions t JOIN bookings b ON b.id = t.booking_id"
                    " WHERE t.receipt_no = ?", (number.replace("-", "/"),), one=True)
        genuine = qr.receipt_ok(txn, request.args.get("s"))
        if txn is not None and genuine:
            if g.staff:
                return redirect(url_for("admin_booking", booking_id=txn["booking_id"]))
            if g.farmer and g.farmer["id"] == txn["farmer_id"]:
                return redirect(url_for("farmer_payment", txn_id=txn["id"]))
        return render_template("verify.html", kind="receipt", genuine=genuine)

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

    def _registration(admin):
        """The registration stepper for a farmer (register.html) or at a counter
        (admin/register_farmer.html). Returns (result, None) once a farmer is
        created, or (None, the page) - first visit, a Farmer ID lookup without
        script, or a form to fix."""
        template = "admin/register_farmer.html" if admin else "register.html"
        values, lands, registry, lookup_failed, start = {}, [], None, False, 1
        if request.method == "POST":
            values = request.form.to_dict()
            lands = _lands_from(request.form)
            code = agristack.clean(values.get("agristack_id"))
            if request.form.get("lookup"):
                record = agristack.lookup(code) if code else None
                if record:
                    registry = agristack.public(record)
                    values.update(use_registry="1", agristack_id=record["farmer_id"])
                    for key in ("name", "village", "district"):
                        values[key] = values.get(key) or record[key]
                    known = {x["land_record_id"] for x in record["lands"]}
                    lands = ([dict(x, source="registry") for x in record["lands"]]
                             + [x for x in lands if x["source"] != "registry" and x["land_record_id"] not in known])
                    start = 2
                else:
                    lookup_failed = bool(code)
                    values["use_registry"] = ""
            else:
                via = (values.get("registered_via") or "staff") if admin else "self"
                result = _create_farmer(request.form, registered_via=via)
                if not result["error"]:
                    return result, None
                flash(result["error"], "error")
                start = {"farmer_id": 1, "name": 2, "phone": 2, "district": 2, "village": 2,
                         "aadhaar": 3, "land": 4}.get(result["field"], 5)
                record = agristack.lookup(code) if code and values.get("use_registry") == "1" else None
                registry = agristack.public(record) if record else None
        return None, render_template(template, form=values, lands=lands, registry=registry,
                                     lookup_failed=lookup_failed, start_step=start, districts=_districts())

    @app.route("/register", methods=["GET", "POST"])
    def register():
        """Self-service registration (the assisted/CSC path is /admin/register-farmer)."""
        result, page = _registration(admin=False)
        if page is not None:
            return page
        session["farmer_id"] = result["farmer_id"]
        problems = result["problems"]
        if problems:
            flash(t("Registered, but we found %d issue(s) in your details. "
                    "See the notice on your dashboard.") % len(problems), "warning")
        else:
            flash(t("Registration complete. Your details passed all verification checks."),
                  "success")
        return redirect(url_for("farmer_dashboard"))

    @app.route("/register/lookup")
    def registry_lookup():
        """A Farmer ID, looked up for the stepper. Never the full Aadhaar or account number."""
        record = agristack.lookup(request.args.get("farmer_id"))
        if record is None:
            return jsonify(found=False)
        if query("SELECT 1 FROM farmers WHERE agristack_id = ?", (record["farmer_id"],), one=True):
            return jsonify(found=False, message=t("This Farmer ID is already registered. Please sign in instead."))
        return jsonify(found=True, farmer=agristack.public(record),
                       shown={"village": t(record["village"]), "district": t(record["district"])})

    @app.route("/lang/<code>")
    def set_lang(code):
        if code in LANGUAGES:
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
        # the weather where this centre is: five days, and each of them hour by
        # hour, so choosing a slot can show what that day and time look like
        wx_forecast, wx_source, point = weather.get_forecast(centre["district"], 5, village=centre["location"])
        wx_forecast = wx_forecast or []
        wx_hours = {d["date"]: weather.get_hours(centre["district"], d["date"], centre["location"])[0]
                    for d in wx_forecast}
        return render_template("farmer/centre.html", centre=centre, by_date=by_date,
                               accepted=accepted, reschedule_id=request.args.get("reschedule"),
                               wx_forecast=wx_forecast, wx_by_date={d["date"]: d for d in wx_forecast},
                               wx_hours=wx_hours, wx_source=wx_source,
                               wx_place=point["place"] if point else centre["district"])

    # book by speaking. voice.js holds a spoken conversation through
    # farmer_voice_step: the portal reads the slot out and a "yes" books it.
    # every booking still goes through _book_for_farmer and its rules

    VOICE_NOTES = (
        ("already_booked_that_day", "You already have a booking that day, so this is another day."),
        ("other_day", "Nothing was free on the day you asked. This is the nearest free day."),
        ("other_time", "That time was full. This is another time on the same day."),
    )
    VOICE_PROBLEMS = {
        "limit": "You already have 3 active bookings, which is the maximum. Complete or cancel one before booking again.",
        "crop_not_bought": "That centre does not buy this crop.",
        "no_slot": "No free slot matches. Try another centre or day.",
    }

    def _is_booking(p):
        """Whether parsed words carry booking details, not just a place name."""
        return bool(p["crop"] or p["quantity"] or p["day"] or p["hours"])

    def _voice_request(text, guesses):
        """The booking request: Gemini first, the parser filling in what it missed.

        Returns (fields, question topic or None, "cancel" or None). The topic
        is None unless the farmer asked something instead of booking. The
        parser runs every time; it takes milliseconds and needs no internet,
        so when Gemini can't answer, nothing is lost.
        """
        backup = voicebook.best_parse([text] + list(guesses))
        asks_cancel = voicebook.wants_cancel(text)
        try:
            ai, intent, topic = voice_ai.understand(text, guesses, district=g.farmer["district"])
        except voice_ai.Unavailable:
            topic = voicebook.question_topic(text)
            return (backup, topic if topic and (topic == "weather" or not _is_booking(backup)) else None,
                    "cancel" if asks_cancel else None)
        if intent == "cancel" or asks_cancel:
            merged = voicebook.fill_gaps(ai, backup) if ai["heard"] else backup
            merged["text"] = backup["text"]
            return merged, None, "cancel"
        if intent == "question":
            ai["text"] = backup["text"]
            return voicebook.fill_gaps(ai, backup), topic, None
        if not ai["heard"]:
            return backup, None, None
        merged = voicebook.fill_gaps(ai, backup)
        merged["text"] = backup["text"]
        return merged, None, None

    def _voice_reply(said, parsed):
        """A reply to what was read out: (details it gives, "yes"/"no"/None, question topic or None)."""
        quick = voicebook.parse(said)
        kind = voicebook.answer_kind(said)
        # a plain haan or nahi is answered at once, without waiting on the AI
        if kind and not quick["heard"] and not voicebook.question_topic(said):
            return quick, kind, None
        so_far = ", ".join("%s: %s" % (k, parsed[k]) for k in
                           ("centre", "district", "day", "hours", "crop", "quantity") if parsed[k])
        try:
            ai, intent, topic = voice_ai.understand(
                said, context="the booking so far is %s. It read this back and asked the farmer to "
                              "confirm it or give what is missing." % (so_far or "empty"),
                district=g.farmer["district"])
        except voice_ai.Unavailable:
            topic = voicebook.question_topic(said)
            if topic and (topic == "weather" or not _is_booking(quick)):
                return quick, None, topic
            return quick, kind, None
        if intent == "question":
            return voicebook.fill_gaps(ai, quick), None, topic
        if not ai["heard"]:
            return quick, intent if intent in ("yes", "no") else kind, None
        return voicebook.fill_gaps(ai, quick), None, None

    def _voice_question_answer(topic, centre_name, crop, day=None):
        """A short spoken answer to a question asked while booking, from real data.

        Returns (words to say, a map link or None). Distances come from where
        the farmer's village and the centre are, never from the AI.
        """
        centre = query("SELECT * FROM procurement_centres WHERE name = ?", (centre_name,), one=True) \
            if centre_name else None
        directions = None
        if centre:
            directions = "https://www.google.com/maps/dir/?api=1&destination=" + quote_plus(
                "%s, %s, %s, Uttarakhand" % (centre["name"], centre["location"], centre["district"]))

        if topic in ("directions", "travel_time", "distance"):
            if not centre:
                return t("Tell me which centre, and the way will be shown."), None
            say = t("%(centre)s is at %(place)s. Tap Directions on the screen to open the map.") % {
                "centre": t(centre["name"]), "place": "%s, %s" % (t(centre["location"]), t(centre["district"]))}
            home = weather.resolve_point(g.farmer["district"], g.farmer["village"])
            there = weather.resolve_point(centre["district"], centre["location"])
            if home and there and home["precision"] == "village":
                road = weather.distance_km(home, there) * 1.3      # roads wind; straight lines don't
                if road < 1.5:
                    say += " " + t("It is very close to %s.") % t(g.farmer["village"])
                else:
                    minutes = max(5, int(round(road / 35 * 60 / 5.0)) * 5)
                    say += " " + t("From %(village)s it is about %(km)d km by road, roughly %(minutes)d minutes "
                                   "by car or motorcycle. A loaded tractor takes about twice as long.") % {
                        "village": t(g.farmer["village"]), "km": round(road), "minutes": minutes}
            elif topic != "directions":
                say += " " + t("I could not work out the exact distance from your village.")
            return say, directions
        if topic == "weather":
            # where the grain is, unless they asked about the centre they are going to
            district = centre["district"] if centre else g.farmer["district"]
            village = centre["location"] if centre else g.farmer["village"]
            card = weather.day_card(district, day or date.today().isoformat(), village)
            if card is None:
                # further off than the forecast reaches: say so, but not nothing -
                # the wait itself is what matters for grain sitting at home
                say = t("I only have the weather for the next five days.")
                risk = weather.assess_risk(g.farmer["district"], day, g.farmer["village"]) if day else None
                if risk and risk["level"] == "high":
                    say += " " + t("Heavy rain is expected before then, so keep the grain covered and off the ground.")
                elif risk and risk["level"] == "low":
                    say += " " + t("Light rain is possible before that day. Keep the grain covered.")
                return say, None
            when = voicebook.spoken_day(card["date"])
            if card["rain_mm"] >= 0.5:
                say = t("%(day)s at %(place)s: %(sky)s, about %(mm)s mm of rain, humidity %(hum)d percent.") % {
                    "day": when, "place": t(card["place"]), "sky": t(card["description"]),
                    "mm": "%g" % card["rain_mm"], "hum": int(card["humidity"])}
                say += " " + t("Keep the grain covered and off the ground.")
            else:
                say = t("%(day)s at %(place)s: %(sky)s, no rain expected, humidity %(hum)d percent.") % {
                    "day": when, "place": t(card["place"]), "sky": t(card["description"]),
                    "hum": int(card["humidity"])}
            return say, None
        if topic == "documents":
            return t("Bring your Aadhaar card, bank passbook and land record, and your token number or gate pass."), None
        if topic == "timings":
            return t("Centres weigh from 8 in the morning to 4 in the afternoon. Please arrive at the start of your slot."), None
        if topic == "price":
            if crop in core.MSP:
                return t("The support price for %(crop)s is %(price)s rupees a quintal.") % {
                    "crop": t(crop), "price": "{:,}".format(int(core.MSP[crop]))}, None
            return t("Support prices for every crop are on the home page."), None
        if topic == "payment":
            return t("Your payment goes to your bank account after your crop is weighed and the transaction is "
                     "closed. You can follow it on the Payments page."), None
        return t("I can only help with booking a slot here. For anything else, use the Help button or call "
                 "Kisan Call Centre on 1800 180 1551."), None

    def _voice_answered(topic, details, parsed, step):
        """Answer a question, then say again whatever the booking was waiting on.

        step is where the booking stood before the question, or None when the
        farmer asked before booking anything.
        """
        parsed = parsed or {}
        centre_name = details.get("centre") or parsed.get("centre")
        if not centre_name and step and step.get("proposal") and step["proposal"].get("slot"):
            centre_name = step["proposal"]["slot"]["centre_name"]
        # "us din" is the day being booked: the slot read out, else the day they named
        day = details.get("day") or parsed.get("day")
        if step and step.get("proposal") and step["proposal"].get("slot"):
            day = day or step["proposal"]["slot"]["date"]
        answer, directions = _voice_question_answer(topic, centre_name, details.get("crop") or parsed.get("crop"), day)
        if step is None:
            step = {"parsed": details, "proposal": None, "stage": "answered", "say": "", "listen": "request",
                    "repeat": False, "url": None, "slot_id": None, "token": None,
                    "prompt": t("Now tell me what you would like to book.")}
        # prompt is the booking's own question, so two questions in a row don't stack answers
        pending = step.get("prompt") or step["say"]
        step.update(say=(answer + " " + pending).strip(), prompt=pending, directions=directions,
                    repeat=False, question=topic)
        return step

    def _upcoming_bookings():
        """The farmer's bookings that could still be cancelled, soonest first."""
        return query(_BOOKING_SELECT + " WHERE b.farmer_id = ? AND b.status = 'booked' AND s.date >= ?"
                     " ORDER BY s.date, s.time_window",
                     (g.farmer["id"], date.today().isoformat()))

    def _spoken_booking(b):
        return t("%(centre)s, %(day)s, %(time)s, %(crop)s %(qty)s quintals") % {
            "centre": t(b["centre_name"]), "day": voicebook.spoken_day(b["date"]),
            "time": voicebook.spoken_window(b["time_window"]), "crop": t(b["crop_type"]),
            "qty": "%g" % b["estimated_quantity"]}

    def _pick_booking(rows, turns):
        """Which booking they mean: the only one there is, the centre or day
        they named, or the number they answered with. None when not certain."""
        if len(rows) == 1:
            return rows[0]
        for said in turns:
            p = voicebook.parse(said)
            for b in rows:
                if p["centre"] and p["centre"] == b["centre_name"]:
                    return b
                if p["day"] and p["day"] == b["date"]:
                    return b
        for said in turns[1:]:          # "dusri wali" only means anything as a reply
            n = voicebook.which_one(said, len(rows))
            if n:
                return rows[n - 1]
        return None

    def _voice_cancel_step(turns, parsed, decision):
        """Cancelling by voice.

        The booking is always read back first and only a clear yes cancels it:
        the slot goes straight back into the pool and another farmer can take
        it within seconds, so a misheard word must never be enough.
        """
        step = {"parsed": parsed, "proposal": None, "stage": None, "say": "", "listen": None,
                "repeat": False, "url": None, "slot_id": None, "token": None, "cancel": None}
        rows = _upcoming_bookings()
        if not rows:
            step.update(stage="nothing_to_cancel", say=t("You have no upcoming booking to cancel."))
            return step

        picked = _pick_booking(rows, turns)
        if picked is None:
            step.update(stage="which_booking", listen="answer", cancel={"bookings": rows},
                        say=t("You have %d bookings. Which one should I cancel?") % len(rows) + " "
                            + " ".join("%d. %s." % (i, _spoken_booking(b)) for i, b in enumerate(rows, 1)))
            return step

        # yes and no are only ever read from a reply: in the opening sentence
        # "cancel" is what they are asking for, not an answer to anything
        answer = decision if decision in ("yes", "no") else (
            voicebook.answer_kind(turns[-1]) if len(turns) > 1 else None)

        if answer == "yes":
            try:
                core.cancel_booking(picked["id"], g.farmer["id"])
            except BookingError as e:
                step.update(stage="problem", say=t(str(e)))
                return step
            execute("INSERT INTO booking_events (booking_id, kind, result, detail, at) VALUES (?,?,?,?,?)",
                    (picked["id"], "cancelled", "by the farmer", "Cancelled by voice",
                     datetime.now().isoformat(timespec="seconds")))
            alerts_mod.raise_alert(
                g.farmer["id"], "booking_confirmed", "app",
                "Your booking %s at %s on %s was cancelled. The slot is open for other farmers again."
                % (picked["token_no"], picked["centre_name"], picked["date"]),
                booking_id=picked["id"],
                message_hi="आपकी बुकिंग %s (%s, %s) रद्द कर दी गई। स्लॉट दूसरे किसानों के लिए खुल गया।"
                           % (picked["token_no"], alerts_mod.hi(picked["centre_name"]),
                              voice.spoken_date(picked["date"])))
            step.update(stage="cancelled_booking", cancel={"booking": picked},
                        url=url_for("farmer_dashboard"),
                        say=t("Cancelled. The slot is free for other farmers again.") + " "
                            + t("You can book another day whenever you are ready."))
            return step

        if answer == "no":
            step.update(stage="kept_booking", cancel={"booking": picked},
                        url=url_for("farmer_booking", booking_id=picked["id"]),
                        say=t("Nothing has been cancelled. Your booking stays as it is."))
            return step

        step.update(stage="confirm_cancel", listen="answer", cancel={"booking": picked},
                    slot_id=picked["slot_id"],
                    say=t("Your booking: %s. Shall I cancel it? Say yes or no.") % _spoken_booking(picked))
        return step

    def _voice_weather_warning(slot):
        """What to say out loud about the weather for a slot, or "".

        Two different worries: rain while the grain waits at home for a far-off
        slot (the storage risk), and rain on the day itself.
        """
        risk = weather.assess_risk(g.farmer["district"], slot["date"], g.farmer["village"])
        card = weather.day_card(slot["centre_district"], slot["date"], slot["location"])
        if risk["level"] == "high":
            return t("A warning. Heavy rain is expected while your grain waits at home. Keep it covered and "
                     "off the ground, or pick an earlier day.") + " "
        if card and card["rain_mm"] >= 0.5:
            return t("One thing. Rain is expected at %(place)s that day, so cover the load.") % {
                "place": t(card["place"])} + " "
        if risk["level"] == "low":
            return t("Light rain is possible before that day. Keep the grain covered.") + " "
        return ""

    def _voice_step(turns, guesses=(), slot_id=None, decision=None, crop=None, quantity=None):
        """One turn of the spoken booking, worked out from everything said so far.

        Nothing is kept between turns: the page sends the whole conversation
        each time. turns[0] is the request, the rest are the farmer's replies.
        decision is "yes" or "no" from a button; otherwise it comes from the
        last reply.
        """
        parsed, question, intent = _voice_request(turns[0], guesses)
        if intent == "cancel":
            return _voice_cancel_step(turns, parsed, decision)
        if question and len(turns) == 1:
            # asked something before booking anything: answer, then ask what to book
            return _voice_answered(question, parsed, None, None)
        reply = reply_kind = None
        for n, said in enumerate(turns[1:], 1):
            details, kind, question = _voice_reply(said, parsed)
            if question:
                if n == len(turns) - 1:
                    # a question in the middle of booking ("rudrapur kaise pahunchun?"):
                    # answer it, then carry on exactly where the booking was
                    before = _voice_step(turns[:-1], guesses, slot_id, None, crop, quantity)
                    return _voice_answered(question, details, before["parsed"], before)
                continue        # an earlier question: already answered, not part of the booking
            reply, reply_kind = details, kind
            if reply["heard"]:
                parsed = voicebook.merge(parsed, reply)
        # the crop and quantity boxes, if the farmer fixed them by hand before tapping yes
        if crop in core.CROPS:
            parsed["crop"] = crop
        try:
            if quantity not in (None, "") and 0 < float(quantity) <= 500:
                parsed["quantity"] = float(quantity)
        except (TypeError, ValueError):
            pass

        # a reply with booking details in it is a correction, not an answer
        stalled = reply is not None and not reply["heard"]
        if decision not in ("yes", "no"):
            decision = (reply_kind or "unclear") if stalled else None

        step = {"parsed": parsed, "proposal": None, "stage": None, "say": "", "listen": None,
                "repeat": stalled, "url": None, "slot_id": None, "token": None}

        if decision == "no":
            step.update(stage="cancelled", say=t("Okay. Nothing has been booked."))
            return step
        if not parsed["heard"]:
            step.update(stage="not_understood", listen="request", repeat=True,
                        say=t("We could not pick out any booking details from that. "
                              "Try saying the centre, day, crop and quantity."))
            return step

        proposal = voicebook.propose(parsed, g.farmer)
        step["proposal"] = proposal
        if proposal["problem"]:
            say = t(VOICE_PROBLEMS.get(proposal["problem"], VOICE_PROBLEMS["no_slot"]))
            listen = None
            if proposal["problem"] == "crop_not_bought":
                # a farmer can answer that one by naming another crop
                say += " " + t("Crops accepted") + ": " + ", ".join(t(c) for c in proposal["accepted"]) + "."
                listen = "answer"
            step.update(stage="problem", say=say, listen=listen)
            return step

        slot = proposal["slot"]
        step["slot_id"] = slot["id"]
        crop_ok = parsed["crop"] in proposal["accepted"]

        if decision == "yes" and crop_ok and parsed["quantity"]:
            try:
                # the slot that was read out, not a fresh pick the farmer never heard
                booking_id, b = _book_for_farmer(slot_id or slot["id"], parsed["crop"], parsed["quantity"])
            except (BookingError, TypeError, ValueError) as e:
                step.update(stage="problem", say=t("That slot could not be booked.") + " " + t(str(e)))
                return step
            step.update(stage="booked", token=b["token_no"], repeat=False,
                        url=url_for("farmer_booking", booking_id=booking_id),
                        say=t("Your slot is booked. Your token number is %s. Please write it down.")
                        % voicebook.spoken_token(b["token_no"])
                        + " " + _voice_weather_warning(slot))
            return step

        before = ""
        for note, sentence in VOICE_NOTES:
            if note in proposal["notes"]:
                before = t(sentence) + " "
                break
        if parsed["out_of_hours"]:
            before = t("Centres weigh between 08:00 and 16:00.") + " " + before

        if not crop_ok:
            step.update(stage="ask_crop", listen="answer",
                        say=before + t("Which crop are you bringing? This centre buys %s.")
                        % ", ".join(t(c) for c in proposal["accepted"]))
        elif not parsed["quantity"]:
            step.update(stage="ask_quantity", listen="answer",
                        say=before + t("How many quintals are you bringing?"))
        else:
            say = before + _voice_weather_warning(slot) + voicebook.confirm_sentence(slot, parsed["crop"], parsed["quantity"])
            if decision == "unclear":
                say = t("Please say yes or no.") + " " + say
            step.update(stage="confirm", listen="answer", say=say)
        return step

    CHAT_LIMIT = 30         # questions per visitor in ten minutes

    @app.route("/help/chat", methods=["POST"])
    def help_chat():
        # the help chat on public and farmer pages (assistant.py). capped per
        # visitor, so one person can't use up the free AI quota for everyone
        data = request.get_json(silent=True) or {}
        messages = []
        for m in (data.get("messages") or [])[-10:]:
            if isinstance(m, dict) and m.get("role") in ("user", "assistant") and str(m.get("text") or "").strip():
                messages.append({"role": m["role"], "text": str(m["text"]).strip()[:500]})
        while messages and messages[0]["role"] != "user":
            messages.pop(0)
        if not messages or messages[-1]["role"] != "user":
            return jsonify(error="no question"), 400
        now = datetime.now().timestamp()
        recent = [x for x in session.get("chat_times", []) if now - x < 600]
        if len(recent) >= CHAT_LIMIT:
            return jsonify(reply=t("You have asked a lot of questions. Please wait a few minutes, or call "
                                   "Kisan Call Centre on 1800-180-1551."),
                           link=None, suggestions=[], source="limit")
        session["chat_times"] = recent + [now]
        return jsonify(assistant.reply(messages, g.farmer))

    @app.route("/farmer/voice", methods=["GET", "POST"])
    @farmer_required
    def farmer_voice():
        # the same first turn as a plain form post, for typing without script
        said = (request.form.get("said") or "").strip()[:300]
        guesses = [x.strip()[:300] for x in (request.form.get("alternatives") or "").splitlines() if x.strip()][:6]
        step = None
        voice_ai.warm()     # open the connection before the farmer has finished speaking
        if request.method == "POST" and said:
            step = _voice_step([said], guesses)
            said = step["parsed"]["text"]
        return render_template("farmer/voice.html", said=said, step=step,
                               window_label=voicebook.window_label)

    @app.route("/farmer/voice/step", methods=["POST"])
    @farmer_required
    def farmer_voice_step():
        data = request.get_json(silent=True) or {}

        def texts(key, most):
            items = data.get(key)
            if not isinstance(items, list):
                return []
            return [str(x).strip()[:300] for x in items if str(x).strip()][:most]

        turns = texts("turns", 10)
        if not turns:
            return jsonify(error="nothing was said"), 400
        try:
            slot_id = int(data["slot_id"]) if data.get("slot_id") else None
        except (TypeError, ValueError):
            slot_id = None
        step = _voice_step(turns, texts("guesses", 6), slot_id, data.get("decision"),
                           data.get("crop"), data.get("quantity"))
        return jsonify(stage=step["stage"], say=step["say"], listen=step["listen"],
                       repeat=step["repeat"], url=step["url"], slot_id=step["slot_id"],
                       source=step["parsed"].get("source", "parser"),
                       html=render_template("farmer/_voice_result.html", step=step,
                                            window_label=voicebook.window_label))

    VOICE_RECORDING_TYPES = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".mp4",
                             "audio/wav": ".wav", "audio/x-wav": ".wav"}
    VOICE_RECORDING_LIMIT = 5 * 1024 * 1024     # 30 seconds of opus is well under 1 MB

    @app.route("/farmer/voice/transcribe", methods=["POST"])
    @farmer_required
    def farmer_voice_transcribe():
        return _transcribe_upload()

    def _transcribe_upload():
        # a recording from a browser with no speech recognition of its own
        audio = request.files.get("audio")
        if audio is None:
            return jsonify(error="no recording"), 400
        data = audio.read(VOICE_RECORDING_LIMIT + 1)
        if not data or len(data) > VOICE_RECORDING_LIMIT:
            return jsonify(error="recording missing or too large"), 413
        lang = request.form.get("lang", "hi")
        suffix = VOICE_RECORDING_TYPES.get((audio.mimetype or "").split(";")[0], ".webm")
        try:
            text = speech_to_text.transcribe(data, lang if lang in ("hi", "bn", "en") else "hi", suffix)
        except speech_to_text.Unavailable as e:
            app.logger.warning("voice transcribe unavailable: %s", e)
            return jsonify(error="speech to text is not set up"), 503
        except Exception:
            app.logger.exception("voice transcribe failed")
            return jsonify(error="could not read the recording"), 500
        return jsonify(text=text)

    @app.route("/farmer/voice/warm", methods=["POST"])
    @farmer_required
    def farmer_voice_warm():
        speech_to_text.warm()
        return "", 204

    # registering by speaking. public: whoever is registering isn't signed in yet

    VOICE_REG_LIMIT = 80    # answers per browser per 10 minutes - each one can cost an AI call

    def _voice_reg_allowed():
        now = datetime.now().timestamp()
        recent = [x for x in session.get("vr_times", []) if now - x < 600]
        if len(recent) >= VOICE_REG_LIMIT:
            return False
        session["vr_times"] = recent + [now]
        return True

    def _voice_reg_turn(text, guesses):
        state = session.get("voice_reg")
        if not isinstance(state, dict):
            state = voice_register.fresh()
        step = voice_register.advance(state, text, guesses)
        if step["stage"] == "done":
            result = _create_farmer(voice_register.as_form(state), registered_via="voice")
            if result["error"]:
                step = voice_register.failed(state, result)
            else:
                session.pop("voice_reg", None)
                session["farmer_id"] = result["farmer_id"]
                n = len(result["problems"])
                flash(t("Registered, but we found %d issue(s) in your details. See the notice on your dashboard.") % n
                      if n else t("Registration complete. Your details passed all verification checks."),
                      "warning" if n else "success")
                step.update(say=t("You are registered. Opening your dashboard."), listen=None, buttons=[],
                            url=url_for("farmer_dashboard"))
                return step, state
        session["voice_reg"] = state
        session.modified = True
        return step, state

    @app.route("/register/voice", methods=["GET", "POST"])
    def register_voice():
        if g.farmer:
            return redirect(url_for("farmer_dashboard"))
        if request.args.get("restart") or not isinstance(session.get("voice_reg"), dict):
            session["voice_reg"] = voice_register.fresh()
        voice_ai.warm()
        state = session["voice_reg"]
        step = voice_register.current(state)
        said = (request.form.get("said") or "").strip()[:300]
        if request.method == "POST" and said and _voice_reg_allowed():
            # the same turn as a plain form post, for typing without script
            step, state = _voice_reg_turn(said, [])
            if step["url"]:
                return redirect(step["url"])
        return render_template("register_voice.html", step=step, state=state)

    @app.route("/register/voice/step", methods=["POST"])
    def register_voice_step():
        data = request.get_json(silent=True) or {}
        turns = [str(x).strip()[:300] for x in (data.get("turns") or []) if str(x).strip()]
        if not turns:
            return jsonify(error="nothing was said"), 400
        if not _voice_reg_allowed():
            return jsonify(error="too many answers, wait a few minutes"), 429
        guesses = [str(x).strip()[:300] for x in (data.get("guesses") or []) if str(x).strip()][:5]
        step, state = _voice_reg_turn(turns[-1], guesses if len(turns) == 1 else [])
        return jsonify(stage=step["stage"], say=step["say"], listen=step["listen"], repeat=step["repeat"],
                       url=step["url"], slot_id=None, source=step["source"] or "parser",
                       html=render_template("_voice_register_step.html", step=step),
                       side=render_template("_voice_register_summary.html", state=state))

    @app.route("/register/voice/transcribe", methods=["POST"])
    def register_voice_transcribe():
        if not _voice_reg_allowed():
            return jsonify(error="too many answers, wait a few minutes"), 429
        return _transcribe_upload()

    @app.route("/register/voice/warm", methods=["POST"])
    def register_voice_warm():
        speech_to_text.warm()
        return "", 204

    def _book_for_farmer(slot_id, crop_type, quantity):
        """Book a slot for the signed-in farmer, with the alerts, storage check and message.

        Shared by the Confirm button and a spoken "yes", so both go through
        exactly the same rules. Raises BookingError, TypeError or ValueError.
        """
        booking_id = core.book_slot(g.farmer["id"], int(slot_id), crop_type, quantity)

        b = query(_BOOKING_SELECT + " WHERE b.id = ?", (booking_id,), one=True)
        alerts_mod.raise_alert(
            g.farmer["id"], "booking_confirmed", "app",
            "Slot confirmed at %s on %s, %s. Token %s. Bring this token and your "
            "Aadhaar card to the centre." % (b["centre_name"], b["date"], b["time_window"],
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
        # shown once, as the big confirmation on the next full page (base.html).
        # not a flash: the voice page renders fragments that would eat it
        session["celebrate"] = {"token": b["token_no"], "centre": b["centre_name"], "date": b["date"],
                                "window": b["time_window"], "risk": bool(risk and risk["level"] == "high")}
        return booking_id, b

    @app.route("/farmer/book", methods=["POST"])
    @farmer_required
    def farmer_book():
        try:
            booking_id, _b = _book_for_farmer(request.form.get("slot_id"), request.form.get("crop_type"),
                                              request.form.get("estimated_quantity"))
        except (BookingError, TypeError, ValueError) as e:
            flash(str(e) if isinstance(e, BookingError) else t("Invalid booking request."), "error")
            return redirect(request.form.get("back") or url_for("farmer_centres"))
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
        target = qr.pass_url(b)
        return render_template("farmer/gatepass.html", b=b, farmer=g.farmer,
                               issued=datetime.now(), qr_svg=qr.gatepass_svg(target),
                               qr_target=target)

    @app.route("/farmer/booking/<int:booking_id>/pass")
    @farmer_required
    def farmer_phone_pass(booking_id):
        """The pass on the farmer's own screen, big and bright, for anyone without a printer."""
        b = _owned_booking(booking_id)
        if b["status"] == "cancelled":
            abort(404)
        return render_template("farmer/pass.html", b=b, qr_svg=qr.gatepass_svg(qr.pass_url(b), box_size=12))

    @app.route("/farmer/payment/<int:txn_id>")
    @farmer_required
    def farmer_payment(txn_id):
        x = payments.full(txn_id)
        if x is None or x["farmer_id"] != g.farmer["id"]:
            abort(404)
        return render_template("farmer/payment.html", x=x, events=payments.events(txn_id),
                               bank=payments.bank_label(x), wait=payments.seconds_left(x),
                               returns=payments.RETURNS)

    @app.route("/farmer/booking/<int:booking_id>/receipt")
    @farmer_required
    def farmer_receipt(booking_id):
        b = _owned_booking(booking_id)
        return _receipt(b["id"], back=url_for("farmer_booking", booking_id=b["id"]))

    def _receipt(booking_id, back):
        txn = query("SELECT id FROM transactions WHERE booking_id = ?", (booking_id,), one=True)
        x = payments.full(txn["id"]) if txn else None
        if x is None or not x["receipt_no"]:
            abort(404)
        return render_template("receipt.html", x=x, bank=payments.bank_label(x), back=back,
                               qr_svg=qr.gatepass_svg(qr.receipt_url(x)), stages=payments.STAGES)

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
            place = _place_error(request.form)
            if place:
                flash(place[0], "error")
                return redirect(url_for("farmer_profile"))
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
            _save_lands(fid, _lands_from(request.form))
            problems = validate_and_flag(fid)
            if problems:
                flash(t("Saved. %d issue(s) still need attention.") % len(problems), "warning")
            else:
                flash(t("Saved. All verification checks passed - your payment will not be held up."),
                      "success")
            return redirect(url_for("farmer_profile"))
        return render_template("farmer/profile.html", farmer=g.farmer, lands=_lands_of(fid),
                               flags=unresolved_flags(fid), districts=_districts())

    # admin

    def _sign_in_staff(role, template, landing):
        """The centre staff and supervisor sign-in pages. Each lets in only its own role."""
        if request.method == "POST":
            code = (request.form.get("staff_code") or "").strip().upper()
            pwd = request.form.get("password") or ""
            s = query("SELECT * FROM staff WHERE staff_code = ?", (code,), one=True)
            # one message for a wrong code, a wrong password and a switched-off
            # account, so the form can't be used to find out which codes exist
            if s is None or not s["active"] or not accounts.check_password(s["password"], pwd):
                flash(t("Invalid member code or password."), "error")
                return render_template(template, roster=accounts.DEMO_STAFF, demo_password=accounts.DEMO_PASSWORD, code=code)
            if s["role"] != role:
                # right password, wrong door. only said once the password is
                # right, so it gives nothing away
                other = (("super_login", "superadmin sign in") if s["role"] == "superadmin"
                         else ("admin_login", "centre member sign in"))
                flash(Markup(t('This account signs in on the <a href="%s">%s</a> page.'))
                      % (url_for(other[0]), t(other[1])), "warning")
                return render_template(template, roster=accounts.DEMO_STAFF, demo_password=accounts.DEMO_PASSWORD, code=code)
            session["staff_id"] = s["id"]
            execute("UPDATE staff SET last_login = ? WHERE id = ?",
                    (datetime.now().isoformat(timespec="seconds"), s["id"]))
            audit.record(s, "sign_in")
            flash(t("Signed in as %s.") % s["name"], "success")
            return redirect(url_for(landing))
        return render_template(template, roster=accounts.DEMO_STAFF, demo_password=accounts.DEMO_PASSWORD, code="")

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        return _sign_in_staff("staff", "admin/login.html", "admin_dashboard")

    @app.route("/super/login", methods=["GET", "POST"])
    def super_login():
        return _sign_in_staff("superadmin", "super/login.html", "super_overview")

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
                               grades=core.GRADES, msp=core.MSP,
                               moisture_max=core.MOISTURE_MAX.get(b["crop_type"], 14.0),
                               foreign_faq=core.FOREIGN_FAQ, foreign_b=core.FOREIGN_B,
                               moisture_table=core.MOISTURE_MAX, grade_factor=core.GRADE_FACTOR,
                               bank_checks=payments.checks(farmer), bank=payments.bank_label(farmer),
                               stages=payments.STAGES, wait=payments.seconds_left(txn) if txn else None,
                               late=payments.is_late(txn) if txn else False,
                               returns=payments.RETURNS, visit=gate.visit(booking_id))

    @app.route("/admin/booking/<int:booking_id>/receipt")
    @staff_required
    def admin_receipt(booking_id):
        b = _scoped_booking(booking_id)
        return _receipt(b["id"], back=url_for("admin_booking", booking_id=b["id"]))

    @app.route("/admin/booking/<int:booking_id>/arrive", methods=["POST"])
    @staff_required
    def admin_arrive(booking_id):
        b = _scoped_booking(booking_id)
        if b["status"] != "booked":
            flash(t("Only a booked entry can be marked as arrived."), "error")
            return redirect(url_for("admin_booking", booking_id=booking_id))
        def number(field, low=0.0, high=None):
            v = float(request.form.get(field))
            if v < low or (high is not None and v > high):
                raise ValueError(field)
            return v

        try:
            gross = number("gross_weight")
            bags = int(number("bags", 0, 2000))
            bag_kg = number("bag_weight_kg", 0, 5)
            moisture = number("moisture", 0, 40)
            foreign = number("foreign_matter", 0, 30)
        except (TypeError, ValueError):
            flash(t("Enter the gross weight, number of bags, bag weight, moisture and foreign matter."), "error")
            return redirect(url_for("admin_booking", booking_id=booking_id))
        actual = core.net_quantity(gross, bags, bag_kg)
        if actual <= 0:
            flash(t("The bags weigh more than the gross weight. Check the readings."), "error")
            return redirect(url_for("admin_booking", booking_id=booking_id))
        grade = request.form.get("quality_grade")
        if grade not in core.GRADES:
            flash(t("Select a quality grade."), "error")
            return redirect(url_for("admin_booking", booking_id=booking_id))
        suggested = core.suggest_grade(b["crop_type"], moisture, foreign)
        note = (request.form.get("grade_note") or "").strip()
        if grade != suggested and len(note) < 5:
            flash(t("The readings suggest grade %s. Write why you picked %s.") % (suggested, grade), "error")
            return redirect(url_for("admin_booking", booking_id=booking_id))

        rate, total = core.compute_amount(b["crop_type"], actual, grade)
        now = datetime.now().isoformat(timespec="seconds")
        if not b["gate_in_at"]:
            # weighed without a gate scan - still counts as having come in
            gate.check_in(b, g.staff, note="at the weighbridge")
        execute("UPDATE bookings SET status = 'arrived' WHERE id = ?", (booking_id,))
        cols = (actual, grade, rate, total, gross, bags, bag_kg, moisture, foreign,
                note if grade != suggested else None, now)
        if query("SELECT id FROM transactions WHERE booking_id = ?", (booking_id,), one=True):
            execute("UPDATE transactions SET actual_quantity=?, quality_grade=?, price_per_unit=?, total_amount=?,"
                    " gross_weight=?, bags=?, bag_weight_kg=?, moisture=?, foreign_matter=?, grade_note=?,"
                    " weighed_at=? WHERE booking_id=?", cols + (booking_id,))
        else:
            execute("INSERT INTO transactions (actual_quantity, quality_grade, price_per_unit, total_amount,"
                    " gross_weight, bags, bag_weight_kg, moisture, foreign_matter, grade_note, weighed_at,"
                    " booking_id, payment_status, pay_stage) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'pending', 'weighed')",
                    cols + (booking_id,))
        txn_id = query("SELECT id FROM transactions WHERE booking_id = ?", (booking_id,), one=True)["id"]
        payments.log(txn_id, "weighed", "%.2f q gross, %d bags, %.2f q net, moisture %.1f%%, grade %s"
                     % (gross, bags, actual, moisture, grade), g.staff, now)
        if grade != suggested:
            audit.record(g.staff, "grade_override", farmer_id=b["farmer_id"], booking_id=booking_id,
                         centre_id=b["centre_id"], detail=note, before=suggested, after=grade)

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
        flash(t("Recorded: %.1f quintals, grade %s.") % (actual, grade), "success")
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
            flash(t("That booking was cancelled, so there is nothing to tell them. "
                  "Ring them from the farmer's page instead."), "error")
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
            flash(t("Record the weighed quantity before completing the transaction."), "error")
            return redirect(url_for("admin_booking", booking_id=booking_id))

        if b["status"] != "arrived":
            flash(t("This transaction is already closed."), "error")
            return redirect(url_for("admin_booking", booking_id=booking_id))
        execute("UPDATE bookings SET status='completed' WHERE id=?", (booking_id,))
        # receipt first, then a bill, a hold (details still wrong) or nothing to pay
        stage = payments.close(txn, b, g.staff)
        if stage == "nil":
            audit.record(g.staff, "close", farmer_id=b["farmer_id"], booking_id=booking_id,
                         centre_id=b["centre_id"], detail="Rejected, nothing payable")
            flash(t("Closed. Rejected produce, so there is nothing to pay. Receipt issued."), "success")
            return _after_write(booking_id)
        blocking = [f for f in unresolved_flags(b["farmer_id"]) if f["severity"] == "blocking"]
        if stage == "held":
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
            flash(t("Transaction closed and receipt issued, but the payment is HELD - the farmer has %d "
                  "blocking detail problem(s). Fix the record, then release it.") % len(blocking), "warning")
            return _after_write(booking_id)

        alerts_mod.raise_alert(
            b["farmer_id"], "payment_update", "app",
            "Transaction complete. Rs %s will be sent to your registered bank account in the centre's next "
            "payment batch." % format(int(txn["total_amount"] or 0), ","), booking_id=booking_id,
            message_hi="लेनदेन पूरा। ₹%d केंद्र के अगले भुगतान बैच में आपके बैंक खाते में भेजे जाएंगे।"
                       % int(txn["total_amount"] or 0))
        alerts_mod.raise_alert(
            b["farmer_id"], "payment_update", "ivr",
            "नमस्ते। आपकी उपज की खरीद पूरी हो गई है। %d रुपये केंद्र के अगले भुगतान बैच में "
            "आपके बैंक खाते में भेजे जाएंगे। धन्यवाद।"
            % int(txn["total_amount"] or 0), booking_id=booking_id)
        audit.record(g.staff, "close", farmer_id=b["farmer_id"], booking_id=booking_id,
                     centre_id=b["centre_id"], detail="Rs %s to be paid" % format(int(txn["total_amount"] or 0), ","))
        flash(t("Transaction closed. Receipt issued and the bill is ready for the next payment batch."), "success")
        return _after_write(booking_id)

    def _scoped_txn(txn_id):
        x = payments.full(txn_id)
        if x is None or not _in_my_centre(x["centre_id"]):
            abort(404)
        return x

    def _back_to(default):
        return redirect(request.form.get("back") or request.referrer or default)

    @app.route("/admin/transactions")
    @staff_required
    def admin_transactions():
        """The payment register: bills waiting for the bank, returns to fix, everything sent."""
        stage = request.args.get("stage", "")
        if stage not in payments.STAGES:
            stage = ""
        rows = payments.register(_my_centre(), stage or None)
        everything = rows if not stage else payments.register(_my_centre())
        ready = [r for r in everything if r["pay_stage"] == "billed"]
        return render_template("admin/transactions.html", rows=rows, all_rows=everything, sel_stage=stage,
                               stages=payments.STAGES, ready=ready,
                               ready_amount=sum(r["total_amount"] or 0 for r in ready),
                               returned=[r for r in everything if r["pay_stage"] == "returned"],
                               late={r["id"] for r in everything if payments.is_late(r)},
                               waiting={r["id"]: payments.seconds_left(r) for r in everything if r["pay_stage"] == "sent"},
                               batches=payments.batches(_my_centre()), returns=payments.RETURNS,
                               bank_label=payments.bank_label, credit_seconds=payments.CREDIT_SECONDS)

    @app.route("/admin/transactions.csv")
    @staff_required
    def admin_transactions_csv():
        import csv
        import io
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["Receipt", "Token", "Farmer", "Centre", "Slot date", "Crop", "Net quintals", "Grade", "Rate",
                    "Amount", "Stage", "Bill", "Batch", "UTR", "Return reason", "Attempts", "Closed", "Settled"])
        for r in payments.register(_my_centre()):
            w.writerow([r["receipt_no"] or "", r["token_no"], r["farmer_name"], r["centre_name"], r["date"],
                        r["crop_type"], r["actual_quantity"], r["quality_grade"], r["price_per_unit"],
                        r["total_amount"], payments.STAGES[r["pay_stage"]][1], r["bill_no"] or "",
                        r["batch_no"] or "", r["utr"] or "",
                        payments.RETURNS[r["return_code"]][0] if r["return_code"] else "", r["attempts"],
                        r["closed_at"] or "", r["settled_at"] or ""])
        return app.response_class(out.getvalue(), mimetype="text/csv", headers={
            "Content-Disposition": "attachment; filename=payment-register-%s.csv" % date.today().isoformat()})

    @app.route("/admin/payments/batch", methods=["POST"])
    @staff_required
    def admin_payment_batch():
        ready = [r for r in payments.register(_my_centre(), "billed")]
        batch = payments.send(ready, g.staff, _my_centre())
        if batch is None:
            flash(t("No bills are waiting for the bank."), "info")
        else:
            audit.record(g.staff, "payment_batch", ref_id=batch["id"],
                         detail="%s: %d bill%s, Rs %s" % (batch["batch_no"], batch["items"],
                                                          "s" if batch["items"] != 1 else "",
                                                          format(int(batch["amount"]), ",")))
            flash(t("Batch %s sent: %d bill(s), %s. The bank answers in about %d seconds.")
                  % (batch["batch_no"], batch["items"],
                     "Rs " + format(int(batch["amount"]), ","), payments.CREDIT_SECONDS), "toast-success")
        return _back_to(url_for("admin_transactions"))

    @app.route("/admin/transaction/<int:txn_id>/send", methods=["POST"])
    @staff_required
    def admin_payment_send(txn_id):
        """One bill now, or a returned one again once its details are fixed."""
        x = _scoped_txn(txn_id)
        if x["pay_stage"] not in ("billed", "returned"):
            flash(t("Only a bill ready for the bank or a returned payment can be sent."), "error")
            return _back_to(url_for("admin_booking", booking_id=x["booking_id"]))
        again = x["pay_stage"] == "returned"
        if again:
            failing = [c["label"] for c in payments.checks(x) if not c["ok"]]
            if failing and not request.form.get("anyway"):
                flash(t("Still failing: %s. Fix the farmer's record first, or the bank will return it again.")
                      % ", ".join(failing), "error")
                return _back_to(url_for("admin_booking", booking_id=x["booking_id"]))
        batch = payments.send([x], g.staff, x["centre_id"])
        audit.record(g.staff, "payment_resend" if again else "payment_batch", farmer_id=x["farmer_id"],
                     booking_id=x["booking_id"], ref_id=txn_id, centre_id=x["centre_id"],
                     detail="%s: Rs %s" % (batch["batch_no"], format(int(x["total_amount"] or 0), ",")))
        flash(t("Sent to the bank in %s. The answer comes in about %d seconds.")
              % (batch["batch_no"], payments.CREDIT_SECONDS), "toast-success")
        return _back_to(url_for("admin_booking", booking_id=x["booking_id"]))

    @app.route("/admin/transaction/<int:txn_id>/release", methods=["POST"])
    @staff_required
    def admin_payment_release(txn_id):
        x = _scoped_txn(txn_id)
        if payments.release(x, g.staff):
            audit.record(g.staff, "payment_release", farmer_id=x["farmer_id"], booking_id=x["booking_id"],
                         ref_id=txn_id, centre_id=x["centre_id"], detail="Rs %s" % format(int(x["total_amount"] or 0), ","))
            flash(t("Released. The bill is ready for the bank."), "success")
        else:
            flash(t("It can't be released while the farmer still has a blocking detail problem."), "error")
        return _back_to(url_for("admin_booking", booking_id=x["booking_id"]))

    @app.route("/admin/transaction/<int:txn_id>/payment", methods=["POST"])
    @staff_required
    def admin_payment(txn_id):
        """Setting a stage by hand. For when the bank's answer came some other
        way. Needs a written reason, goes in the activity log as sensitive."""
        x = _scoped_txn(txn_id)
        new = request.form.get("stage")
        reason = (request.form.get("reason") or "").strip()
        if new not in payments.STAGES:
            abort(400)
        if len(reason) < 8:
            flash(t("Write why you are changing it by hand (at least a few words)."), "error")
            return _back_to(url_for("admin_booking", booking_id=x["booking_id"]))
        if new == x["pay_stage"]:
            flash(t("It is already at that stage."), "info")
            return _back_to(url_for("admin_booking", booking_id=x["booking_id"]))
        payments.override(x, new, reason, g.staff)
        amount = int(x["total_amount"] or 0)
        if new == "credited":
            alerts_mod.raise_alert(x["farmer_id"], "payment_update", "app",
                                   "Payment of Rs %s has been credited to your bank account." % format(amount, ","),
                                   booking_id=x["booking_id"], message_hi="₹%d आपके बैंक खाते में जमा हो गए।" % amount)
        audit.record(g.staff, "payment_manual", farmer_id=x["farmer_id"], booking_id=x["booking_id"],
                     ref_id=txn_id, centre_id=x["centre_id"], detail="Rs %s - %s" % (format(amount, ","), reason),
                     before=payments.STAGES[x["pay_stage"]][1], after=payments.STAGES[new][1])
        flash(t("Stage set to '%s' by hand. This shows in the superadmin's activity log.") % t(payments.STAGES[new][1]),
              "warning")
        return _back_to(url_for("admin_booking", booking_id=x["booking_id"]))

    # the gate

    @app.route("/admin/gate")
    @staff_required
    def admin_gate():
        """Scan a pass with the phone's camera, or type the token."""
        code = request.args.get("code", "")
        result = _gate_result(code) if code else None
        return render_template("admin/gate.html", stats=gate.today(_my_centre()), result=result, code=code)

    def _gate_result(code):
        token, sig = gate.parse_code(code)
        b = gate.find(token) if token else None
        # typed by hand has nothing to check. a real pass for a cancelled
        # booking is still genuine - the verdict then says cancelled, not fake
        genuine = None if sig is None else qr.pass_signed(b, sig)
        v = gate.verdict(b, genuine, _my_centre())
        gate.log_scan(b, g.staff, v, _my_centre())
        return {"v": v, "b": b, "code": code, "genuine": genuine}

    @app.route("/admin/gate/check", methods=["POST"])
    @staff_required
    def admin_gate_check():
        r = _gate_result((request.get_json(silent=True) or {}).get("code") or request.form.get("code", ""))
        return jsonify({"tone": r["v"]["tone"], "html": render_template("admin/_gate_result.html", r=r)})

    @app.route("/admin/gate/act", methods=["POST"])
    @staff_required
    def admin_gate_act():
        data = request.get_json(silent=True) or request.form
        token, sig = gate.parse_code(data.get("code", ""))
        b = gate.find(token) if token else None
        if b is None or not _in_my_centre(b["centre_id"]):
            abort(404)
        if sig is not None and not qr.pass_signed(b, sig):
            abort(403)
        action = data.get("action")
        if action in ("checkin", "checkin_anyway") and b["status"] == "booked" and not b["gate_in_at"]:
            note = (data.get("note") or "").strip() if action == "checkin_anyway" else None
            if action == "checkin_anyway" and len(note or "") < 3:
                return jsonify({"error": "Write a short reason for letting them in."}), 400
            gate.check_in(b, g.staff, note=note)
        elif action == "checkout" and b["status"] == "completed" and not b["gate_out_at"]:
            gate.check_out(b, g.staff)
        else:
            return jsonify({"error": "Nothing to do for this pass now."}), 400
        b = gate.find(token)
        v = gate.verdict(b, True if sig else None, _my_centre())
        r = {"v": v, "b": b, "code": data.get("code", ""), "genuine": True if sig else None, "done": action}
        return jsonify({"tone": v["tone"], "html": render_template("admin/_gate_result.html", r=r)})

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
                               "Your '%s' detail has been verified and corrected by centre members."
                               % f["field_flagged"],
                               message_hi="आपकी %s की जानकारी केंद्र ने जांचकर सही कर दी है।"
                               % {"aadhaar": "आधार", "bank": "बैंक", "land": "भूमि रिकॉर्ड",
                                  "name_match": "नाम"}.get(f["field_flagged"], f["field_flagged"]))
        audit.record(g.staff, "flag_verified", farmer_id=f["farmer_id"], ref_id=flag_id,
                     detail="%s: %s" % (f["field_flagged"], f["detail"]))
        flash(t("Flag marked resolved."), "success")
        return redirect(request.referrer or url_for("admin_flags"))

    @app.route("/admin/farmer/<int:farmer_id>", methods=["GET", "POST"])
    @staff_required
    def admin_farmer(farmer_id):
        farmer = query("SELECT * FROM farmers WHERE id = ?", (farmer_id,), one=True)
        if farmer is None or not _farmer_visible(farmer_id):
            abort(404)
        if request.method == "POST":
            place = _place_error(request.form)
            if place:
                flash(place[0], "error")
                return redirect(url_for("admin_farmer", farmer_id=farmer_id))
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
            seeded = 1 if request.form.get("aadhaar_seeded") else 0
            if seeded != farmer["aadhaar_seeded"]:
                execute("UPDATE farmers SET aadhaar_seeded = ? WHERE id = ?", (seeded, farmer_id))
                audit.record(g.staff, "id_edit", farmer_id=farmer_id, detail="Aadhaar linked to bank account",
                             before="yes" if farmer["aadhaar_seeded"] else "no", after="yes" if seeded else "no")
            _save_lands(farmer_id, _lands_from(request.form))
            changed, before, after = audit.farmer_diff(farmer, request.form)
            if changed:
                audit.record(g.staff, "id_edit" if audit.touches_id(changed) else "record_edit",
                             farmer_id=farmer_id, before=before, after=after,
                             detail=", ".join(audit.FIELD_LABELS[k] for k in changed))
            problems = validate_and_flag(farmer_id)
            flash(t("Details updated. %s") % (t("%d issue(s) remain.") % len(problems) if problems
                                           else t("All checks now pass.")),
                  "warning" if problems else "success")
            return redirect(url_for("admin_farmer", farmer_id=farmer_id))
        bookings = query(_BOOKING_SELECT + " WHERE b.farmer_id = ? ORDER BY s.date DESC",
                         (farmer_id,))
        return render_template("admin/farmer.html", farmer=farmer, bookings=bookings, lands=_lands_of(farmer_id),
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
        farmers = query(sql, tuple(args))
        if request.args.get("partial"):
            # the live search on the page asks for just the list
            return render_template("admin/_farmer_rows.html", farmers=farmers, q=q)
        return render_template("admin/farmers.html", farmers=farmers, q=q)

    @app.route("/admin/register-farmer", methods=["GET", "POST"])
    @staff_required
    def admin_register_farmer():
        """Assisted / CSC registration path (spec 4.1), the same stepper as a farmer's."""
        result, page = _registration(admin=True)
        if page is not None:
            return page
        audit.record(g.staff, "register_farmer", farmer_id=result["farmer_id"],
                     detail="CSC operator" if request.form.get("registered_via") == "csc"
                     else "At the counter")
        n = len(result["problems"])
        flash(t("Farmer registered. %s") % (t("%d verification issue(s) flagged for follow-up.") % n
                                         if n else t("All verification checks passed.")),
              "warning" if n else "success")
        return redirect(url_for("admin_farmer", farmer_id=result["farmer_id"]))

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
                flash(t("Fill in centre, date and capacity correctly."), "error")
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
                flash(t("Capacity updated for that slot."), "success")
            else:
                slot_id = execute("INSERT INTO slots (centre_id, date, time_window, max_capacity,"
                                  " booked_count) VALUES (?,?,?,?,0)", (centre_id, on, tw, cap))
                audit.record(g.staff, "slot_create", ref_id=slot_id, centre_id=centre_id,
                             detail="%s, %s, %d farmers" % (on, tw, cap))
                flash(t("Slot created."), "success")
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
            flash(t("Enter the delay in whole minutes."), "error")
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
        flash(t("Running %d minutes behind.") % mins if mins else t("Marked as running on time."),
              "success")
        return redirect(request.referrer or url_for("admin_slots"))

    @app.route("/admin/storage-risk")
    @staff_required
    def admin_storage_risk():
        # offering an earlier slot is done at the centre, by the people who
        # know which slots they can open. the supervisor does not work this list
        if g.staff["role"] == "superadmin":
            flash(t("Storage risk is handled by centre members."), "info")
            return redirect(url_for("super_overview"))
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
                flash(t("Account %s created.") % code, "success")
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
                    flash(t("A password needs at least 6 characters."), "error")
                else:
                    execute("UPDATE staff SET password = ? WHERE id = ?",
                            (accounts.hash_password(pwd), staff_id))
                    audit.record(g.staff, "password_reset", ref_id=staff_id,
                                 centre_id=person["centre_id"],
                                 detail="%s (%s)" % (person["name"], person["staff_code"]))
                    flash(t("Password reset for %s.") % person["staff_code"], "success")
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
                             "role": lambda v: "Superadmin" if v == "superadmin" else "Centre member",
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
                        flash(t("Saved."), "success")
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
        # back to the page they signed in on
        supervisor = bool(g.get("staff")) and g.staff["role"] == "superadmin"
        session.pop("staff_id", None)
        flash(t("Member signed out."), "success")
        return redirect(url_for("super_login" if supervisor else "admin_login"))

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
            "SELECT t.payment_status, t.pay_stage, t.utr, t.return_code, t.total_amount, b.token_no"
            " FROM transactions t"
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
    " t.payment_status, t.total_amount, t.actual_quantity, t.quality_grade, t.pay_stage, t.id AS txn_id,"
    " t.receipt_no"
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
        return "Centre members need a centre."
    if new:
        name = (form.get("name") or "").strip()
        code = (form.get("staff_code") or "").strip().upper()
        if len(name) < 3:
            return "Enter the person's name."
        if not (3 <= len(code) <= 12 and code.isalnum()):
            return "A member code is 3 to 12 letters and numbers."
        if query("SELECT 1 FROM staff WHERE staff_code = ?", (code,), one=True):
            return "%s is already taken." % code
        if len(form.get("password") or "") < 6:
            return "A password needs at least 6 characters."
    elif person is not None and person["id"] == g.staff["id"]:
        # nobody locks themselves out of the only screen that can let them back in
        if role != "superadmin" or not form.get("active"):
            return "You can't remove your own superadmin access or switch off your own account."
    return None


def _owned_booking(booking_id):
    b = query(_BOOKING_SELECT + " WHERE b.id = ?", (booking_id,), one=True)
    if b is None or b["farmer_id"] != session.get("farmer_id"):
        abort(404)
    return b


def _lands_from(form):
    """The land rows a form posted. One farmer, one Aadhaar, as many parcels as they farm."""
    ids, villages = form.getlist("land_record_id"), form.getlist("land_village")
    areas, sources = form.getlist("land_area"), form.getlist("land_source")
    out, seen = [], set()
    for i, raw in enumerate(ids):
        record = (raw or "").strip().upper()
        if not record or record in seen:
            continue
        seen.add(record)
        try:
            area = round(float(areas[i]), 2) if i < len(areas) and str(areas[i]).strip() else None
        except ValueError:
            area = None
        out.append({"land_record_id": record,
                    "village": (villages[i] if i < len(villages) else "").strip(),
                    "area_acres": area,
                    "source": sources[i] if i < len(sources) and sources[i] in ("registry", "manual") else "manual"})
    return out


def _lands_of(farmer_id):
    return [dict(r) for r in query("SELECT * FROM farmer_lands WHERE farmer_id = ? ORDER BY id", (farmer_id,))]


def _save_lands(farmer_id, lands):
    """Replace a farmer's land rows. The first one also goes on the farmer
    record, for the screens that show a single land record."""
    now = datetime.now().isoformat(timespec="seconds")
    farmer = query("SELECT district FROM farmers WHERE id = ?", (farmer_id,), one=True)
    execute("DELETE FROM farmer_lands WHERE farmer_id = ?", (farmer_id,))
    for land in lands:
        execute("INSERT INTO farmer_lands (farmer_id, land_record_id, village, district, area_acres, source, added_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (farmer_id, land["land_record_id"], land.get("village") or "",
                 land.get("district") or (farmer["district"] if farmer else ""), land.get("area_acres"),
                 land.get("source") or "manual", now))
    execute("UPDATE farmers SET land_record_id = ? WHERE id = ?",
            (lands[0]["land_record_id"] if lands else "", farmer_id))


def _place_error(form):
    """(message, field) when the district, the village or a land record's
    village isn't one from the lists, else None. The page only offers listed
    ones; this stops a hand-made post."""
    district = (form.get("district") or "").strip()
    if district not in villages.VILLAGES:
        return t("Select your district."), "district"
    if not villages.valid(district, (form.get("village") or "").strip()):
        return t("Select your village from the list for %s.") % t(district), "village"
    for land in _lands_from(form):
        if land["village"] and not villages.valid(district, land["village"]):
            return t("Select the village of land record %s from the list.") % land["land_record_id"], "land"
    return None


def _create_farmer(form, registered_via):
    """Shared by the registration stepper, a counter's assisted registration
    and registering by voice. Returns {error, field, farmer_id, problems} -
    field names the step an error belongs to.

    With a Farmer ID and use_registry=1, the Aadhaar and bank details come
    from the registry itself, not from the form: the page only ever saw the
    last four digits."""
    def fail(message, field):
        return {"error": message, "field": field, "farmer_id": None, "problems": []}

    name = (form.get("name") or "").strip()
    phone = (form.get("phone_number") or "").strip()
    if not name or len(name) < 3:
        return fail(t("Enter the farmer's full name."), "name")
    if not phone.isdigit() or len(phone) != 10:
        return fail(t("Enter a valid 10-digit mobile number."), "phone")
    if query("SELECT id FROM farmers WHERE phone_number = ?", (phone,), one=True):
        return fail(t("%s is already registered. Please sign in instead.") % phone, "phone")
    place = _place_error(form)
    if place:
        return fail(*place)

    code = agristack.clean(form.get("agristack_id"))
    record = None
    if code:
        record = agristack.lookup(code)
        if record is None:
            return fail(t("No farmer record found for Farmer ID %s. Check the number, or leave it empty "
                          "and fill in the details yourself.") % code, "farmer_id")
        if query("SELECT 1 FROM farmers WHERE agristack_id = ?", (code,), one=True):
            return fail(t("Farmer ID %s is already registered. Please sign in instead.") % code, "farmer_id")

    if record is not None and form.get("use_registry") == "1":
        aadhaar, account, ifsc = record["aadhaar"], record["bank_account"], record["ifsc"]
        on_account, seeded = record["name_on_account"], record["aadhaar_seeded"]
    else:
        aadhaar = (form.get("aadhaar_number") or "").replace(" ", "").strip()
        account = (form.get("bank_account") or "").strip()
        ifsc = (form.get("ifsc_code") or "").strip().upper()
        on_account, seeded = (form.get("bank_name_on_account") or "").strip() or name, 1

    # one Aadhaar is one farmer. more land goes on the account they already have
    if aadhaar:
        other = query("SELECT phone_number FROM farmers WHERE aadhaar_number = ?", (aadhaar,), one=True)
        if other:
            return fail(t("This Aadhaar number is already registered, with the mobile number ending %s. Sign in "
                          "with that number - you can add more land records on My Details.")
                        % other["phone_number"][-2:], "aadhaar")

    lands = _lands_from(form)
    farmer_id = execute(
        "INSERT INTO farmers (name, phone_number, aadhaar_number, bank_account, ifsc_code,"
        " bank_name_on_account, land_record_id, agristack_id, aadhaar_seeded, village, district,"
        " registered_via, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (name, phone, aadhaar, account, ifsc, on_account,
         lands[0]["land_record_id"] if lands else "", code or None, seeded,
         (form.get("village") or "").strip(),
         (form.get("district") or "").strip(),
         registered_via, datetime.now().isoformat(timespec="seconds")))
    _save_lands(farmer_id, lands)

    # the checks run here, at registration - not weeks later at payout
    problems = validate_and_flag(farmer_id)
    return {"error": None, "field": None, "farmer_id": farmer_id, "problems": problems}


app = create_app()

if __name__ == "__main__":
    if not os.path.exists(db.DB_PATH):
        print("No database found. Run:  python seed.py")
    # the debugger runs code typed into a browser, so it stays off unless
    # asked for: never on the public share link. FLASK_DEBUG=1 in .env for development
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="0.0.0.0",
            port=int(os.environ.get("PORT", 5000)))
