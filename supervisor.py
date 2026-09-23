"""Queries for the superadmin screens (read only)."""

from datetime import date, datetime, timedelta

import audit
from db import query
from i18n import t

# thresholds for the needs attention page
HELD_DAYS = 2              # a held payment older than this
LATE_MINUTES = 30          # a counter this far behind
FLAG_WINDOW_DAYS = 30
FLAG_MIN = 3
FLAG_RATIO = 2
OVERRIDE_WINDOW_DAYS = 7
REJECT_WINDOW_DAYS = 30


def _today():
    return date.today()


def centres_today():
    # subqueries so centres with no bookings still show up
    today = _today().isoformat()
    rows = query(
        "SELECT c.id, c.name, c.district, c.location, c.delay_minutes, c.delay_set_at,"
        " (SELECT COUNT(*) FROM bookings b JOIN slots s ON s.id = b.slot_id"
        "   WHERE s.centre_id = c.id AND s.date = ? AND b.status != 'cancelled') AS today_total,"
        " (SELECT COUNT(*) FROM bookings b JOIN slots s ON s.id = b.slot_id"
        "   WHERE s.centre_id = c.id AND s.date = ? AND b.status IN ('arrived','completed')) AS today_weighed,"
        " (SELECT COUNT(*) FROM bookings b JOIN slots s ON s.id = b.slot_id"
        "   WHERE s.centre_id = c.id AND s.date = ? AND b.status = 'completed') AS today_closed,"
        " (SELECT COALESCE(SUM(s.booked_count), 0) FROM slots s"
        "   WHERE s.centre_id = c.id AND s.date = ?) AS places_booked,"
        " (SELECT COALESCE(SUM(s.max_capacity), 0) FROM slots s"
        "   WHERE s.centre_id = c.id AND s.date = ?) AS places_total,"
        " (SELECT COUNT(*) FROM bookings b JOIN slots s ON s.id = b.slot_id"
        "   WHERE s.centre_id = c.id AND s.date >= ? AND b.status = 'booked'"
        "     AND b.storage_risk = 'high') AS high_risk,"
        " (SELECT COUNT(*) FROM transactions t JOIN bookings b ON b.id = t.booking_id"
        "   JOIN slots s ON s.id = b.slot_id WHERE s.centre_id = c.id"
        "     AND t.payment_status = 'failed' AND t.total_amount > 0) AS held,"
        " (SELECT COUNT(*) FROM staff st WHERE st.centre_id = c.id AND st.active = 1) AS staff_count"
        " FROM procurement_centres c ORDER BY c.name",
        (today,) * 6)
    out = []
    for r in rows:
        c = dict(r)
        c["usage"] = round(100 * c["places_booked"] / c["places_total"]) if c["places_total"] else 0
        out.append(c)
    return out


def _nice_ceiling(n):
    for step in (2, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100, 150, 200, 250, 500, 1000):
        if n <= step:
            return step
    return (n // 500 + 1) * 500


def _rect(x, y, w, h):
    return "M%.1f,%.1f h%.1f v%.1f h%.1f Z" % (x, y, w, h, -w)


def _rounded_top(x, y, w, h, r):
    r = min(r, h, w / 2)
    return ("M%.1f,%.1f V%.1f A%.1f,%.1f 0 0 1 %.1f,%.1f H%.1f A%.1f,%.1f 0 0 1 %.1f,%.1f V%.1f Z"
            % (x, y + h, y + r, r, r, x + r, y, x + w - r, r, r, x + w, y + r, y + h))


# bottom of the stack first
STACK = (("closed", "Closed"), ("weighed", "Weighed, not closed"), ("booked", "Booked"))


def bookings_chart(days_back=7, days_ahead=6):
    # stacked bar svg, geometry done here so the template just draws paths
    today = _today()
    start, end = today - timedelta(days=days_back), today + timedelta(days=days_ahead)
    rows = query(
        "SELECT s.date, b.status, COUNT(*) AS n FROM bookings b JOIN slots s ON s.id = b.slot_id"
        " WHERE s.date BETWEEN ? AND ? AND b.status != 'cancelled' GROUP BY s.date, b.status",
        (start.isoformat(), end.isoformat()))
    counts = {}
    for r in rows:
        key = {"completed": "closed", "arrived": "weighed", "booked": "booked"}.get(r["status"])
        if not key:
            continue
        counts.setdefault(r["date"], {})[key] = r["n"]

    W, H = 720, 232
    left, right, top, bottom = 30, 8, 22, 40
    base = H - bottom
    plot_h = base - top
    n_days = (end - start).days + 1
    slot = (W - left - right) / n_days
    bar_w = min(24.0, slot * 0.5)

    days = []
    d = start
    while d <= end:
        c = counts.get(d.isoformat(), {})
        days.append({"date": d, "iso": d.isoformat(), "is_today": d == today,
                     **{k: c.get(k, 0) for k, _ in STACK}})
        days[-1]["total"] = sum(days[-1][k] for k, _ in STACK)
        d += timedelta(days=1)

    ceiling = _nice_ceiling(max([x["total"] for x in days] + [1]))
    bars = []
    for i, day in enumerate(days):
        x = left + i * slot + (slot - bar_w) / 2
        y = base
        present = [(k, day[k]) for k, _ in STACK if day[k]]
        segments = []
        for j, (key, n) in enumerate(present):
            h = n / ceiling * plot_h
            seg_top = y - h
            last = j == len(present) - 1
            draw_top = seg_top if last else seg_top + 2
            draw_h = max(h if last else h - 2, 1)
            path = (_rounded_top(x, draw_top, bar_w, draw_h, 4) if last
                    else _rect(x, draw_top, bar_w, draw_h))
            segments.append({"key": key, "path": path})
            y = seg_top
        parts = ", ".join("%d %s" % (day[k], label.lower()) for k, label in reversed(STACK) if day[k])
        bars.append({"x": x, "cx": x + bar_w / 2, "w": bar_w, "top_y": y, "segments": segments,
                     "total": day["total"], "is_today": day["is_today"], "iso": day["iso"],
                     "day": day["date"].day, "dow": day["date"].strftime("%a"),
                     "hit_x": left + i * slot, "hit_w": slot,
                     "title": "%s: %s" % (day["date"].strftime("%a %d %b"), parts or "no bookings")})

    grid = [{"y": base - v / ceiling * plot_h, "v": v} for v in (0, ceiling // 2, ceiling)]
    return {"w": W, "h": H, "left": left, "right": W - right, "base": base, "bars": bars,
            "grid": grid, "days": days, "legend": list(reversed(STACK))}


def payment_split():
    rows = {r["payment_status"]: r for r in query(
        "SELECT payment_status, COUNT(*) AS n, COALESCE(SUM(total_amount), 0) AS amount"
        " FROM transactions GROUP BY payment_status")}
    order = (("completed", "Paid"), ("processing", "Processing"), ("pending", "Pending"),
             ("failed", "Held or failed"))
    total = sum(r["amount"] for r in rows.values()) or 0
    out = []
    for key, label in order:
        r = rows.get(key)
        amount = r["amount"] if r else 0
        out.append({"key": key, "label": label, "n": r["n"] if r else 0, "amount": amount,
                    "pct": round(100 * amount / total) if total else 0})
    return out


def overview():
    centres = centres_today()
    today = _today().isoformat()
    held = query("SELECT COUNT(*) AS n, COALESCE(SUM(total_amount), 0) AS amount FROM transactions"
                 " WHERE payment_status = 'failed' AND total_amount > 0", one=True)
    totals = {
        "today": sum(c["today_total"] for c in centres),
        "weighed": sum(c["today_weighed"] for c in centres),
        "held_n": held["n"], "held_amount": held["amount"],
        "high_risk": sum(c["high_risk"] for c in centres),
        "staff_active": query("SELECT COUNT(*) AS n FROM staff WHERE active = 1 AND role = 'staff'",
                              one=True)["n"],
        "signed_in": query("SELECT COUNT(DISTINCT staff_id) AS n FROM audit_log"
                           " WHERE action = 'sign_in' AND at >= ?", (today,), one=True)["n"],
    }
    return {"centres": centres, "totals": totals, "chart": bookings_chart(),
            "payments": payment_split()}


def needs_attention():
    today = _today()

    held = []
    for r in query(
            "SELECT t.id AS txn_id, t.total_amount, b.id AS booking_id, b.token_no,"
            " f.id AS farmer_id, f.name AS farmer_name, s.date, c.name AS centre_name"
            " FROM transactions t JOIN bookings b ON b.id = t.booking_id"
            " JOIN farmers f ON f.id = b.farmer_id JOIN slots s ON s.id = b.slot_id"
            " JOIN procurement_centres c ON c.id = s.centre_id"
            " WHERE t.payment_status = 'failed' AND t.total_amount > 0 AND s.date <= ?"
            " ORDER BY s.date", ((today - timedelta(days=HELD_DAYS)).isoformat(),)):
        item = dict(r)
        item["days"] = (today - datetime.strptime(r["date"], "%Y-%m-%d").date()).days
        held.append(item)

    late = [dict(r) for r in query(
        "SELECT id, name, delay_minutes, delay_set_at FROM procurement_centres"
        " WHERE delay_minutes >= ? ORDER BY delay_minutes DESC", (LATE_MINUTES,))]

    # staff clearing way more flags than the rest of the team
    since_flags = (today - timedelta(days=FLAG_WINDOW_DAYS)).isoformat()
    counts = [dict(r) for r in query(
        "SELECT st.id, st.name, st.staff_code, c.name AS centre_name, COUNT(a.id) AS n"
        " FROM staff st LEFT JOIN procurement_centres c ON c.id = st.centre_id"
        " LEFT JOIN audit_log a ON a.staff_id = st.id AND a.action = 'flag_verified' AND a.at >= ?"
        " WHERE st.role = 'staff' GROUP BY st.id", (since_flags,))]
    flag_outliers = []
    for person in counts:
        others = [p["n"] for p in counts if p["id"] != person["id"]]
        mean = sum(others) / len(others) if others else 0
        if person["n"] >= FLAG_MIN and person["n"] > FLAG_RATIO * mean:
            person["team_mean"] = mean
            flag_outliers.append(person)

    overrides = [dict(r) for r in query(
        "SELECT a.*, st.name AS staff_name, st.staff_code, f.name AS farmer_name, b.token_no"
        " FROM audit_log a JOIN staff st ON st.id = a.staff_id"
        " LEFT JOIN farmers f ON f.id = a.farmer_id LEFT JOIN bookings b ON b.id = a.booking_id"
        " WHERE a.action = 'payment_manual' AND a.at >= ? ORDER BY a.at DESC",
        ((today - timedelta(days=OVERRIDE_WINDOW_DAYS)).isoformat(),))]
    for o in overrides:
        o["changes"] = audit.changes(o["before_value"], o["after_value"])

    rejected = [dict(r) for r in query(
        "SELECT f.id AS farmer_id, f.name AS farmer_name, f.village, COUNT(*) AS n,"
        " MAX(s.date) AS last_date, GROUP_CONCAT(DISTINCT c.name) AS centres"
        " FROM transactions t JOIN bookings b ON b.id = t.booking_id"
        " JOIN farmers f ON f.id = b.farmer_id JOIN slots s ON s.id = b.slot_id"
        " JOIN procurement_centres c ON c.id = s.centre_id"
        " WHERE t.quality_grade = 'Rejected' AND s.date >= ?"
        " GROUP BY f.id ORDER BY n DESC, last_date DESC",
        ((today - timedelta(days=REJECT_WINDOW_DAYS)).isoformat(),))]

    return [
        {"key": "held", "title": t("Payments held"), "icon": "banknote", "tone": "bad",
         "rule": t("Held for %d days or more") % HELD_DAYS, "items": held},
        {"key": "flags", "title": t("Flags cleared without a fix"), "icon": "flag", "tone": "warn",
         "rule": t("%d or more in %d days, over %d times the team average")
                 % (FLAG_MIN, FLAG_WINDOW_DAYS, FLAG_RATIO),
         "items": flag_outliers},
        {"key": "overrides", "title": t("Payment status changed by hand"), "icon": "receipt",
         "tone": "warn", "rule": t("Last %d days") % OVERRIDE_WINDOW_DAYS, "items": overrides},
        {"key": "late", "title": t("Centres running late"), "icon": "hourglass", "tone": "warn",
         "rule": t("%d minutes or more behind") % LATE_MINUTES, "items": late},
        {"key": "rejected", "title": t("Loads rejected at the gate"), "icon": "x-circle",
         "tone": "neutral", "rule": t("Last %d days") % REJECT_WINDOW_DAYS, "items": rejected},
    ]


def attention_count():
    return sum(len(s["items"]) for s in needs_attention())


def staff_rows():
    today = _today().isoformat()
    return query(
        "SELECT st.id, st.name, st.staff_code, st.role, st.active, st.last_login, st.centre_id,"
        " c.name AS centre_name,"
        " SUM(CASE WHEN a.action = 'weigh' AND a.at >= ? THEN 1 ELSE 0 END) AS weighed,"
        " SUM(CASE WHEN a.action IN ('close', 'payment_held') AND a.at >= ? THEN 1 ELSE 0 END) AS closed,"
        " SUM(CASE WHEN a.action = 'flag_verified' AND a.at >= ? THEN 1 ELSE 0 END) AS flags,"
        " SUM(CASE WHEN a.action = 'call' AND a.at >= ? THEN 1 ELSE 0 END) AS calls"
        " FROM staff st LEFT JOIN procurement_centres c ON c.id = st.centre_id"
        " LEFT JOIN audit_log a ON a.staff_id = st.id"
        " GROUP BY st.id ORDER BY st.role DESC, st.active DESC, c.name, st.name",
        (today, today, today, today))


def staff_stats(staff_id, days=30):
    since = (_today() - timedelta(days=days)).isoformat()
    counts = {r["action"]: r["n"] for r in query(
        "SELECT action, COUNT(*) AS n FROM audit_log WHERE staff_id = ? AND at >= ?"
        " GROUP BY action", (staff_id, since))}
    return {
        "weighed": counts.get("weigh", 0),
        "closed": counts.get("close", 0) + counts.get("payment_held", 0),
        "flags": counts.get("flag_verified", 0),
        "calls": counts.get("call", 0),
        "sensitive": sum(counts.get(k, 0) for k in audit.SENSITIVE),
    }


def activity(centre_id=None, staff_id=None, action=None, days=None, sensitive_only=False,
             limit=300):
    sql = ("SELECT a.*, st.name AS staff_name, st.staff_code, st.role AS staff_role,"
           " c.name AS centre_name, f.name AS farmer_name, b.token_no"
           " FROM audit_log a JOIN staff st ON st.id = a.staff_id"
           " LEFT JOIN procurement_centres c ON c.id = a.centre_id"
           " LEFT JOIN farmers f ON f.id = a.farmer_id"
           " LEFT JOIN bookings b ON b.id = a.booking_id WHERE 1=1")
    args = []
    if centre_id:
        sql += " AND a.centre_id = ?"
        args.append(centre_id)
    if staff_id:
        sql += " AND a.staff_id = ?"
        args.append(staff_id)
    if action in audit.ACTIONS:
        sql += " AND a.action = ?"
        args.append(action)
    if days:
        sql += " AND a.at >= ?"
        args.append((_today() - timedelta(days=days - 1)).isoformat())
    if sensitive_only:
        sql += " AND a.action IN (%s)" % ",".join("?" * len(audit.SENSITIVE))
        args.extend(audit.SENSITIVE)
    sql += " ORDER BY a.at DESC, a.id DESC LIMIT ?"
    args.append(limit)
    out = []
    for r in query(sql, tuple(args)):
        e = dict(r)
        label, icon, sensitive = audit.ACTIONS.get(e["action"], (e["action"], "info", False))
        e.update(label=label, icon=icon, sensitive=sensitive,
                 changes=audit.changes(e["before_value"], e["after_value"]))
        out.append(e)
    return out
