"""Writes alerts into alerts_log.

'app' ones actually show up for the farmer. 'sms' and 'ivr' are only saved
in the table for now - the IVR part will read them later.
TODO: hook up Fast2SMS
"""

from datetime import datetime

from db import execute, query


def raise_alert(farmer_id, alert_type, channel, message, booking_id=None):
    return execute(
        "INSERT INTO alerts_log (farmer_id, booking_id, alert_type, channel, message, sent_at)"
        " VALUES (?,?,?,?,?,?)",
        (farmer_id, booking_id, alert_type, channel, message,
         datetime.now().isoformat(timespec="seconds")),
    )


def farmer_alerts(farmer_id, limit=50):
    return query(
        "SELECT * FROM alerts_log WHERE farmer_id = ? ORDER BY id DESC LIMIT ?",
        (farmer_id, limit),
    )


def unread_count(farmer_id):
    row = query("SELECT COUNT(*) AS c FROM alerts_log WHERE farmer_id = ? AND read_flag = 0",
                (farmer_id,), one=True)
    return row["c"] if row else 0


def mark_all_read(farmer_id):
    execute("UPDATE alerts_log SET read_flag = 1 WHERE farmer_id = ?", (farmer_id,))
