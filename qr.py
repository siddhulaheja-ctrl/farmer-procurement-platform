"""QR codes for gate passes and receipts. They hold a signed url so a normal
camera app can open them too. SVG so we don't need pillow."""

import base64
import hashlib
import hmac
import io

import qrcode
import qrcode.image.svg
from flask import current_app, url_for


def sign(*parts):
    # truncated hmac, 12 chars is enough here
    mac = hmac.new(current_app.secret_key.encode(), "|".join(str(p) for p in parts).encode(),
                   hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac)[:12].decode()


def verify(sig, *parts):
    return bool(sig) and hmac.compare_digest(str(sig), sign(*parts))


# slot_id is in there so a rescheduled booking's old pass stops working
def _pass_parts(b):
    return ("pass", b["token_no"], b["id"], b["slot_id"])


def pass_sig(b):
    return sign(*_pass_parts(b))


def pass_signed(b, sig):
    return b is not None and verify(sig, *_pass_parts(b))


def pass_ok(b, sig):
    return pass_signed(b, sig) and b["status"] != "cancelled" and not b["gate_out_at"]


def pass_url(b):
    return url_for("token_lookup", token=b["token_no"], s=pass_sig(b), _external=True)


def _receipt_parts(txn):
    return ("receipt", txn["receipt_no"], txn["id"], "%.2f" % (txn["total_amount"] or 0))


def receipt_ok(txn, sig):
    return txn is not None and bool(txn["receipt_no"]) and verify(sig, *_receipt_parts(txn))


def receipt_url(txn):
    return url_for("receipt_lookup", number=txn["receipt_no"].replace("/", "-"),
                   s=sign(*_receipt_parts(txn)), _external=True)


def gatepass_svg(url, box_size=9):
    q = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=2,
    )
    q.add_data(url)
    q.make(fit=True)
    buf = io.BytesIO()
    q.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(buf)
    svg = buf.getvalue().decode("utf-8")

    if svg.startswith("<?xml"):
        svg = svg[svg.index("?>") + 2:].lstrip()
    return svg.replace('<svg width', '<svg class="qr" width', 1)
