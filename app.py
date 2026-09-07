"""Main flask app - all the routes live here.

SIH 2026, PS 26032.

The IVR part is not built yet, there is just a stub under /ivr that the
other team member can build on top of.

Login is kept simple for now, OTP is hardcoded and staff share one password.
TODO: real OTP + hash the staff passwords
"""

import os
import random
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)

import alerts as alerts_mod
import core
import db
import voice
import weather
from core import BookingError
from db import execute, query
from i18n import t, get_lang
from validation import unresolved_flags, validate_and_flag

# hardcoded otp, shown on the login page
DEMO_OTP = "123456"

# Outbound calls go straight from here to vonage, no second server involved.


# App factory

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "sih-2026-ps26032-demo-key")
    app.teardown_appcontext(db.close_db)
    app.jinja_env.globals["t"] = t
    app.jinja_env.globals["lang"] = get_lang
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
        if not session.get("staff_id"):
            flash("Staff sign-in required.", "warning")
            return redirect(url_for("admin_login"))
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
        " LEFT JOIN procurement_centres c ON c.id = s.centre_id WHERE s.id = ?",
        (sid,), one=True)


# Routes

def register_routes(app):

    @app.before_request
    def _load_user():
        g.farmer = current_farmer()
        g.staff = current_staff()
        g.unread = alerts_mod.unread_count(g.farmer["id"]) if g.farmer else 0
        g.today = date.today()

    # public

    @app.route("/")
    def home():
        stats = {
            "centres": query("SELECT COUNT(*) c FROM procurement_centres", one=True)["c"],
            "farmers": query("SELECT COUNT(*) c FROM farmers", one=True)["c"],
            "bookings": query("SELECT COUNT(*) c FROM bookings", one=True)["c"],
            "slots_open": query(
                "SELECT COALESCE(SUM(max_capacity - booked_count),0) c FROM slots"
                " WHERE date >= ?", (date.today().isoformat(),), one=True)["c"],
        }
        return render_template("home.html", stats=stats)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            phone = (request.form.get("phone") or "").strip()
            farmer = query("SELECT * FROM farmers WHERE phone_number = ?", (phone,), one=True)
            if farmer is None:
                flash("No farmer is registered with %s. Please register first." % phone, "error")
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
                flash("Incorrect OTP. For this demo the OTP is always %s." % DEMO_OTP, "error")
            else:
                session.pop("pending_phone", None)
                session["farmer_id"] = farmer["id"]
                flash("Signed in as %s." % farmer["name"], "success")
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
                flash("Registered, but we found %d issue(s) in your details. "
                      "See the notice on your dashboard." % len(problems), "warning")
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
        sql = ("SELECT c.*, "
               " (SELECT COALESCE(SUM(s.max_capacity - s.booked_count),0) FROM slots s"
               "   WHERE s.centre_id = c.id AND s.date >= ?) AS open_slots"
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
            flash(str(e) if isinstance(e, BookingError) else "Invalid booking request.", "error")
            return redirect(request.form.get("back") or url_for("farmer_centres"))

        b = query(_BOOKING_SELECT + " WHERE b.id = ?", (booking_id,), one=True)
        alerts_mod.raise_alert(
            g.farmer["id"], "booking_confirmed", "app",
            "Slot confirmed at %s on %s, %s. Token %s. Bring this token and your "
            "registration ID to the centre." % (b["centre_name"], b["date"], b["time_window"],
                                                b["token_no"]),
            booking_id=booking_id)
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
            flash("Booking confirmed. Your token is %s." % b["token_no"], "success")
        return redirect(url_for("farmer_booking", booking_id=booking_id))

    @app.route("/farmer/booking/<int:booking_id>")
    @farmer_required
    def farmer_booking(booking_id):
        b = _owned_booking(booking_id)
        txn = query("SELECT * FROM transactions WHERE booking_id = ?", (booking_id,), one=True)
        risk = None
        if b["status"] == "booked":
            risk = weather.assess_risk(g.farmer["district"], b["date"])
        return render_template("farmer/booking.html", b=b, txn=txn, risk=risk)

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
                booking_id=booking_id)
            flash("Slot rescheduled to %s, %s." % (b["date"], b["time_window"]), "success")
        except (BookingError, TypeError, ValueError) as e:
            flash(str(e) if isinstance(e, BookingError) else "Invalid slot.", "error")
        return redirect(url_for("farmer_booking", booking_id=booking_id))

    @app.route("/farmer/booking/<int:booking_id>/gatepass")
    @farmer_required
    def farmer_gatepass(booking_id):
        b = _owned_booking(booking_id)
        return render_template("farmer/gatepass.html", b=b, farmer=g.farmer,
                               issued=datetime.now())

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
                flash("Saved. %d issue(s) still need attention." % len(problems), "warning")
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
            # TODO: constant-time hash comparison in production.
            if s is None or s["password"] != pwd:
                flash("Invalid staff code or password.", "error")
                return render_template("admin/login.html", code=code)
            session["staff_id"] = s["id"]
            flash("Signed in as %s." % s["name"], "success")
            return redirect(url_for("admin_dashboard"))
        return render_template("admin/login.html", code="")

    @app.route("/admin/dashboard")
    @staff_required
    def admin_dashboard():
        centre_id = request.args.get("centre_id") or (g.staff["centre_id"] or "")
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
        summary["flags"] = query(
            "SELECT COUNT(*) c FROM data_validation_flags WHERE status='unresolved'",
            one=True)["c"]
        summary["risk"] = query(
            "SELECT COUNT(*) c FROM bookings WHERE storage_risk='high' AND status='booked'",
            one=True)["c"]

        return render_template("admin/dashboard.html", bookings=bookings,
                               centres=query("SELECT * FROM procurement_centres ORDER BY name"),
                               sel_centre=str(centre_id), sel_date=dt, sel_status=status,
                               summary=summary)

    @app.route("/admin/booking/<int:booking_id>")
    @staff_required
    def admin_booking(booking_id):
        b = query(_BOOKING_SELECT + " WHERE b.id = ?", (booking_id,), one=True)
        if b is None:
            abort(404)
        txn = query("SELECT * FROM transactions WHERE booking_id = ?", (booking_id,), one=True)
        farmer = query("SELECT * FROM farmers WHERE id = ?", (b["farmer_id"],), one=True)
        return render_template("admin/booking.html", b=b, txn=txn, farmer=farmer,
                               flags=unresolved_flags(b["farmer_id"]),
                               grades=core.GRADES, msp=core.MSP)

    @app.route("/admin/booking/<int:booking_id>/arrive", methods=["POST"])
    @staff_required
    def admin_arrive(booking_id):
        b = query("SELECT * FROM bookings WHERE id = ?", (booking_id,), one=True)
        if b is None:
            abort(404)
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
            % (actual, b["crop_type"], grade, total), booking_id=booking_id)
        flash("Recorded: %.1f quintals, grade %s." % (actual, grade), "success")
        return redirect(url_for("admin_booking", booking_id=booking_id))

    @app.route("/admin/booking/<int:booking_id>/complete", methods=["POST"])
    @staff_required
    def admin_complete(booking_id):
        b = query("SELECT * FROM bookings WHERE id = ?", (booking_id,), one=True)
        txn = query("SELECT * FROM transactions WHERE booking_id = ?", (booking_id,), one=True)
        if b is None or txn is None:
            flash("Record the weighed quantity before completing the transaction.", "error")
            return redirect(url_for("admin_booking", booking_id=booking_id))

        # don't let the payment go through if their details are still wrong
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
                booking_id=booking_id)
            flash("Transaction closed, but payment marked FAILED - farmer has %d unresolved "
                  "blocking flag(s)." % len(blocking), "warning")
            return redirect(url_for("admin_booking", booking_id=booking_id))

        execute("UPDATE bookings SET status='completed' WHERE id=?", (booking_id,))
        execute("UPDATE transactions SET payment_status='processing' WHERE booking_id=?",
                (booking_id,))
        alerts_mod.raise_alert(
            b["farmer_id"], "payment_update", "app",
            "Transaction complete. %.2f is being credited to your registered bank account. "
            "Expect credit within 48-72 hours." % txn["total_amount"], booking_id=booking_id)
        alerts_mod.raise_alert(
            b["farmer_id"], "payment_update", "ivr",
            "नमस्ते। आपकी उपज की खरीद पूरी हो गई है। %d रुपये का भुगतान प्रक्रिया में है "
            "और दो से तीन दिन में आपके बैंक खाते में जमा हो जाएगा। धन्यवाद।"
            % int(txn["total_amount"] or 0), booking_id=booking_id)
        flash("Transaction completed. Payment moved to 'processing'.", "success")
        return redirect(url_for("admin_booking", booking_id=booking_id))

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
        if g.staff["centre_id"]:
            sql += " AND c.id = ?"
            args.append(g.staff["centre_id"])
        sql += " ORDER BY s.date DESC, t.id DESC"
        return render_template("admin/transactions.html", rows=query(sql, tuple(args)),
                               sel_status=status)

    @app.route("/admin/transaction/<int:txn_id>/payment", methods=["POST"])
    @staff_required
    def admin_payment(txn_id):
        new = request.form.get("payment_status")
        if new not in ("pending", "processing", "completed", "failed"):
            abort(400)
        t = query("SELECT t.*, b.farmer_id FROM transactions t JOIN bookings b"
                  " ON b.id = t.booking_id WHERE t.id = ?", (txn_id,), one=True)
        if t is None:
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
        alerts_mod.raise_alert(t["farmer_id"], "payment_update", "app", msg,
                               booking_id=t["booking_id"])
        flash("Payment status set to '%s'." % new, "success")
        return redirect(request.referrer or url_for("admin_transactions"))

    @app.route("/admin/flags")
    @staff_required
    def admin_flags():
        show = request.args.get("status", "unresolved")
        sql = ("SELECT d.*, f.name AS farmer_name, f.phone_number, f.district"
               " FROM data_validation_flags d JOIN farmers f ON f.id = d.farmer_id")
        args = []
        if show in ("unresolved", "resolved"):
            sql += " WHERE d.status = ?"
            args.append(show)
        sql += " ORDER BY CASE d.severity WHEN 'blocking' THEN 0 ELSE 1 END, d.farmer_id"
        return render_template("admin/flags.html", flags=query(sql, tuple(args)), sel_status=show)

    @app.route("/admin/flag/<int:flag_id>/resolve", methods=["POST"])
    @staff_required
    def admin_resolve_flag(flag_id):
        f = query("SELECT * FROM data_validation_flags WHERE id = ?", (flag_id,), one=True)
        if f is None:
            abort(404)
        execute("UPDATE data_validation_flags SET status='resolved', resolved_at=? WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"), flag_id))
        alerts_mod.raise_alert(f["farmer_id"], "data_mismatch", "app",
                               "Your '%s' detail has been verified and corrected by centre staff."
                               % f["field_flagged"])
        flash("Flag marked resolved.", "success")
        return redirect(request.referrer or url_for("admin_flags"))

    @app.route("/admin/farmer/<int:farmer_id>", methods=["GET", "POST"])
    @staff_required
    def admin_farmer(farmer_id):
        farmer = query("SELECT * FROM farmers WHERE id = ?", (farmer_id,), one=True)
        if farmer is None:
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
        sql = ("SELECT f.*, "
               " (SELECT COUNT(*) FROM data_validation_flags d WHERE d.farmer_id = f.id"
               "   AND d.status='unresolved') AS flag_count,"
               " (SELECT COUNT(*) FROM bookings b WHERE b.farmer_id = f.id) AS booking_count"
               " FROM farmers f WHERE 1=1")
        args = []
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
            tw = request.form.get("time_window")
            existing = query("SELECT id FROM slots WHERE centre_id=? AND date=? AND time_window=?",
                             (centre_id, on, tw), one=True)
            if existing:
                execute("UPDATE slots SET max_capacity=? WHERE id=?", (cap, existing["id"]))
                flash("Capacity updated for that slot.", "success")
            else:
                execute("INSERT INTO slots (centre_id, date, time_window, max_capacity,"
                        " booked_count) VALUES (?,?,?,?,0)", (centre_id, on, tw, cap))
                flash("Slot created.", "success")
            return redirect(url_for("admin_slots", centre_id=centre_id, date=on))

        centre_id = request.args.get("centre_id") or (g.staff["centre_id"] or "")
        on = request.args.get("date") or date.today().isoformat()
        args = [on]
        sql = ("SELECT s.*, c.name AS centre_name FROM slots s"
               " JOIN procurement_centres c ON c.id = s.centre_id WHERE s.date = ?")
        if centre_id:
            sql += " AND s.centre_id = ?"
            args.append(centre_id)
        sql += " ORDER BY c.name, s.time_window"
        return render_template("admin/slots.html", slots=query(sql, tuple(args)),
                               centres=query("SELECT * FROM procurement_centres ORDER BY name"),
                               sel_centre=str(centre_id), sel_date=on,
                               windows=["08:00 - 10:00", "10:00 - 12:00",
                                        "12:00 - 14:00", "14:00 - 16:00", "16:00 - 18:00"])

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
            " ORDER BY CASE b.storage_risk WHEN 'high' THEN 0 WHEN 'low' THEN 1 ELSE 2 END,"
            " s.date", (date.today().isoformat(),))
        return render_template("admin/storage_risk.html", rows=rows)

    @app.route("/admin/demo", methods=["GET", "POST"])
    @staff_required
    def admin_demo():
        """Buttons for the demo so we can trigger things on stage."""
        result = None
        if request.method == "POST":
            action = request.form.get("action")
            if action == "toggle_risk":
                weather.DEMO_FORCE_RISK["on"] = not weather.DEMO_FORCE_RISK["on"]
                flash("Storage-risk override is now %s."
                      % ("ON - every check returns HIGH" if weather.DEMO_FORCE_RISK["on"]
                         else "OFF - real rules apply"), "success")
            elif action == "rescan_risk":
                res = weather.rescan_all_upcoming()
                high = sum(1 for r in res if r and r["level"] == "high")
                flash("Re-scanned %d upcoming bookings. %d flagged HIGH risk."
                      % (len(res), high), "success")
            elif action == "revalidate":
                ids = [r["id"] for r in query("SELECT id FROM farmers")]
                flagged = sum(1 for i in ids if validate_and_flag(i))
                flash("Re-validated %d farmers. %d have open issues." % (len(ids), flagged),
                      "success")
            elif action == "advance_payments":
                rows = query("SELECT id FROM transactions WHERE payment_status = 'processing'")
                for r in rows:
                    execute("UPDATE transactions SET payment_status='completed', payment_date=?"
                            " WHERE id=?", (datetime.now().isoformat(timespec="seconds"), r["id"]))
                flash("Settled %d in-flight payments." % len(rows), "success")
            elif action == "set_test_number":
                num = "".join(c for c in (request.form.get("test_number") or "") if c.isdigit())
                if num:
                    session["voice_test_number"] = num
                    flash("Demo calls will now go to %s instead of the farmer's real number."
                          % num, "success")
                else:
                    session.pop("voice_test_number", None)
                    flash("Cleared. Demo calls will use each farmer's own number again.",
                          "success")
            elif action == "place_call":
                alert = query(
                    "SELECT a.*, f.name, f.phone_number FROM alerts_log a"
                    " JOIN farmers f ON f.id = a.farmer_id WHERE a.id = ?",
                    (request.form.get("alert_id"),), one=True)
                if alert is None:
                    flash("That queued call no longer exists.", "error")
                else:
                    # If a test number is set we ring that instead, and treat it as
                    # deliberate so the allowlist doesn't block it.
                    test_to = session.get("voice_test_number")
                    to = test_to or alert["phone_number"]
                    ok, detail = voice.place_call(to, alert["message"], "hi",
                                                  explicit=bool(test_to))
                    if test_to:
                        detail = "(redirected to %s) %s" % (test_to, detail)
                    voice.log_call(alert["farmer_id"], alert["message"], ok, detail,
                                   booking_id=alert["booking_id"])
                    flash("%s - %s" % (alert["name"], detail), "success" if ok else "error")
            elif action == "check_weather":
                district = request.form.get("district") or "Karnal"
                fc, source = weather.get_forecast(district, 5)
                result = {"district": district, "forecast": fc, "source": source}
            return render_template("admin/demo.html", forced=weather.DEMO_FORCE_RISK["on"],
                                   districts=_districts(), result=result,
                                   owm=bool(weather.OWM_API_KEY),
                                   queued_calls=_queued_calls(), voice=voice.status(),
                                   test_number=session.get("voice_test_number"))
        return render_template("admin/demo.html", forced=weather.DEMO_FORCE_RISK["on"],
                               districts=_districts(), result=None,
                               owm=bool(weather.OWM_API_KEY),
                               queued_calls=_queued_calls(), voice=voice.status(),
                               test_number=session.get("voice_test_number"))

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


def _queued_calls(limit=8):
    """Alerts that were queued for the phone channel but not dialled yet."""
    return query(
        "SELECT a.*, f.name, f.phone_number FROM alerts_log a"
        " JOIN farmers f ON f.id = a.farmer_id"
        " WHERE a.channel = 'ivr' AND a.alert_type != 'voice_call'"
        " ORDER BY a.id DESC LIMIT ?", (limit,))


def _districts():
    return [r["district"] for r in
            query("SELECT DISTINCT district FROM procurement_centres ORDER BY district")]


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

    # Novelty Feature A runs here, at registration - not weeks later at payout.
    problems = validate_and_flag(farmer_id)
    return {"error": None, "farmer_id": farmer_id, "problems": problems}


app = create_app()

if __name__ == "__main__":
    if not os.path.exists(db.DB_PATH):
        print("No database found. Run:  python seed.py")
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
