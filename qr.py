"""QR codes for gate passes and purchase receipts.

Holds a URL, not just the token, so any camera app opens it - nothing to
install at every gate - and the portal's own gate scanner reads the same URL.

The URL carries a signature (an HMAC of the booking under the app's secret
key). A code someone typed up themselves, edited, or kept from before a
reschedule fails it, and the gate screen says so.

The token number is still what identifies the farmer, because that works on a
feature phone or a printout and a QR doesn't.

SVG, so no pillow and it prints at any size.
"""

import base64
import hashlib
import hmac
import io

import qrcode
import qrcode.image.svg
from flask import current_app, url_for


def sign(*parts):
    """12 url-safe characters - 72 bits, plenty for something checked by a person at a gate."""
    mac = hmac.new(current_app.secret_key.encode(), "|".join(str(p) for p in parts).encode(),
                   hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac)[:12].decode()


def verify(sig, *parts):
    return bool(sig) and hmac.compare_digest(str(sig), sign(*parts))


# the slot is part of what's signed, so moving a booking retires its old pass
def _pass_parts(b):
    return ("pass", b["token_no"], b["id"], b["slot_id"])


def pass_sig(b):
    return sign(*_pass_parts(b))


def pass_signed(b, sig):
    """The code really came from us for this booking in its current slot."""
    return b is not None and verify(sig, *_pass_parts(b))


def pass_ok(b, sig):
    """Signed and still usable - what a stranger scanning it is told."""
    return pass_signed(b, sig) and b["status"] != "cancelled" and not b["gate_out_at"]


def pass_url(b):
    # absolute - it gets scanned from a different phone
    return url_for("token_lookup", token=b["token_no"], s=pass_sig(b), _external=True)


# the amount is signed too, so a receipt with a changed figure fails
def _receipt_parts(txn):
    return ("receipt", txn["receipt_no"], txn["id"], "%.2f" % (txn["total_amount"] or 0))


def receipt_ok(txn, sig):
    return txn is not None and bool(txn["receipt_no"]) and verify(sig, *_receipt_parts(txn))


def receipt_url(txn):
    return url_for("receipt_lookup", number=txn["receipt_no"].replace("/", "-"),
                   s=sign(*_receipt_parts(txn)), _external=True)


def gatepass_svg(url, box_size=9):
    """QR for `url` as an <svg> string, ready to drop into a template.

    Error correction M survives about 15% damage - it gets folded into a
    pocket and carried to a mandi.
    """
    q = qrcode.QRCode(
        version=None,                                    # smallest that fits
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=2,
    )
    q.add_data(url)
    q.make(fit=True)
    buf = io.BytesIO()
    q.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(buf)
    svg = buf.getvalue().decode("utf-8")

    # the xml declaration is invalid halfway down an html page
    if svg.startswith("<?xml"):
        svg = svg[svg.index("?>") + 2:].lstrip()
    # size it from css, not the mm the library writes
    return svg.replace('<svg width', '<svg class="qr" width', 1)
