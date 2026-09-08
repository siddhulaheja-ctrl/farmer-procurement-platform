"""Gate pass QR codes.

The QR holds a URL rather than the bare token, so it opens in whatever camera
app the clerk already has on their phone. That matters more than it sounds -
it means no scanner app to install on every gate, nothing to keep updated, and
nothing to go wrong at six in the morning. The phone's own camera reads it and
offers the link.

It is a lookup shortcut for the clerk, not the thing that identifies the
farmer. The token number stays the primary identifier because it works when
the farmer has a feature phone, a printout, or a number written on a scrap of
paper, and QR does not.

SVG rather than PNG: no pillow to install, it goes straight into the page as
markup, and it prints at whatever size the paper is.
"""

import io

import qrcode
import qrcode.image.svg


def gatepass_svg(url, box_size=9):
    """QR for `url`, as an <svg> string ready to drop into a template.

    Error correction M tolerates about 15% damage, which is the right level for
    something that gets folded into a pocket and carried to a mandi.
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

    # drop the xml declaration, it is invalid halfway down an html page
    if svg.startswith("<?xml"):
        svg = svg[svg.index("?>") + 2:].lstrip()
    # let css size it instead of the hardcoded mm the library writes
    return svg.replace('<svg width', '<svg class="qr" width', 1)
