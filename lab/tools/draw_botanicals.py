"""Line drawings of the six MSP crops for the field-notebook design.

    python lab/tools/draw_botanicals.py

Writes lab/designs/field-notebook/art/<crop>.svg. Ink lines with a light wash
of each part's real colour: green leaves and stalks, golden grain, yellow
mustard flowers, pink gram flowers.
Drawn from simple geometry with a fixed seed, so re-running gives the same
pictures.
"""
import math
import os
import random

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "designs", "field-notebook", "art")


def f(v):
    return ("%.1f" % v).rstrip("0").rstrip(".")


def poly(pts, close=False):
    d = "M" + " L".join("%s %s" % (f(x), f(y)) for x, y in pts)
    return d + (" Z" if close else "")


def rot(x, y, a):
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c


def bez(p0, p1, p2, p3, t):
    u = 1 - t
    x = u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0]
    y = u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]
    return x, y


def bez_tan(p0, p1, p2, p3, t):
    u = 1 - t
    dx = 3 * u * u * (p1[0] - p0[0]) + 6 * u * t * (p2[0] - p1[0]) + 3 * t * t * (p3[0] - p2[0])
    dy = 3 * u * u * (p1[1] - p0[1]) + 6 * u * t * (p2[1] - p1[1]) + 3 * t * t * (p3[1] - p2[1])
    return math.atan2(dy, dx)


def curve(c, a=0.0, b=1.0, n=40):
    return [bez(*c, a + (b - a) * i / n) for i in range(n + 1)]


# per crop: part -> (line colour, wash colour or None, wash opacity)
COLOURS = {
    "wheat": {"stem": ("#a88a3c", None, 0), "grain": ("#8f6418", "#e3b458", .55), "awn": ("#b58f45", None, 0),
              "leaf": ("#7e8c3c", "#b4bd6a", .3), "twine": ("#7a5a2e", None, 0)},
    "paddy": {"stem": ("#7f8a3a", None, 0), "rachis": ("#9a8436", None, 0), "grain": ("#9c7317", "#e8bf45", .65),
              "leaf": ("#4f8434", "#8fbf5c", .3)},
    "mustard": {"stem": ("#4c7a30", None, 0), "pod": ("#5f8a36", "#9cc267", .4), "flower": ("#c79a00", "#f5d224", .9),
                "bud": ("#8f9a20", "#d6d44a", .7), "leaf": ("#467a2e", "#86b85c", .35)},
    "gram": {"stem": ("#5a7a38", None, 0), "leaf": ("#4b7a34", "#8cbf63", .45), "pod": ("#8a8a45", "#c9c98a", .55),
             "flower": ("#a8466f", "#e39ab8", .75)},
    "maize": {"stem": ("#5c8636", None, 0), "cob": ("#b98612", "#f2c53a", .75), "silk": ("#9b5a2a", None, 0),
              "husk": ("#6f963e", "#b5d27c", .45), "leaf": ("#4f8434", "#8fbf5c", .3)},
    "bajra": {"stem": ("#6f8a3a", None, 0), "spike": ("#7a6648", "#b8a47e", .5), "bristle": ("#8b7a58", None, 0),
              "leaf": ("#55853a", "#93bf66", .3)},
}


class Layer(list):
    """A list of path data that remembers which part of the plant each path is."""
    def __init__(self, drawing):
        super().__init__()
        self.drawing = drawing

    def append(self, d):
        super().append((self.drawing.part, d))


class Drawing:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.part = "stem"
        self.bold, self.main, self.fine = Layer(self), Layer(self), Layer(self)

    def svg(self, colours):
        out = []
        for layer, sw, cls in ((self.bold, 1.8, "l1"), (self.main, 1.2, "l2"), (self.fine, .7, "l3")):
            parts = []
            for part, _ in layer:
                if part not in parts:
                    parts.append(part)
            for part in parts:
                line, wash, alpha = colours[part]
                for closed in (False, True):
                    paths = [d for pt, d in layer if pt == part and d.endswith(" Z") == closed]
                    if not paths:
                        continue
                    fill = ' fill="%s" fill-opacity="%s"' % (wash, alpha) if closed and wash and cls == "l2" else ""
                    out.append('<g class="%s" stroke="%s" stroke-width="%s"%s>%s</g>' % (
                        cls, line, sw, fill, "".join('<path d="%s"/>' % d for d in paths)))
        return ('<svg xmlns="http://www.w3.org/2000/svg" class="botanical" width="%d" height="%d" viewBox="0 0 %d %d" fill="none" '
                'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
                '%s</svg>\n') % (self.w, self.h, self.w, self.h, "".join(out))

    # ---- parts

    def almond(self, cx, cy, ang, length, width, crease=True, hatch=0, fill_side=1):
        pts_top, pts_bot = [], []
        n = 14
        for i in range(n + 1):
            t = -1 + 2 * i / n
            x = t * length / 2
            y = width / 2 * (1 - t * t) ** .75
            pts_top.append(rot(x, -y, ang))
            pts_bot.append(rot(x, y, ang))
        outline = [(cx + x, cy + y) for x, y in pts_top] + [(cx + x, cy + y) for x, y in reversed(pts_bot)]
        self.main.append(poly(outline, close=True))
        if crease:
            a = rot(-length * .32, 0, ang)
            b = rot(length * .3, 0, ang)
            self.fine.append(poly([(cx + a[0], cy + a[1]), (cx + b[0], cy + b[1])]))
        for k in range(hatch):
            t = -.5 + k / max(1, hatch - 1) * .9
            x = t * length / 2
            y = width / 2 * (1 - t * t) ** .75
            p = rot(x, fill_side * y * .85, ang)
            q = rot(x + length * .05, fill_side * y * .3, ang)
            self.fine.append(poly([(cx + p[0], cy + p[1]), (cx + q[0], cy + q[1])]))

    def leaf(self, base, ctrl1, ctrl2, tip, width, veins=0, twist=None, wave=0.0, rng=None):
        """A blade along a cubic curve, widest a third of the way up."""
        c = (base, ctrl1, ctrl2, tip)
        n = 36
        left, right, mid = [], [], []
        for i in range(n + 1):
            t = i / n
            x, y = bez(*c, t)
            a = bez_tan(*c, t)
            w = width * math.sin(math.pi * min(1, t ** .8)) * (1 - .15 * t)
            if wave:
                w *= 1 + wave * math.sin(t * 38)
            nx, ny = -math.sin(a), math.cos(a)
            wl, wr = w, w
            if twist is not None and t > twist:
                # past the twist the blade shows its edge: narrow on one side
                k = min(1, (t - twist) / .12)
                wr = w * (1 - .8 * k)
            left.append((x + nx * wl, y + ny * wl))
            right.append((x - nx * wr, y - ny * wr))
            mid.append((x, y))
        self.main.append(poly(left + list(reversed(right)), close=True))
        self.fine.append(poly(mid[2:-4]))
        for k in range(veins):
            t = .12 + .75 * k / max(1, veins - 1)
            i = int(t * n)
            x, y = mid[i]
            a = bez_tan(*c, t)
            for side in (1, -1):
                ex = x + math.cos(a + side * .55) * width * .9
                ey = y + math.sin(a + side * .55) * width * .9
                self.fine.append(poly([(x, y), ((x + ex) / 2 + (ex - x) * .1, (y + ey) / 2), (ex, ey)]))

    def stem(self, c, width=1.6, nodes=()):
        pts = curve(c, n=60)
        self.bold.append(poly(pts))
        # a second, finer line gives the stalk a little body
        off = []
        for i, (x, y) in enumerate(pts):
            a = bez_tan(*c, i / 60)
            off.append((x - math.sin(a) * width, y + math.cos(a) * width))
        self.fine.append(poly(off[3:-3]))
        for t in nodes:
            x, y = bez(*c, t)
            a = bez_tan(*c, t)
            nx, ny = -math.sin(a) * 3.2, math.cos(a) * 3.2
            self.main.append(poly([(x - nx, y - ny), (x + nx * 1.6, y + ny * 1.6)]))


# ---- the crops

def wheat(rng, ox=0, oy=0, sc=1.0, lean=0.0, d=None, leaves=True):
    d = d or Drawing(220, 420)
    S = lambda x, y: (ox + x * sc, oy + y * sc)
    c = (S(110, 415), S(108 + lean * 20, 300), S(104 + lean * 50, 190), S(112 + lean * 70, 40))
    d.part = "stem"
    d.stem(c, nodes=(.34, .62))
    ear_from, ear_to = .6, .985
    n = 12
    for i in range(n):
        t = ear_from + (ear_to - ear_from) * i / (n - 1)
        x, y = bez(*c, t)
        a = bez_tan(*c, t)
        size = 1 - .35 * (i / (n - 1)) ** 2
        for side in (-1, 1):
            spread = .5 + .08 * rng.random()
            ga = a + side * spread
            gx = x + math.cos(ga) * 12.5 * sc * size
            gy = y + math.sin(ga) * 12.5 * sc * size
            d.part = "grain"
            d.almond(gx, gy, ga, 22 * sc * size, 10.5 * sc * size, hatch=3, fill_side=side)
            # the glume behind each grain
            gl = [(x, y), (x + math.cos(a + side * .9) * 9 * sc * size, y + math.sin(a + side * .9) * 9 * sc * size)]
            d.fine.append(poly(gl))
            # the awn: long, faintly bowed
            d.part = "awn"
            tx = gx + math.cos(ga) * 11 * sc * size
            ty = gy + math.sin(ga) * 11 * sc * size
            al = (48 + 22 * rng.random()) * sc * (1 - .25 * i / n)
            aa = ga - side * .22
            mx = tx + math.cos(aa + side * .06) * al / 2
            my = ty + math.sin(aa + side * .06) * al / 2
            ex = tx + math.cos(aa) * al
            ey = ty + math.sin(aa) * al
            d.fine.append("M%s %s Q%s %s %s %s" % (f(tx), f(ty), f(mx), f(my), f(ex), f(ey)))
    x, y = bez(*c, 1)
    a = bez_tan(*c, 1)
    d.part = "grain"
    d.almond(x + math.cos(a) * 6 * sc, y + math.sin(a) * 6 * sc, a, 16 * sc, 8 * sc)
    d.part = "awn"
    d.fine.append(poly([(x + math.cos(a) * 14 * sc, y + math.sin(a) * 14 * sc),
                        (x + math.cos(a) * 60 * sc, y + math.sin(a) * 60 * sc)]))
    if leaves:
        d.part = "leaf"
        bx, by = bez(*c, .34)
        d.leaf((bx, by), S(60, 330), S(20, 300), S(8, 214), 9 * sc, twist=.55)
        bx, by = bez(*c, .62)
        d.leaf((bx, by), S(150, 220), S(190, 200), S(212, 262), 7.5 * sc, twist=.6)
    return d


def wheat_bundle(rng):
    d = Drawing(300, 440)
    wheat(rng, ox=38, oy=22, sc=.95, lean=-.9, d=d, leaves=False)
    wheat(rng, ox=58, oy=34, sc=.92, lean=.9, d=d, leaves=False)
    wheat(rng, ox=40, oy=0, sc=1.0, lean=.05, d=d)
    # the twine that ties them
    d.part = "twine"
    for k in range(3):
        y = 352 + k * 5
        d.main.append("M136 %d Q150 %d 168 %d" % (y, y + 4, y - 2))
    return d


def paddy(rng):
    d = Drawing(260, 420)
    c = ((70, 415), (78, 260), (88, 110), (122, 52))
    d.stem(c, nodes=(.3, .55))
    arch = ((122, 52), (150, 6), (205, 20), (222, 150))
    pts = curve(arch, n=60)
    d.part = "rachis"
    d.bold.append(poly(pts))
    for k in range(12):
        t = .06 + .9 * k / 11
        x, y = bez(*arch, t)
        a = bez_tan(*arch, t)
        for side in ((-1, 1) if k % 2 == 0 else (1,)):
            ba = a + side * .9 + (.5 if side > 0 else -.1)
            ba = math.pi / 2 + (ba - math.pi / 2) * .35  # branches hang
            length = (48 + 30 * math.sin(math.pi * t)) * (.8 + .3 * rng.random())
            bc = ((x, y), (x + math.cos(a) * 10, y + math.sin(a) * 10),
                  (x + math.cos(ba) * length * .6 + side * 6, y + math.sin(ba) * length * .5),
                  (x + math.cos(ba) * length + side * 4, y + math.sin(ba) * length))
            d.part = "rachis"
            d.main.append(poly(curve(bc, n=16)))
            d.part = "grain"
            for j in range(7):
                tt = .2 + .78 * j / 6
                gx, gy = bez(*bc, tt)
                ga = bez_tan(*bc, tt) + (.55 if j % 2 else -.55)
                d.almond(gx + math.cos(ga) * 5, gy + math.sin(ga) * 5, ga, 11, 5, crease=False, hatch=2)
    d.part = "leaf"
    d.leaf((74, 330), (30, 260), (20, 190), (40, 120), 7, twist=.6)
    d.leaf((78, 260), (130, 210), (170, 220), (200, 300), 6.5, twist=.55)
    d.leaf((71, 395), (120, 360), (160, 360), (195, 400), 6, twist=.5)
    return d


def mustard(rng):
    d = Drawing(240, 420)
    main = ((120, 415), (116, 300), (130, 180), (120, 40))
    d.stem(main, nodes=(.42,))
    branches = [
        ((119, 250), (100, 200), (70, 170), (58, 110)),
        ((124, 210), (150, 170), (180, 140), (190, 90)),
    ]
    for b in branches:
        d.stem(b, width=1.2)
    for c, (t0, t1) in [(main, (.5, .88)), (branches[0], (.25, .8)), (branches[1], (.25, .8))]:
        for k in range(6):
            t = t0 + (t1 - t0) * k / 5
            x, y = bez(*c, t)
            a = bez_tan(*c, t)
            side = 1 if k % 2 else -1
            pa = a + side * .5
            px = x + math.cos(a + side * .9) * 2
            py = y + math.sin(a + side * .9) * 2
            d.part = "stem"
            d.fine.append(poly([(x, y), (px, py)]))
            d.part = "pod"
            d.almond(px + math.cos(pa) * 16, py + math.sin(pa) * 16, pa, 30, 4.2, crease=True)
            bx, by = px + math.cos(pa) * 31, py + math.sin(pa) * 31
            d.fine.append(poly([(bx, by), (bx + math.cos(pa) * 5, by + math.sin(pa) * 5)]))
    for c in [main] + branches:
        x, y = bez(*c, 1)
        for k in range(5):
            ang = -math.pi / 2 + (k - 2) * .55 + rng.uniform(-.1, .1)
            r = 14 if k % 2 == 0 else 22
            fx, fy = x + math.cos(ang) * r * .55, y + math.sin(ang) * r * .55 + 6
            d.part = "stem"
            d.fine.append(poly([(x, y + 4), (fx, fy)]))
            d.part = "flower" if k % 2 == 0 else "bud"
            if k % 2 == 0:
                for p in range(4):
                    pa = p * math.pi / 2 + .4 + ang
                    d.almond(fx + math.cos(pa) * 5.2, fy + math.sin(pa) * 5.2, pa, 9, 6.5, crease=False)
                d.fine.append("M%s %sm-1.4 0a1.4 1.4 0 1 0 2.8 0a1.4 1.4 0 1 0 -2.8 0" % (f(fx), f(fy)))
            else:
                d.almond(fx, fy, ang, 7, 4.5, crease=False)
    d.part = "leaf"
    d.leaf((118, 380), (80, 360), (40, 350), (14, 300), 18, veins=5, wave=.12)
    d.leaf((120, 345), (160, 335), (195, 320), (220, 275), 14, veins=4, wave=.12)
    return d


def gram(rng):
    d = Drawing(240, 420)
    stem = [(118, 415), (112, 340), (130, 270), (112, 190), (128, 110), (118, 40)]
    for i in range(len(stem) - 1):
        a, b = stem[i], stem[i + 1]
        d.bold.append("M%s %s Q%s %s %s %s" % (f(a[0]), f(a[1]), f((a[0] + b[0]) / 2 + 4), f((a[1] + b[1]) / 2), f(b[0]), f(b[1])))

    def compound(x, y, ang, length, pairs):
        ex, ey = x + math.cos(ang) * length, y + math.sin(ang) * length
        d.part = "stem"
        d.main.append(poly([(x, y), (ex, ey)]))
        d.part = "leaf"
        for k in range(pairs):
            t = .25 + .7 * k / max(1, pairs - 1)
            px, py = x + math.cos(ang) * length * t, y + math.sin(ang) * length * t
            for side in (-1, 1):
                la = ang + side * 1.0
                d.almond(px + math.cos(la) * 7, py + math.sin(la) * 7, la, 13, 7.5, crease=True)
        d.almond(ex + math.cos(ang) * 6, ey + math.sin(ang) * 6, ang, 13, 7.5)

    for (x, y), side in zip(stem[1:-1], (1, -1, 1, -1)):
        compound(x, y, -math.pi / 2 + side * 1.0, 62, 4)
    compound(118, 40, -math.pi / 2, 30, 2)
    # pods, puffed, each on a short stalk
    for (x, y, side) in [(112, 340, -1), (130, 270, 1), (112, 190, -1), (128, 110, 1)]:
        px, py = x + side * 22, y + 26
        d.part = "stem"
        d.main.append("M%s %s Q%s %s %s %s" % (f(x), f(y), f(x + side * 16), f(y + 4), f(px), f(py - 10)))
        a = math.pi / 2 + side * .35
        d.part = "pod"
        d.almond(px, py + 4, a, 30, 20, crease=False, hatch=4, fill_side=-side)
        tip = (px + math.cos(a) * 16, py + 4 + math.sin(a) * 16)
        d.fine.append(poly([tip, (tip[0] + side * 3, tip[1] + 5)]))
    # one flower
    fx, fy = 150, 58
    d.part = "flower"
    for p in range(5):
        pa = p * 2 * math.pi / 5
        d.almond(fx + math.cos(pa) * 5, fy + math.sin(pa) * 5, pa, 10, 7, crease=False)
    d.part = "stem"
    d.main.append("M%s %s Q%s %s %s %s" % (f(128), f(110), f(144), f(90), f(fx), f(fy + 7)))
    return d


def maize(rng):
    d = Drawing(240, 420)
    d.stem(((120, 415), (122, 330), (118, 250), (122, 150)), width=2.2, nodes=(.35, .75))
    # the cob, leaning out of its husk
    cx, cy, ang = 150, 170, -1.2
    L, W = 150, 44
    d.part = "cob"
    outline_t, outline_b = [], []
    for i in range(31):
        t = -1 + 2 * i / 30
        x = t * L / 2
        w = W / 2 * (1 - (max(0, t) ** 3) * .75) * (1 - (min(0, t) ** 4) * .5)
        outline_t.append(rot(x, -w, ang))
        outline_b.append(rot(x, w, ang))
    d.main.append(poly([(cx + x, cy + y) for x, y in outline_t] + [(cx + x, cy + y) for x, y in reversed(outline_b)], close=True))
    for r in range(-3, 4):
        row = []
        for i in range(2, 29):
            t = -1 + 2 * i / 30
            x = t * L / 2
            w = W / 2 * (1 - (max(0, t) ** 3) * .75) * (1 - (min(0, t) ** 4) * .5)
            row.append(rot(x, r / 3.6 * w, ang))
        d.fine.append(poly([(cx + x, cy + y) for x, y in row]))
        # kernel breaks along the row
        for i in range(3, 28, 2):
            t = -1 + 2 * i / 30
            x = t * L / 2
            w = W / 2 * (1 - (max(0, t) ** 3) * .75) * (1 - (min(0, t) ** 4) * .5)
            p = rot(x, (r / 3.6) * w, ang)
            q = rot(x, ((r + .9) / 3.6) * w, ang)
            if abs(r + .9) <= 3.4:
                d.fine.append(poly([(cx + p[0], cy + p[1]), (cx + q[0], cy + q[1])]))
    # silk from the tip
    d.part = "silk"
    tip = rot(L / 2, 0, ang)
    tx, ty = cx + tip[0], cy + tip[1]
    for k in range(7):
        a = ang + (k - 3) * .16
        d.fine.append("M%s %s C%s %s %s %s %s %s" % (
            f(tx), f(ty), f(tx + math.cos(a) * 20 + 8), f(ty + math.sin(a) * 20),
            f(tx + math.cos(a) * 30 - 10), f(ty + math.sin(a) * 38), f(tx + math.cos(a) * 48 + rng.uniform(-6, 6)), f(ty + math.sin(a) * 50)))
    # husk leaves wrapping the base of the cob
    base = rot(-L / 2, 0, ang)
    bx, by = cx + base[0], cy + base[1]
    d.part = "husk"
    d.leaf((bx, by), (bx - 30, by - 30), (bx - 10, by - 110), (bx + 40, by - 150), 16, twist=None)
    d.leaf((bx, by), (bx + 40, by - 10), (bx + 80, by - 60), (bx + 100, by - 100), 14)
    d.part = "leaf"
    d.leaf((120, 330), (70, 300), (30, 300), (10, 360), 11, twist=.5, veins=0)
    d.leaf((122, 150), (100, 80), (70, 50), (30, 30), 9, twist=.6)
    return d


def bajra(rng):
    d = Drawing(220, 420)
    c = ((110, 415), (108, 330), (112, 250), (110, 205))
    d.stem(c, nodes=(.4,))
    # the spike: a long candle of tiny grains with bristles
    top, bottom = 22, 205
    for i in range(0, 34):
        y = bottom - (bottom - top) * i / 33
        t = i / 33
        w = 13 * (1 - (t ** 6) * .75) * (1 - ((1 - t) ** 10) * .5)
        d_off = 1.2 * math.sin(i)
        for j in range(-2, 3):
            x = 110 + j / 2.3 * w + d_off + (2 if i % 2 else 0)
            if abs(j / 2.3 * w) > w:
                continue
            d.part = "spike"
            d.fine.append("M%s %sm-1.8 0a1.8 1.8 0 1 0 3.6 0a1.8 1.8 0 1 0 -3.6 0" % (f(x), f(y)))
        if i % 3 == 0:
            d.part = "bristle"
            for side in (-1, 1):
                d.fine.append(poly([(110 + side * w, y), (110 + side * (w + 6 + rng.random() * 3), y - 4)]))
    left = [(110 - 13 * (1 - ((i / 33) ** 6) * .75) * (1 - ((1 - i / 33) ** 10) * .5), bottom - (bottom - top) * i / 33) for i in range(34)]
    right = [(220 - x, y) for x, y in left]
    d.part = "spike"
    d.main.append(poly(left + [(110, top - 6)] + list(reversed(right)), close=True))
    d.part = "leaf"
    d.leaf((109, 340), (60, 300), (30, 250), (20, 170), 10, twist=.55)
    d.leaf((111, 280), (150, 250), (180, 250), (205, 300), 8, twist=.5)
    return d


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, fn in [("wheat", lambda r: wheat(r)), ("wheat-bundle", wheat_bundle), ("paddy", paddy),
                     ("mustard", mustard), ("gram", gram), ("maize", maize), ("bajra", bajra)]:
        rng = random.Random(name)
        with open(os.path.join(OUT, name + ".svg"), "w", encoding="utf-8") as fh:
            fh.write(fn(rng).svg(COLOURS[name.split("-")[0]]))
        print(name)


if __name__ == "__main__":
    main()
