"""Writes alerts into alerts_log.

'app' ones actually show up for the farmer. 'sms' and 'ivr' are only saved
in the table for now - the IVR part will read them later.
TODO: hook up Fast2SMS
"""

from datetime import datetime

from db import execute, query
from i18n import HINDI

# ivr rows that aren't a call log are the words a phone call reads out. they
# belong to the helpline, and on the farmer's screen they just repeat the
# in-app alert next to them
FARMER_VISIBLE = "NOT (channel = 'ivr' AND alert_type != 'voice_call')"


def hi(text):
    """Hindi name of a centre, crop or place, for building hindi messages."""
    return HINDI.get(text, text)


def raise_alert(farmer_id, alert_type, channel, message, booking_id=None, message_hi=None):
    return execute(
        "INSERT INTO alerts_log (farmer_id, booking_id, alert_type, channel, message,"
        " message_hi, sent_at) VALUES (?,?,?,?,?,?,?)",
        (farmer_id, booking_id, alert_type, channel, message, message_hi,
         datetime.now().isoformat(timespec="seconds")),
    )


def farmer_alerts(farmer_id, limit=50):
    return query(
        "SELECT * FROM alerts_log WHERE farmer_id = ? AND " + FARMER_VISIBLE +
        " ORDER BY id DESC LIMIT ?",
        (farmer_id, limit),
    )


def unread_count(farmer_id):
    row = query("SELECT COUNT(*) AS c FROM alerts_log WHERE farmer_id = ? AND read_flag = 0"
                " AND " + FARMER_VISIBLE, (farmer_id,), one=True)
    return row["c"] if row else 0


def mark_all_read(farmer_id):
    execute("UPDATE alerts_log SET read_flag = 1 WHERE farmer_id = ?", (farmer_id,))
