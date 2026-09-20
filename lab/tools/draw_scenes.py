"""Ink-and-wash drawings for the portal's pages, in the field-notebook style.

    python lab/tools/draw_scenes.py            # every drawing
    python lab/tools/draw_scenes.py gate bank  # just these

Writes static/img/art/<name>.svg. Each is a small scene for one part of the
portal: a phone with a code for signing in, a procurement shed for centres, a
bank for payments, a scarecrow for a missing page. Lines are wobbled a little
and every shape gets a second, fainter pass, so they read as drawn by hand; the
colour is a flat wash set slightly off the outline, the way watercolour misses
the pencil. Fixed seeds, so re-running gives the same pictures.
"""
import math
import os
import random
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "static", "img", "art")

INK = "#1f3b2d"
TERRA = "#c0582f"
WASH = {
    "leaf": "#b7d38c", "leaf2": "#8fbf5c", "wheat": "#efd28c", "straw": "#e6c36a", "terra": "#eaa07d",
    "sky": "#c3dcec", "soil": "#dcc398", "paper": "#fbfbf2", "stone": "#d9dfd0", "red": "#ea907a",
    "blue": "#a6c9e4", "gold": "#f4d06f", "brown": "#c49a6c", "grey": "#cbd3c5", "pink": "#f1b8c2",
    "white": "#ffffff", "cream": "#f6efd9", "shade": "#aebaa5", "dark": "#6f7f6a",
}


def f(v):
    return ("%.1f" % v).rstrip("0").rstrip(".")


class Scene:
    def __init__(self, name, w=320, h=240, seed=None):
        self.name, self.w, self.h = name, w, h
        self.rng = random.Random(seed if seed is not None else name)
        self.layers = {"back": [], "wash": [], "fine": [], "ink": [], "top": []}
        self.tf = []

    # ------------------------------------------------------------ geometry
    def _apply(self, pts):
        for fn in reversed(self.tf):
            pts = [fn(x, y) for x, y in pts]
        return pts

    def push(self, rotate=0, about=(0, 0), translate=(0, 0), scale=1):
        a = math.radians(rotate)
        cx, cy = about
        tx, ty = translate

        def fn(x, y):
            x, y = (x - cx) * scale, (y - cy) * scale
            x, y = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
            return x + cx + tx, y + cy + ty
        self.tf.append(fn)
        return self

    def pop(self):
        self.tf.pop()

    def _subdivide(self, pts, closed, step=12):
        out = []
        n = len(pts)
        segs = n if closed else n - 1
        for i in range(segs):
            (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
            k = max(1, int(math.hypot(x2 - x1, y2 - y1) / step))
            for j in range(k):
                out.append((x1 + (x2 - x1) * j / k, y1 + (y2 - y1) * j / k))
        if not closed:
            out.append(pts[-1])
        return out

    def _wobble(self, pts, amt):
        return [(x + self.rng.uniform(-amt, amt), y + self.rng.uniform(-amt, amt)) for x, y in pts]

    @staticmethod
    def _d(pts, closed):
        d = "M" + " L".join("%s %s" % (f(x), f(y)) for x, y in pts)
        return d + (" Z" if closed else "")

    # ------------------------------------------------------------ marks
    def shape(self, pts, closed=True, fill=None, stroke=INK, w=2.2, wobble=0.7, alpha=0.85,
              offset=(3, 2.5), fine=True, layer="ink", smooth=False):
        pts = self._apply(pts)
        if smooth:
            pts = catmull(pts, closed)
        if fill:
            wp = [(x + offset[0], y + offset[1]) for x, y in self._wobble(self._subdivide(pts, closed, 14), 1.2)]
            self.layers["wash"].append('<path d="%s" fill="%s" fill-opacity="%s"/>'
                                       % (self._d(wp, True), WASH.get(fill, fill), alpha))
        if stroke:
            line = self._wobble(self._subdivide(pts, closed), wobble)
            self.layers[layer].append('<path d="%s" stroke="%s" stroke-width="%s"/>' % (self._d(line, closed), stroke, f(w)))
            if fine and w >= 1.6:
                again = self._wobble(self._subdivide(pts, closed, 18), wobble * 1.6)
                self.layers["fine"].append('<path d="%s" stroke="%s" stroke-width="%s" stroke-opacity=".35"/>'
                                           % (self._d(again, closed), stroke, f(max(0.8, w * .45))))

    def blob(self, pts, fill, alpha=0.6, layer="back"):
        """a wash with no line: the pale ground a scene stands on"""
        pts = catmull(self._apply(pts), True)
        self.layers[layer].append('<path d="%s" fill="%s" fill-opacity="%s"/>' % (self._d(pts, True), WASH.get(fill, fill), alpha))

    def line(self, x1, y1, x2, y2, **kw):
        kw.setdefault("fine", False)
        self.shape([(x1, y1), (x2, y2)], closed=False, **kw)

    def lines(self, pts, **kw):
        self.shape(pts, closed=False, **kw)

    def rect(self, x, y, rw, rh, r=0, **kw):
        self.shape(rounded(x, y, rw, rh, r), **kw)

    def ellipse(self, cx, cy, rx, ry=None, **kw):
        ry = rx if ry is None else ry
        n = max(14, int((rx + ry) * .45))
        self.shape([(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)], **kw)

    def arc(self, cx, cy, r, a0, a1, **kw):
        n = max(6, int(abs(a1 - a0) * r / 12))
        pts = [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
               for i in range(n + 1)]
        kw.setdefault("closed", False)
        self.shape(pts, **kw)

    def dot(self, x, y, r=2.2, color=INK):
        (x, y), = self._apply([(x, y)])
        self.layers["top"].append('<circle cx="%s" cy="%s" r="%s" fill="%s"/>' % (f(x), f(y), f(r), color))

    def ground(self, x1=24, x2=296, y=214, tufts=5):
        """the pencilled patch of soil with a few blades of grass that every scene stands on"""
        pts = [(x1 + (x2 - x1) * i / 8, y + math.sin(i * 1.3) * 2) for i in range(9)]
        self.shape(pts, closed=False, w=1.8, smooth=True, fine=False)
        for i in range(tufts):
            gx = x1 + 10 + (x2 - x1 - 20) * (i + .5) / tufts + self.rng.uniform(-10, 10)
            for dx, lean in ((-2, -3), (0, 1), (2, 4)):
                self.line(gx + dx, y + 1, gx + dx + lean, y - 7 - self.rng.uniform(0, 4), stroke="#5f8a3e", w=1.3)

    def sparkle(self, x, y, s=6, color=TERRA):
        self.line(x - s, y, x + s, y, stroke=color, w=1.6)
        self.line(x, y - s, x, y + s, stroke=color, w=1.6)

    def svg(self):
        body = "".join(self.layers["back"] + self.layers["wash"] + self.layers["fine"] + self.layers["ink"] + self.layers["top"])
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" fill="none" '
                'stroke-linecap="round" stroke-linejoin="round">%s</svg>\n') % (self.w, self.h, self.w, self.h, body)


def rounded(x, y, w, h, r):
    if r <= 0:
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    pts = []
    for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
        for i in range(4):
            a = math.radians(a0 + 90 * i / 3)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def catmull(pts, closed, n=6):
    if len(pts) < 3:
        return pts
    out = []
    P = pts + pts[:3] if closed else [pts[0]] + pts + [pts[-1]]
    count = len(pts) if closed else len(pts) - 1
    for i in range(count):
        p0, p1, p2, p3 = P[i], P[i + 1], P[i + 2], P[i + 3]
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    if not closed:
        out.append(pts[-1])
    return out


# ------------------------------------------------------------ small pieces used by several scenes

def sack(d, x, y, s=1.0, fill="cream", tie=True):
    """a jute sack, standing, bottom centre at (x, y)"""
    w, h = 34 * s, 42 * s
    d.shape([(x - w * .42, y - h * .78), (x - w * .5, y - h * .3), (x - w * .46, y), (x + w * .46, y), (x + w * .5, y - h * .3),
             (x + w * .42, y - h * .78), (x + w * .2, y - h * .92), (x - w * .2, y - h * .92)], fill=fill, smooth=True, w=2)
    if tie:
        d.lines([(x - w * .22, y - h * .82), (x, y - h * .74), (x + w * .22, y - h * .82)], w=1.6)
        d.lines([(x - w * .1, y - h * .92), (x - w * .16, y - h * 1.08)], w=1.6)
        d.lines([(x + w * .1, y - h * .92), (x + w * .16, y - h * 1.08)], w=1.6)
    for k in range(3):
        yy = y - h * (.25 + k * .17)
        d.line(x - w * .28, yy, x + w * .28, yy + 1, w=1, stroke="#8a7a58")


def wheat_ear(d, x, y, h=60, lean=0, fill="straw"):
    top = (x + lean, y - h)
    d.lines([(x, y), (x + lean * .5, y - h * .5), top], w=1.8, smooth=True, stroke="#8f7a3a")
    for k in range(5):
        t = .55 + k * .09
        cx, cy = x + lean * t, y - h * t
        for side in (-1, 1):
            d.ellipse(cx + side * 4, cy, 3.4, 6, fill=fill, w=1.3, stroke="#8f6418", fine=False)
    d.line(top[0], top[1] - 6, top[0] + lean * .1, top[1] - 16, stroke="#b58f45", w=1)


def sprout(d, x, y, s=1.0):
    d.lines([(x, y), (x, y - 22 * s)], w=2, stroke="#4f7a3a")
    d.shape([(x, y - 16 * s), (x - 14 * s, y - 26 * s), (x - 20 * s, y - 20 * s), (x - 8 * s, y - 13 * s)], fill="leaf2", smooth=True, stroke="#4f7a3a", w=1.8)
    d.shape([(x, y - 22 * s), (x + 12 * s, y - 36 * s), (x + 19 * s, y - 30 * s), (x + 8 * s, y - 20 * s)], fill="leaf", smooth=True, stroke="#4f7a3a", w=1.8)


def cloud(d, cx, cy, s=1.0, fill="white"):
    pts = []
    for ang, r in ((180, 16), (220, 18), (260, 24), (300, 20), (340, 16), (20, 14), (90, 12), (150, 14)):
        a = math.radians(ang)
        pts.append((cx + math.cos(a) * r * 1.6 * s, cy + math.sin(a) * r * .9 * s))
    d.shape(pts, fill=fill, smooth=True, w=2, stroke="#5d7384")


def sun(d, cx, cy, r=16):
    d.ellipse(cx, cy, r, fill="gold", stroke="#c9901a", w=2)
    for k in range(10):
        a = math.radians(k * 36)
        d.line(cx + math.cos(a) * (r + 5), cy + math.sin(a) * (r + 5), cx + math.cos(a) * (r + 11), cy + math.sin(a) * (r + 11),
               stroke="#d99a06", w=2)


def rupee(d, x, y, s=1.0, stroke=INK, w=2.2):
    """the ₹ sign drawn as strokes, (x, y) its top left"""
    d.line(x, y, x + 14 * s, y, stroke=stroke, w=w)
    d.line(x, y + 5 * s, x + 14 * s, y + 5 * s, stroke=stroke, w=w)
    d.lines([(x, y), (x + 6 * s, y), (x + 10 * s, y + 2.5 * s), (x + 10 * s, y + 5 * s), (x + 7 * s, y + 9 * s), (x + 1 * s, y + 9 * s)],
            stroke=stroke, w=w, smooth=True)
    d.line(x + 1 * s, y + 9 * s, x + 12 * s, y + 20 * s, stroke=stroke, w=w)


def qr(d, x, y, s=40, seed=3):
    rng = random.Random(seed)
    d.rect(x, y, s, s, 2, fill="white", w=2)
    cell = s / 9
    for fx, fy in ((0, 0), (6, 0), (0, 6)):
        d.rect(x + (fx + .5) * cell, y + (fy + .5) * cell, cell * 2.2, cell * 2.2, 0, w=1.6, fine=False)
        d.dot(x + (fx + 1.6) * cell, y + (fy + 1.6) * cell, cell * .45)
    for i in range(9):
        for j in range(9):
            if (i < 3 and j < 3) or (i > 5 and j < 3) or (i < 3 and j > 5):
                continue
            if rng.random() < .45:
                d.dot(x + (i + .5) * cell, y + (j + .5) * cell, cell * .32)


def person(d, x, y, s=1.0, turban="terra", shirt="white", scarf=None):
    """a farmer from the chest up, (x, y) the bottom centre"""
    d.shape([(x - 28 * s, y), (x - 26 * s, y - 22 * s), (x - 12 * s, y - 32 * s), (x + 12 * s, y - 32 * s), (x + 26 * s, y - 22 * s), (x + 28 * s, y)],
            fill=shirt, smooth=True, w=2)
    d.lines([(x - 6 * s, y - 32 * s), (x, y - 24 * s), (x + 6 * s, y - 32 * s)], w=1.6)
    d.ellipse(x, y - 46 * s, 12 * s, 14 * s, fill="#e7b98f", stroke="#6b4a2f", w=2)
    if turban == "scarf":
        d.shape([(x - 15 * s, y - 44 * s), (x - 14 * s, y - 60 * s), (x, y - 66 * s), (x + 14 * s, y - 60 * s), (x + 15 * s, y - 44 * s),
                 (x + 18 * s, y - 28 * s), (x + 10 * s, y - 36 * s), (x - 10 * s, y - 36 * s), (x - 18 * s, y - 28 * s)],
                fill=scarf or "pink", smooth=True, w=2)
    elif turban:
        d.shape([(x - 14 * s, y - 50 * s), (x - 15 * s, y - 60 * s), (x - 6 * s, y - 68 * s), (x + 8 * s, y - 68 * s), (x + 15 * s, y - 60 * s),
                 (x + 14 * s, y - 50 * s)], fill=turban, smooth=True, w=2)
        d.arc(x, y - 52 * s, 13 * s, 200, 340, w=1.4)
    d.dot(x - 4 * s, y - 47 * s, 1.3 * s)
    d.dot(x + 4 * s, y - 47 * s, 1.3 * s)
    d.lines([(x - 3 * s, y - 40 * s), (x, y - 38.5 * s), (x + 3 * s, y - 40 * s)], w=1.3, stroke="#6b4a2f", fine=False)


# ------------------------------------------------------------ scenes

def phone_otp():
    d = Scene("phone-otp")
    d.blob([(40, 190), (70, 70), (170, 40), (280, 80), (290, 190), (170, 222)], "stone", .45)
    d.ground(40, 290)
    d.push(rotate=-8, about=(150, 120))
    d.rect(108, 36, 92, 170, 14, fill="paper", w=2.6)
    d.rect(116, 54, 76, 128, 4, fill="sky", alpha=.45, w=1.6)
    d.line(142, 45, 166, 45, w=2)
    d.ellipse(154, 194, 5, w=1.6, fine=False)
    d.rect(124, 70, 60, 34, 8, fill="leaf", w=1.8)
    d.lines([(134, 104), (130, 114), (144, 104)], w=1.8)
    for k in range(6):
        d.ellipse(128 + k * 10.5, 87, 3.2, fill=INK, alpha=1, w=1.2, fine=False)
    d.rect(124, 124, 60, 12, 6, fill="terra", w=1.6)
    d.line(124, 150, 176, 150, w=1.2, fine=False)
    d.line(124, 162, 160, 162, w=1.2, fine=False)
    d.pop()
    sprout(d, 238, 212, 1.5)
    d.sparkle(222, 70)
    d.sparkle(82, 96, 5, INK)
    d.arc(208, 90, 18, -60, 20, w=2, stroke=TERRA)
    d.arc(208, 90, 30, -55, 15, w=2, stroke=TERRA)
    return d


def otp_lock():
    d = Scene("otp-lock")
    d.blob([(40, 190), (80, 60), (180, 36), (286, 90), (280, 196), (150, 222)], "stone", .45)
    d.ground(44, 286)
    d.rect(92, 104, 96, 90, 12, fill="gold", w=2.6)
    d.arc(140, 104, 30, 180, 360, w=4, stroke=INK)
    d.line(110, 104, 110, 86, w=4)
    d.ellipse(140, 140, 9, fill=INK, alpha=1, w=1.6)
    d.line(140, 146, 140, 166, w=5)
    d.rect(186, 46, 104, 40, 10, fill="white", w=2)
    d.lines([(206, 86), (200, 100), (218, 86)], w=2)
    for k in range(6):
        d.dot(202 + k * 14, 66, 4)
    d.push(rotate=-28, about=(236, 168))
    d.ellipse(212, 168, 14, fill="terra", w=2.2)
    d.ellipse(212, 168, 5, w=1.6, fine=False)
    d.lines([(226, 168), (272, 168), (272, 178), (262, 178), (262, 172), (252, 172), (252, 178)], w=2.2)
    d.pop()
    d.sparkle(70, 80)
    return d


def register_card():
    d = Scene("register-card")
    d.blob([(30, 196), (60, 70), (160, 34), (284, 70), (296, 196), (160, 226)], "stone", .45)
    d.ground(36, 292)
    d.push(rotate=-6, about=(140, 120))
    d.rect(56, 62, 164, 108, 10, fill="paper", w=2.6)
    d.rect(56, 62, 164, 22, 0, fill="leaf", alpha=.7, w=1.6)
    d.rect(70, 96, 46, 56, 4, fill="sky", alpha=.5, w=1.8)
    d.ellipse(93, 116, 10, fill="#e7b98f", w=1.6, fine=False)
    d.shape([(79, 152), (82, 134), (104, 134), (107, 152)], fill="terra", w=1.6, fine=False)
    for k, ln in enumerate((78, 62, 70, 44)):
        d.line(130, 104 + k * 13, 130 + ln, 104 + k * 13, w=1.6, fine=False)
    d.pop()
    d.push(rotate=38, about=(230, 150))
    d.rect(200, 144, 76, 12, 3, fill="terra", w=2)
    d.shape([(200, 144), (186, 150), (200, 156)], fill="cream", w=2)
    d.pop()
    d.shape([(250, 212), (244, 186), (292, 186), (286, 212)], fill="terra", w=2.2)
    sprout(d, 268, 186, 1.2)
    d.sparkle(262, 60)
    return d


def voice():
    d = Scene("voice")
    d.blob([(34, 196), (54, 64), (160, 30), (290, 64), (292, 198), (160, 226)], "stone", .45)
    d.ground(40, 290)
    d.rect(118, 52, 56, 92, 28, fill="terra", w=2.8)
    for k in range(4):
        d.line(130, 74 + k * 14, 162, 74 + k * 14, w=1.4, stroke="#7a3a1e", fine=False)
    d.arc(146, 112, 44, 20, 160, w=3)
    d.line(146, 156, 146, 194, w=3)
    d.lines([(118, 212), (126, 196), (166, 196), (174, 212)], w=2.6)
    for k, r in enumerate((58, 74)):
        d.arc(146, 98, r, -40, 30, w=2.4, stroke="#2f6b3a")
        d.arc(146, 98, r, 150, 220, w=2.4, stroke="#2f6b3a")
    d.rect(212, 34, 82, 48, 12, fill="leaf", w=2)
    d.lines([(230, 82), (222, 96), (246, 82)], w=2)
    heights = (10, 22, 14, 26, 12, 18)
    for k, hh in enumerate(heights):
        d.line(226 + k * 10, 58 - hh / 2, 226 + k * 10, 58 + hh / 2, w=2.4, fine=False)
    d.rect(22, 44, 70, 40, 12, fill="white", w=2)
    d.lines([(76, 84), (84, 96), (64, 84)], w=2)
    d.dot(42, 64, 3.5)
    d.dot(57, 64, 3.5)
    d.dot(72, 64, 3.5)
    return d


def _oval(cx, cy, rx, ry, n=16):
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def pin():
    """a small thumbtack, for the corner of a card pinned to the page"""
    d = Scene("pin", 44, 54)
    d.blob(_oval(23, 49, 8, 3), "stone", .35)
    d.line(22, 28, 19, 46, w=2, stroke="#6b4a2f")
    d.push(rotate=-10, about=(21, 18))
    d.ellipse(21, 18, 12, 11, fill="red", w=2.2)
    d.arc(17, 13, 5, 200, 300, w=1.3, stroke="#f4c9b0")
    d.pop()
    return d


def mandi():
    d = Scene("mandi")
    d.blob([(20, 204), (36, 84), (150, 44), (300, 80), (306, 204), (160, 230)], "stone", .45)
    d.ground(16, 306)
    d.rect(50, 110, 190, 98, 0, fill="cream", w=2.6)
    d.shape([(38, 114), (60, 74), (230, 74), (252, 114)], fill="terra", w=2.8)
    for k in range(9):
        d.line(66 + k * 20, 78, 50 + k * 24, 112, w=1.1, stroke="#9a4a2a", fine=False)
    d.rect(118, 140, 58, 68, 0, fill="brown", alpha=.5, w=2.2)
    d.line(147, 140, 147, 208, w=1.4)
    sack(d, 24, 208, .8, "wheat")
    sack(d, 84, 208, .9)
    sack(d, 102, 176, .8, "wheat")
    d.line(206, 208, 206, 150, w=2.4)
    d.line(190, 150, 222, 150, w=2.4)
    d.lines([(190, 150), (184, 170), (196, 170), (190, 150)], w=1.8)
    d.lines([(222, 150), (216, 170), (228, 170), (222, 150)], w=1.8)
    d.line(196, 208, 216, 208, w=2.4)
    d.push(translate=(0, -6))
    d.shape([(262, 72), (250, 50), (254, 34), (270, 30), (282, 38), (282, 52)], fill="red", smooth=True, w=2.4)
    d.ellipse(267, 45, 6, fill="white", w=1.6, fine=False)
    d.pop()
    d.lines([(264, 66), (262, 112)], w=1.4, stroke=TERRA)
    return d


def calendar():
    d = Scene("calendar")
    d.blob([(30, 200), (46, 70), (160, 34), (290, 70), (296, 204), (160, 228)], "stone", .45)
    d.ground(34, 294)
    d.rect(60, 50, 146, 150, 8, fill="paper", w=2.6)
    d.rect(60, 50, 146, 34, 8, fill="terra", w=2.2)
    for x in (86, 180):
        d.line(x, 40, x, 60, w=4)
    for r in range(3):
        for c in range(4):
            x, y = 80 + c * 32, 104 + r * 30
            d.rect(x - 8, y - 8, 18, 16, 3, w=1.4, fine=False, fill="cream" if (r, c) != (1, 2) else None)
    d.ellipse(145, 135, 16, 14, stroke=TERRA, w=2.6)
    d.lines([(136, 136), (143, 144), (156, 126)], w=2.6, stroke="#2f6b3a")
    d.ellipse(234, 150, 36, fill="white", w=2.6)
    for k in range(12):
        a = math.radians(k * 30)
        d.line(234 + math.cos(a) * 29, 150 + math.sin(a) * 29, 234 + math.cos(a) * 33, 150 + math.sin(a) * 33, w=1.6, fine=False)
    d.line(234, 150, 234, 128, w=2.8)
    d.line(234, 150, 250, 158, w=2.8)
    d.dot(234, 150, 3)
    wheat_ear(d, 280, 212, 70, -8)
    return d


def ticket():
    d = Scene("ticket")
    d.blob([(20, 204), (40, 78), (150, 40), (296, 70), (306, 204), (160, 230)], "stone", .45)
    d.ground(16, 306)
    d.rect(126, 120, 150, 60, 4, fill="leaf", alpha=.7, w=2.6)
    d.line(110, 164, 126, 164, w=3)
    for k in range(4):
        sack(d, 146 + k * 30, 122, .72, fill="cream" if k % 2 else "wheat")
    for cx in (160, 244):
        d.ellipse(cx, 194, 16, fill="dark", alpha=.6, w=2.6)
        d.ellipse(cx, 194, 5, w=1.6, fine=False)
    d.push(rotate=-10, about=(70, 96))
    d.rect(20, 60, 104, 70, 6, fill="gold", w=2.4)
    d.line(46, 60, 46, 130, w=1.6, stroke="#8a6a1a")
    for k in range(4):
        d.dot(46, 70 + k * 16, 2.4, "#eef1e6")
    d.line(58, 82, 110, 82, w=2, fine=False)
    d.line(58, 96, 100, 96, w=2, fine=False)
    d.line(58, 110, 92, 110, w=2, fine=False)
    d.pop()
    return d


def gate():
    d = Scene("gate")
    d.blob([(20, 204), (30, 80), (150, 40), (296, 70), (306, 206), (160, 230)], "stone", .45)
    d.ground(16, 306)
    d.rect(34, 96, 52, 112, 2, fill="cream", w=2.6)
    d.shape([(28, 100), (60, 76), (92, 100)], fill="terra", w=2.4)
    d.rect(46, 118, 28, 22, 2, fill="sky", w=1.8)
    d.rect(94, 150, 14, 58, 2, fill="dark", alpha=.5, w=2.4)
    d.push(rotate=-18, about=(101, 156))
    d.rect(101, 150, 150, 12, 3, fill="white", w=2.4)
    for k in range(5):
        d.rect(114 + k * 28, 150, 12, 12, 0, fill="red", w=0, stroke=None)
    d.pop()
    d.push(rotate=10, about=(232, 150))
    d.rect(200, 92, 66, 116, 12, fill="paper", w=2.6)
    qr(d, 212, 112, 42)
    d.line(222, 176, 256, 176, w=1.8, fine=False)
    d.line(226, 188, 250, 188, w=1.8, fine=False)
    d.pop()
    for k in range(3):
        d.arc(233, 150, 64 + k * 12, -70, -40, w=2, stroke=TERRA)
    return d


def bank():
    d = Scene("bank")
    d.blob([(20, 204), (36, 80), (150, 36), (296, 70), (306, 206), (160, 230)], "stone", .45)
    d.ground(16, 306)
    d.shape([(34, 92), (122, 44), (210, 92)], fill="terra", w=2.8)
    d.rect(40, 92, 164, 14, 0, fill="cream", w=2.4)
    for k in range(5):
        d.rect(52 + k * 32, 112, 14, 78, 0, fill="white", w=2.2)
    d.rect(34, 190, 176, 18, 0, fill="stone", w=2.6)
    d.ellipse(122, 72, 8, fill="gold", w=1.8, fine=False)
    for k in range(5):
        d.ellipse(262, 204 - k * 11, 26, 8, fill="gold", w=2.2)
    d.push(rotate=-12, about=(250, 110))
    d.rect(218, 84, 72, 44, 4, fill="leaf", w=2.4)
    d.ellipse(254, 106, 12, w=1.8, fine=False)
    rupee(d, 248, 97, .55, w=1.8)
    d.pop()
    d.sparkle(288, 150)
    return d


def bell():
    d = Scene("bell")
    d.blob([(30, 200), (46, 70), (160, 34), (290, 70), (296, 204), (160, 228)], "stone", .45)
    d.ground(34, 294)
    d.shape([(102, 180), (110, 158), (112, 110), (126, 86), (150, 78), (174, 86), (188, 110), (190, 158), (198, 180)], fill="gold", smooth=True, w=2.8)
    d.line(98, 180, 202, 180, w=3)
    d.ellipse(150, 192, 11, fill="terra", w=2.4)
    d.ellipse(150, 72, 7, w=2.2)
    for side in (-1, 1):
        d.arc(150, 132, 72, 200 if side < 0 else -20, 240 if side < 0 else 20, w=2.6, stroke=TERRA)
        d.arc(150, 132, 88, 205 if side < 0 else -25, 235 if side < 0 else 15, w=2.2, stroke=TERRA)
    cloud(d, 250, 58, .8, "sky")
    for k in range(3):
        d.line(236 + k * 14, 82, 232 + k * 14, 94, stroke="#3b78b8", w=2.4)
    d.rect(28, 50, 58, 38, 3, fill="white", w=2.2)
    d.lines([(28, 50), (57, 72), (86, 50)], w=2)
    return d


def profile():
    d = Scene("profile")
    d.blob([(24, 200), (40, 70), (150, 36), (296, 70), (300, 204), (160, 228)], "stone", .45)
    d.ground(24, 300)
    for k, (x, y, fill) in enumerate(((176, 150, "leaf"), (226, 150, "wheat"), (176, 182, "wheat"), (226, 182, "leaf2"))):
        d.shape([(x, y), (x + 46, y - 4), (x + 50, y + 26), (x + 2, y + 30)], fill=fill, alpha=.75, w=2)
        for r in range(3):
            d.line(x + 6, y + 8 + r * 8, x + 42, y + 5 + r * 8, w=1, stroke="#6f8f4a", fine=False)
    d.push(rotate=-8, about=(100, 110))
    d.rect(30, 64, 130, 88, 10, fill="paper", w=2.6)
    d.ellipse(66, 102, 18, 20, fill="sky", w=2)
    d.arc(66, 132, 18, 200, 340, w=2)
    for k, ln in enumerate((52, 40, 46)):
        d.line(96, 92 + k * 14, 96 + ln, 92 + k * 14, w=1.8, fine=False)
    d.pop()
    d.ellipse(252, 76, 22, fill="leaf2", w=2.6)
    d.lines([(240, 77), (249, 86), (265, 66)], w=3.4)
    return d


def seal():
    d = Scene("seal")
    d.blob([(30, 200), (46, 70), (160, 34), (290, 70), (296, 204), (160, 228)], "stone", .45)
    d.ground(34, 294)
    d.push(rotate=-5, about=(130, 120))
    d.rect(60, 40, 120, 160, 4, fill="paper", w=2.6)
    for k in range(6):
        d.line(76, 64 + k * 14, 164 - (k % 3) * 14, 64 + k * 14, w=1.6, fine=False)
    pts = []
    for k in range(24):
        a = math.radians(k * 15)
        r = 26 if k % 2 else 22
        pts.append((140 + math.cos(a) * r, 166 + math.sin(a) * r))
    d.shape(pts, fill="terra", w=2.2)
    d.lines([(130, 166), (137, 174), (152, 156)], w=3, stroke="#ffffff", fine=False)
    d.pop()
    d.ellipse(226, 110, 40, fill="sky", alpha=.35, w=3.4)
    d.line(254, 140, 290, 184, w=8, stroke=INK)
    d.line(254, 140, 290, 184, w=4, stroke="#c49a6c", fine=False)
    return d


def scarecrow():
    d = Scene("scarecrow")
    d.blob([(20, 204), (40, 70), (150, 30), (296, 64), (306, 204), (160, 230)], "sky", .35)
    d.shape([(10, 214), (80, 196), (160, 204), (240, 192), (310, 202), (310, 228), (10, 228)], fill="leaf", alpha=.55, stroke=None)
    d.line(160, 214, 160, 62, w=4, stroke="#6b4a2f")
    d.line(96, 104, 224, 98, w=4, stroke="#6b4a2f")
    d.shape([(126, 100), (194, 98), (198, 168), (122, 170)], fill="terra", w=2.6)
    d.lines([(160, 104), (160, 168)], w=1.4, fine=False)
    d.shape([(98, 100), (126, 96), (124, 118), (104, 114)], fill="terra", w=2.2)
    d.shape([(222, 96), (194, 96), (196, 118), (216, 112)], fill="terra", w=2.2)
    for x in (100, 214):
        for k in range(3):
            d.line(x + (4 if x < 160 else -4), 110, x - 8 + k * 6 + (0 if x < 160 else 6), 126, stroke="#b8902a", w=1.6)
    d.ellipse(160, 74, 20, fill="wheat", w=2.4)
    d.shape([(130, 64), (190, 64), (176, 52), (160, 32), (144, 52)], fill="straw", w=2.4)
    d.line(128, 64, 192, 64, w=3)
    d.lines([(152, 72), (156, 76)], w=2, fine=False)
    d.lines([(168, 72), (164, 76)], w=2, fine=False)
    d.lines([(150, 84), (156, 88), (162, 84), (168, 88)], w=1.6, fine=False)
    for x, y in ((236, 58), (258, 44)):
        d.lines([(x - 8, y), (x - 3, y - 4), (x, y), (x + 3, y - 4), (x + 8, y)], w=1.8, smooth=True)
    d.ground(10, 310, 214, 7)
    return d


def scroll():
    d = Scene("scroll")
    d.blob([(30, 200), (46, 70), (160, 34), (290, 70), (296, 204), (160, 228)], "stone", .45)
    d.ground(34, 294)
    d.rect(72, 46, 150, 150, 2, fill="cream", w=2.6)
    d.ellipse(72, 46, 10, 10, fill="soil", w=2.2)
    d.rect(62, 40, 170, 12, 6, fill="soil", w=2.4)
    d.rect(62, 190, 170, 12, 6, fill="soil", w=2.4)
    for k in range(7):
        d.line(90, 70 + k * 15, 204 - (k * 13) % 50, 70 + k * 15, w=1.6, fine=False)
    pts = []
    for k in range(20):
        a = math.radians(k * 18)
        r = 20 if k % 2 else 16
        pts.append((196 + math.cos(a) * r, 168 + math.sin(a) * r))
    d.shape(pts, fill="red", w=2)
    d.lines([(188, 186), (182, 210), (192, 202), (198, 212), (200, 186)], w=1.8)
    d.push(rotate=40, about=(256, 110))
    d.shape([(240, 70), (262, 60), (270, 90), (258, 150), (252, 150), (246, 90)], fill="white", smooth=True, w=2.2)
    d.line(256, 150, 254, 170, w=2)
    d.pop()
    return d


def counter():
    d = Scene("counter")
    d.blob([(20, 204), (36, 78), (150, 36), (296, 70), (306, 206), (160, 230)], "stone", .45)
    d.ground(16, 306)
    d.rect(30, 140, 260, 68, 0, fill="brown", alpha=.55, w=2.8)
    d.rect(22, 128, 276, 14, 3, fill="soil", w=2.6)
    for x in (70, 160, 250):
        d.rect(x - 22, 154, 44, 40, 2, w=1.6, fine=False)
    d.push(rotate=-6, about=(120, 110))
    d.shape([(70, 126), (72, 90), (120, 96), (122, 128)], fill="paper", w=2.4)
    d.shape([(122, 128), (120, 96), (170, 90), (174, 126)], fill="paper", w=2.4)
    for k in range(3):
        d.line(80, 102 + k * 8, 112, 106 + k * 8, w=1.2, fine=False)
        d.line(130, 104 + k * 8, 162, 100 + k * 8, w=1.2, fine=False)
    d.pop()
    d.rect(214, 104, 34, 18, 3, fill="terra", w=2.2)
    d.rect(226, 84, 10, 20, 2, fill="brown", w=2)
    d.ellipse(231, 80, 9, 6, fill="brown", w=2)
    d.ellipse(262, 122, 14, 4, fill="red", alpha=.5, w=1.6, fine=False)
    d.push(rotate=-30, about=(184, 112))
    d.rect(176, 108, 50, 7, 3, fill="blue", w=1.8)
    d.pop()
    return d


def office():
    d = Scene("office")
    d.blob([(20, 204), (30, 70), (150, 30), (300, 64), (306, 206), (160, 230)], "sky", .35)
    d.ground(16, 306)
    d.rect(70, 100, 170, 108, 0, fill="cream", w=2.8)
    d.rect(60, 88, 190, 14, 0, fill="terra", w=2.6)
    for r in range(2):
        for c in range(4):
            d.rect(88 + c * 40, 116 + r * 34, 20, 22, 0, fill="sky", w=1.8)
    d.rect(140, 170, 30, 38, 0, fill="brown", w=2.2)
    d.line(155, 88, 155, 30, w=2.4)
    d.shape([(155, 32), (195, 36), (192, 52), (155, 50)], fill="terra", w=2)
    d.shape([(155, 50), (192, 52), (190, 68), (155, 66)], fill="leaf2", w=2)
    d.ellipse(172, 49, 3, w=1.2, fine=False)
    d.line(276, 208, 276, 160, w=3, stroke="#6b4a2f")
    d.ellipse(276, 142, 24, 28, fill="leaf2", w=2.2)
    d.line(34, 208, 34, 176, w=3, stroke="#6b4a2f")
    d.ellipse(34, 162, 16, 18, fill="leaf", w=2)
    return d


def clipboard():
    d = Scene("clipboard")
    d.blob([(24, 200), (40, 70), (150, 36), (296, 70), (300, 204), (160, 228)], "stone", .45)
    d.ground(24, 300)
    d.push(rotate=-6, about=(120, 120))
    d.rect(60, 44, 118, 160, 6, fill="brown", alpha=.6, w=2.6)
    d.rect(72, 60, 94, 132, 2, fill="paper", w=2)
    d.rect(98, 36, 42, 18, 4, fill="stone", w=2.4)
    for k in range(5):
        y = 80 + k * 22
        d.rect(80, y - 7, 12, 12, 2, w=1.6, fine=False)
        if k < 3:
            d.lines([(81, y - 1), (85, y + 3), (93, y - 9)], w=2.4, stroke="#2f6b3a", fine=False)
        d.line(100, y, 154 - k * 5, y, w=1.6, fine=False)
    d.pop()
    sack(d, 214, 212, 1.05, "wheat")
    sack(d, 256, 212, 1.05)
    sack(d, 236, 172, .95, "cream")
    return d


def calendar_grid():
    d = Scene("calendar-grid")
    d.blob([(24, 200), (40, 66), (150, 34), (296, 70), (300, 204), (160, 228)], "stone", .45)
    d.ground(24, 300)
    d.rect(40, 46, 178, 158, 6, fill="paper", w=2.6)
    d.rect(40, 46, 178, 28, 6, fill="leaf2", alpha=.75, w=2.2)
    for r in range(4):
        for c in range(5):
            x, y = 50 + c * 33, 84 + r * 29
            fill = "terra" if (r, c) in ((1, 1), (2, 3)) else ("wheat" if (r * 5 + c) % 4 == 0 else None)
            d.rect(x, y, 26, 22, 3, fill=fill, alpha=.7, w=1.4, fine=False)
    d.ellipse(252, 150, 38, fill="white", w=2.8)
    d.line(252, 150, 252, 124, w=3)
    d.line(252, 150, 272, 150, w=3)
    d.dot(252, 150, 3.4)
    d.lines([(234, 110), (228, 100)], w=3)
    d.lines([(270, 110), (276, 100)], w=3)
    return d


def magnifier():
    d = Scene("magnifier")
    d.blob([(24, 200), (40, 66), (150, 34), (296, 70), (300, 204), (160, 228)], "stone", .45)
    d.ground(24, 300)
    d.push(rotate=4, about=(120, 120))
    d.rect(50, 44, 124, 160, 4, fill="paper", w=2.6)
    for k in range(7):
        d.line(66, 66 + k * 16, 156 - (k % 2) * 20, 66 + k * 16, w=1.6, fine=False)
    d.pop()
    d.line(214, 208, 214, 74, w=3)
    d.shape([(214, 76), (268, 88), (214, 112)], fill="red", w=2.4)
    d.ellipse(150, 120, 38, fill="sky", alpha=.35, w=3.6)
    d.line(176, 148, 214, 190, w=9, stroke=INK)
    d.line(176, 148, 214, 190, w=4.5, stroke="#c49a6c", fine=False)
    d.lines([(134, 118), (146, 130), (166, 106)], w=3.4, stroke="#2f6b3a")
    return d


def rain_sacks():
    d = Scene("rain-sacks")
    d.blob([(20, 204), (36, 80), (150, 40), (296, 70), (306, 206), (160, 230)], "stone", .45)
    d.ground(16, 306)
    for k in range(4):
        sack(d, 110 + k * 34, 210, .95, "wheat" if k % 2 else "cream")
    for k in range(3):
        sack(d, 127 + k * 34, 172, .9, "cream" if k % 2 else "wheat")
    d.shape([(78, 176), (110, 118), (150, 104), (196, 108), (234, 130), (250, 186), (240, 170), (220, 176), (190, 164), (150, 170), (110, 168), (90, 180)],
            fill="blue", alpha=.7, smooth=True, w=2.6)
    cloud(d, 170, 52, 1.25, "stone")
    for k in range(6):
        x = 110 + k * 24
        d.line(x, 82, x - 6, 98, stroke="#3b78b8", w=2.6)
    d.shape([(50, 132), (72, 92), (94, 132)], fill="gold", w=2.4)
    d.line(72, 106, 72, 118, w=3)
    d.dot(72, 126, 2.4)
    return d


def farmers():
    d = Scene("farmers")
    d.blob([(20, 204), (36, 80), (150, 40), (296, 70), (306, 206), (160, 230)], "stone", .45)
    person(d, 92, 214, 1.15, "terra", "white")
    person(d, 228, 214, 1.15, "scarf", "leaf", scarf="pink")
    person(d, 160, 220, 1.35, "gold", "sky")
    d.ground(16, 306, 214, 3)
    return d


def district_map():
    d = Scene("map")
    d.blob([(20, 204), (36, 70), (150, 34), (296, 66), (306, 206), (160, 230)], "stone", .45)
    d.ground(16, 306)
    d.shape([(34, 70), (100, 52), (170, 70), (236, 52), (236, 190), (170, 208), (100, 190), (34, 208)], fill="leaf", alpha=.6, w=2.6)
    d.line(100, 52, 100, 190, w=1.6, fine=False)
    d.line(170, 70, 170, 208, w=1.6, fine=False)
    d.lines([(48, 120), (90, 104), (130, 140), (190, 116), (224, 150)], w=2.4, stroke="#3b78b8", smooth=True)
    for x, y in ((80, 96), (150, 160), (206, 96)):
        d.shape([(x, y), (x - 10, y - 18), (x - 8, y - 30), (x, y - 34), (x + 8, y - 30), (x + 10, y - 18)], fill="red", smooth=True, w=2.2)
        d.ellipse(x, y - 24, 4, fill="white", w=1.2, fine=False)
    for k, hh in enumerate((40, 64, 30, 80)):
        d.rect(250 + k * 14, 208 - hh, 10, hh, 1, fill="wheat" if k % 2 else "terra", w=1.8)
    return d


def signpost():
    d = Scene("signpost")
    d.blob([(24, 200), (40, 66), (150, 34), (296, 70), (300, 204), (160, 228)], "stone", .45)
    d.ground(24, 300)
    d.line(150, 212, 150, 120, w=5, stroke="#6b4a2f")
    d.shape([(150, 28), (214, 132), (86, 132)], fill="gold", w=3)
    d.line(150, 62, 150, 100, w=7)
    d.dot(150, 116, 4.5)
    for side in (-1, 1):
        d.arc(150, 88, 84, (205 if side < 0 else -25), (235 if side < 0 else 5), w=2.6, stroke=TERRA)
    sprout(d, 70, 212, 1.2)
    sprout(d, 238, 212, 1)
    return d


def badges():
    d = Scene("badges")
    d.blob([(24, 200), (40, 66), (150, 34), (296, 70), (300, 204), (160, 228)], "stone", .45)
    d.ground(24, 300)
    for k, (x, rot, fill) in enumerate(((100, -8, "leaf"), (210, 7, "terra"))):
        d.push(rotate=rot, about=(x, 120))
        d.lines([(x - 22, 40), (x, 90), (x + 22, 40)], w=2.2, stroke="#3b78b8")
        d.rect(x - 38, 90, 76, 104, 8, fill="paper", w=2.6)
        d.rect(x - 38, 90, 76, 22, 8, fill=fill, alpha=.8, w=2)
        d.rect(x - 8, 84, 16, 12, 3, fill="stone", w=1.8)
        d.ellipse(x, 136, 15, 16, fill="sky", w=2)
        d.arc(x, 162, 15, 200, 340, w=2)
        d.line(x - 24, 176, x + 24, 176, w=1.8, fine=False)
        d.line(x - 18, 186, x + 18, 186, w=1.8, fine=False)
        d.pop()
    return d


def notebook():
    d = Scene("notebook")
    d.blob([(24, 200), (40, 66), (150, 34), (296, 70), (300, 204), (160, 228)], "stone", .45)
    d.ground(24, 300)
    d.shape([(40, 190), (44, 60), (150, 70), (150, 200)], fill="paper", w=2.6)
    d.shape([(150, 200), (150, 70), (256, 60), (262, 190)], fill="paper", w=2.6)
    for k in range(6):
        y = 90 + k * 18
        d.line(58, y - 3, 138, y, w=1.3, stroke="#8aa0b8", fine=False)
        d.line(162, y, 244, y - 3, w=1.3, stroke="#8aa0b8", fine=False)
    for k in range(5):
        y = 88 + k * 20
        d.ellipse(66, y, 4.5, fill="terra" if k == 2 else "leaf2", w=1.6, fine=False)
        d.line(76, y, 128 - (k * 7) % 30, y + 1, w=1.8, fine=False)
    d.line(66, 92, 66, 172, w=1.4, stroke="#6f8f4a", fine=False)
    d.push(rotate=-35, about=(230, 130))
    d.rect(186, 126, 100, 12, 4, fill="gold", w=2.2)
    d.shape([(186, 126), (170, 132), (186, 138)], fill="cream", w=2)
    d.rect(272, 126, 14, 12, 2, fill="red", w=1.8)
    d.pop()
    return d


def weighbridge():
    d = Scene("weighbridge")
    d.blob([(20, 204), (36, 80), (150, 40), (296, 70), (306, 206), (160, 230)], "stone", .45)
    d.ground(16, 306)
    d.rect(40, 190, 170, 16, 2, fill="stone", w=2.8)
    d.rect(52, 206, 14, 8, 0, w=2, fine=False)
    d.rect(184, 206, 14, 8, 0, w=2, fine=False)
    for k in range(3):
        sack(d, 80 + k * 44, 190, 1.05, "wheat" if k == 1 else "cream")
    sack(d, 102, 150, .95, "cream")
    sack(d, 146, 150, .95, "wheat")
    d.rect(232, 110, 60, 96, 6, fill="leaf", alpha=.7, w=2.6)
    d.ellipse(262, 146, 22, fill="white", w=2.4)
    for k in range(7):
        a = math.radians(200 + k * 23)
        d.line(262 + math.cos(a) * 16, 146 + math.sin(a) * 16, 262 + math.cos(a) * 20, 146 + math.sin(a) * 20, w=1.4, fine=False)
    d.line(262, 146, 276, 132, w=2.6, stroke=TERRA)
    d.dot(262, 146, 2.6)
    d.rect(244, 176, 36, 14, 2, fill="dark", alpha=.6, w=1.8)
    return d


def basket():
    d = Scene("basket", 240, 180)
    d.blob([(20, 150), (30, 50), (120, 24), (220, 50), (224, 150), (120, 172)], "stone", .4)
    d.ground(24, 216, 160, 3)
    d.shape([(52, 104), (188, 104), (172, 156), (68, 156)], fill="soil", w=2.6)
    d.ellipse(120, 104, 68, 12, fill="brown", alpha=.5, w=2.4)
    for k in range(5):
        d.line(66 + k * 26, 114, 76 + k * 22, 154, w=1.2, stroke="#8a6a3a", fine=False)
    for k in range(3):
        d.line(58 + k * 4, 122 + k * 12, 182 - k * 4, 122 + k * 12, w=1.2, stroke="#8a6a3a", fine=False)
    d.arc(120, 104, 60, 190, 350, w=2.6)
    sprout(d, 150, 98, 1.1)
    return d


def footer_field():
    """a strip of grass and wheat heads for the top edge of the footer, one colour"""
    d = Scene("footer-field", 480, 60, seed=5)
    c = "#183a2c"
    pts = [(0, 60), (0, 40)]
    x = 0
    while x < 480:
        pts.append((x + 6, 34 + d.rng.uniform(-6, 6)))
        x += 12
    pts += [(480, 40), (480, 60)]
    d.layers["ink"].append('<path d="%s" fill="%s"/>' % (Scene._d(pts, True), c))
    for k in range(9):
        x = 20 + k * 52 + d.rng.uniform(-8, 8)
        h = d.rng.uniform(22, 34)
        d.layers["ink"].append('<path d="M%s 42 Q%s %s %s %s" stroke="%s" stroke-width="2"/>' % (f(x), f(x + 3), f(42 - h / 2), f(x + 5), f(42 - h), c))
        for j in range(4):
            yy = 42 - h + 4 + j * 5
            d.layers["ink"].append('<ellipse cx="%s" cy="%s" rx="2.4" ry="4" fill="%s" transform="rotate(-25 %s %s)"/>'
                                   % (f(x + 2), f(yy), c, f(x + 2), f(yy)))
            d.layers["ink"].append('<ellipse cx="%s" cy="%s" rx="2.4" ry="4" fill="%s" transform="rotate(25 %s %s)"/>'
                                   % (f(x + 8), f(yy), c, f(x + 8), f(yy)))
    return d


SCENES = {
    "phone-otp": phone_otp, "otp-lock": otp_lock, "register-card": register_card, "voice": voice,
    "mandi": mandi, "calendar": calendar, "ticket": ticket, "gate": gate, "bank": bank,
    "bell": bell, "profile": profile, "seal": seal, "scarecrow": scarecrow, "scroll": scroll, "counter": counter,
    "office": office, "clipboard": clipboard, "calendar-grid": calendar_grid, "magnifier": magnifier,
    "rain-sacks": rain_sacks, "farmers": farmers, "map": district_map, "signpost": signpost, "badges": badges,
    "notebook": notebook, "weighbridge": weighbridge, "basket": basket, "footer-field": footer_field,
    "pin": pin,
}


def main(names):
    os.makedirs(OUT, exist_ok=True)
    for name in names or SCENES:
        with open(os.path.join(OUT, name + ".svg"), "w", encoding="utf-8") as fh:
            fh.write(SCENES[name]().svg())
        print(name)


if __name__ == "__main__":
    main(sys.argv[1:])
