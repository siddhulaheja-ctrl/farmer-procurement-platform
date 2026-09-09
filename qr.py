"""Gate pass QR codes.

Holds a URL, not just the token, so the clerk's normal camera app opens it -
nothing to install at every gate.

It's a shortcut for staff, not ID. The token number is still the thing that
identifies the farmer, because that works on a feature phone or a printout
and a QR doesn't.

SVG, so no pillow and it prints at any size.
"""

import io

import qrcode
import qrcode.image.svg


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
