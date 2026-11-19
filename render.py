#!/usr/bin/env python3
"""Build-time renderer for the 18 November 2026 world-news image.

Runs once on the author's machine (needs Pillow and Natural Earth land GeoJSON) and
writes assets/entry.png. The graded entry (main.py) never runs this file; it only
copies the committed PNG, so the output is byte-identical on every run.

Usage:
    python3 render.py --land110 ne_110m_land.geojson --land50 ne_50m_land.geojson
"""
import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = HERE / "assets" / "fonts"
OUT = HERE / "assets" / "entry.png"

S = 2            # supersampling factor; drawn at 2048 px, downsampled to 1024 px
W = H = 1024

PAPER = (246, 243, 236)
INK = (17, 24, 39)
MUTED = (78, 86, 99)
RULE = (206, 199, 186)
NAVY = (13, 27, 46)
GOLD = (245, 190, 80)
RED = (196, 18, 48)
TEAL = (13, 118, 110)
INDIGO = (67, 56, 202)
AMBER = (176, 84, 10)
PLUM = (128, 30, 140)
LAND_DOT = (186, 177, 161)
INSET_LAND = (228, 221, 207)
INSET_WATER = (210, 224, 231)


# ---------------------------------------------------------------- fonts & text
def poppins(weight, size):
    return ImageFont.truetype(str(FONTS / f"Poppins-{weight}.ttf"), round(size * S))


def lora(size, weight=b"Bold"):
    f = ImageFont.truetype(str(FONTS / "Lora-Variable.ttf"), round(size * S))
    for name in f.get_variation_names():
        if name == weight:
            f.set_variation_by_name(name)
    return f


def wrap(d, text, font, maxw):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if d.textlength(trial, font=font) <= maxw * S:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def para(d, x, y, text, font, maxw, lh, fill, max_lines):
    """Draw wrapped text; refuse to render anything that would overflow its box."""
    lines = wrap(d, text, font, maxw)
    if len(lines) > max_lines:
        raise SystemExit(f"text overflow ({len(lines)}>{max_lines}): {text[:50]!r}")
    for i, line in enumerate(lines):
        d.text((x * S, (y + i * lh) * S), line, font=font, fill=fill)
    return y + len(lines) * lh


def text(d, x, y, s, font, fill, anchor="la", stroke=0, stroke_fill=None):
    d.text((x * S, y * S), s, font=font, fill=fill, anchor=anchor,
           stroke_width=round(stroke * S), stroke_fill=stroke_fill)


def spaced(d, x, y, s, font, fill, tracking=1.2):
    """Small caps-style kicker with letter spacing."""
    cx = x * S
    for ch in s:
        d.text((cx, y * S), ch, font=font, fill=fill)
        cx += d.textlength(ch, font=font) + tracking * S
    return cx / S


def rect(d, x0, y0, x1, y1, fill=None, outline=None, width=1):
    d.rectangle((x0 * S, y0 * S, x1 * S, y1 * S), fill=fill, outline=outline,
                width=round(width * S) if outline else 0)


def disc(d, cx, cy, r, fill=None, outline=None, width=1):
    d.ellipse(((cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S), fill=fill,
              outline=outline, width=round(width * S) if outline else 0)


def badge(d, cx, cy, n, color, r=10):
    disc(d, cx, cy, r, fill=color)
    text(d, cx, cy + 0.5, str(n), poppins("Bold", r * 1.25), (255, 255, 255), anchor="mm")


def kicker(d, x, y, n, label, color):
    badge(d, x + 9, y + 8, n, color, r=9)
    spaced(d, x + 24, y, label, poppins("Bold", 11.5), color, tracking=1.3)


# ---------------------------------------------------------------- geography
def rings(geojson_path):
    data = json.loads(Path(geojson_path).read_text())
    out = []
    for feat in data["features"]:
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            out.append(poly[0])          # exterior ring only (land, no lakes needed)
    return out


def draw_dot_map(img, land, x0, y0, w, lat_top, lat_bot, step=6.5, r=1.9):
    """Dot-matrix world map, equirectangular, lon -180..180."""
    h = w * (lat_top - lat_bot) / 360.0
    mw, mh = int(w * S), int(h * S)
    mask = Image.new("L", (mw, mh), 0)
    md = ImageDraw.Draw(mask)
    for ring in land:
        pts = [((lon + 180) / 360 * mw, (lat_top - lat) / (lat_top - lat_bot) * mh)
               for lon, lat in ring]
        if len(pts) >= 3:
            md.polygon(pts, fill=255)
    d = ImageDraw.Draw(img)
    rows = int(h / step)
    cols = int(w / step)
    for j in range(rows + 1):
        for i in range(cols + 1):
            px, py = i * step + step / 2, j * step + step / 2
            if px >= w or py >= h:
                continue
            if mask.getpixel((int(px * S), int(py * S))) > 0:
                disc(d, x0 + px, y0 + py, r, fill=LAND_DOT)

    def proj(lon, lat):
        return x0 + (lon + 180) / 360 * w, y0 + (lat_top - lat) / (lat_top - lat_bot) * h
    return proj, h


def draw_inset(img, land, x0, y0, w, h, lon0, lon1, lat1):
    """Equirectangular inset with cos(latitude) correction; returns projector."""
    d = ImageDraw.Draw(img)
    mid = math.radians(28.0)
    kx = w / ((lon1 - lon0) * math.cos(mid))
    k = kx                                # pixels per degree of latitude

    def proj(lon, lat):
        return x0 + (lon - lon0) * math.cos(mid) * k, y0 + (lat1 - lat) * k

    rect(d, x0, y0, x0 + w, y0 + h, fill=INSET_WATER)
    layer = Image.new("RGB", img.size, INSET_WATER)
    ld = ImageDraw.Draw(layer)
    for ring in land:
        lons = [p[0] for p in ring]
        lats = [p[1] for p in ring]
        if max(lons) < lon0 - 5 or min(lons) > lon1 + 5 or min(lats) > lat1 + 5:
            continue
        pts = [(proj(lon, lat)[0] * S, proj(lon, lat)[1] * S) for lon, lat in ring]
        ld.polygon(pts, fill=INSET_LAND, outline=(196, 186, 168))
    box = (int(x0 * S), int(y0 * S), int((x0 + w) * S), int((y0 + h) * S))
    img.paste(layer.crop(box), box[:2])
    rect(d, x0, y0, x0 + w, y0 + h, outline=RULE, width=1)
    return proj


def burst(d, x, y, color):
    for r, a in ((15, 1.2), (10, 1.6)):
        disc(d, x, y, r, outline=color, width=a)
    disc(d, x, y, 5, fill=color)


# ---------------------------------------------------------------- page
def render(land110, land50):
    img = Image.new("RGB", (W * S, H * S), PAPER)
    d = ImageDraw.Draw(img)

    # Masthead ---------------------------------------------------------------
    rect(d, 0, 0, W, 82, fill=NAVY)
    rect(d, 0, 82, W, 86, fill=RED)
    x = 28
    text(d, x, 41, "WORLD NEWS", poppins("Bold", 34), (255, 255, 255), anchor="lm")
    x += d.textlength("WORLD NEWS", font=poppins("Bold", 34)) / S + 12
    text(d, x, 41, "— 18 NOVEMBER 2026", poppins("Medium", 34), GOLD, anchor="lm")
    text(d, 996, 30, "WEDNESDAY", poppins("Bold", 14), (255, 255, 255), anchor="rm")
    text(d, 996, 52, "The day in one page", poppins("Regular", 13), (190, 202, 220), anchor="rm")

    # Lead story -------------------------------------------------------------
    lx, ly, lw = 28, 104, 516
    kicker(d, lx, ly, 1, "LEAD  ·  MIDDLE EAST  ·  IRAN WAR", RED)
    y = para(d, lx, ly + 26, "Iran widens Gulf attacks, targeting US base in Kuwait and Bahrain",
             lora(37), lw, 42, INK, 3)
    y = para(d, lx, y + 8,
             "Iranian drones hit at Ali Al Salem air base, which hosts US forces: Tehran's "
             "first reported attack on Kuwait since September. Bahrain, home of the US 5th "
             "Fleet, intercepts a new wave. Iran calls it retaliation for Tuesday's US strike "
             "on Qeshm Island.",
             poppins("Regular", 15.5), lw, 22, (40, 46, 58), 5)
    rect(d, lx, y + 8, lx + lw, y + 9, fill=RULE)
    sy = y + 14
    text(d, lx, sy, "30+", poppins("Bold", 26), RED)
    text(d, lx + 60, sy + 5,
         "Iranian strikes on Ali Al Salem in this war (AP analysis)",
         poppins("Medium", 13), MUTED)
    lead_bottom = sy + 34

    # Gulf inset -------------------------------------------------------------
    ix, iy, iw, ih = 566, 104, 430, 286
    proj = draw_inset(img, land50, ix, iy, iw, ih, 43.0, 61.0, 32.6)
    d = ImageDraw.Draw(img)
    halo = dict(stroke=2.2, stroke_fill=INSET_LAND)
    text(d, *proj(53.6, 31.4), "IRAN", poppins("Bold", 17), (120, 110, 95), anchor="mm")
    text(d, *proj(46.0, 24.4), "SAUDI ARABIA", poppins("Bold", 12), (140, 130, 115), anchor="mm")
    text(d, *proj(52.2, 27.25), "Gulf", poppins("Italic", 13), (92, 120, 135), anchor="mm")
    text(d, ix + iw - 8, proj(56.0, 25.3)[1], "Strait of Hormuz", poppins("Italic", 11.5),
         (92, 120, 135), anchor="rm", stroke=2, stroke_fill=INSET_WATER)

    kx, ky = proj(47.52, 29.35)
    bx, by = proj(50.55, 26.07)
    qx, qy = proj(55.83, 26.75)
    burst(d, kx, ky, RED)
    burst(d, bx, by, RED)
    burst(d, qx, qy, NAVY)
    text(d, kx + 20, ky - 9, "KUWAIT", poppins("Bold", 14), RED, **halo)
    text(d, kx + 20, ky + 8, "Ali Al Salem air base", poppins("Medium", 12), INK, **halo)
    text(d, bx - 20, by + 4, "BAHRAIN", poppins("Bold", 14), RED, anchor="rm", **halo)
    text(d, bx - 20, by + 21, "US 5th Fleet base", poppins("Medium", 12), INK, anchor="rm", **halo)
    text(d, qx, qy - 30, "Qeshm Island", poppins("Bold", 13), NAVY, anchor="mm",
         stroke=2.2, stroke_fill=INSET_WATER)
    text(d, qx, qy + 26, "US strike, Tue", poppins("Medium", 12), NAVY, anchor="mm",
         stroke=2.2, stroke_fill=INSET_LAND)

    # legend strip inside inset
    gy = iy + ih - 26
    rect(d, ix + 1, gy - 6, ix + iw - 1, iy + ih - 1, fill=(250, 248, 243))
    disc(d, ix + 16, gy + 7, 5, fill=RED)
    text(d, ix + 26, gy + 7, "Iranian attacks, Wed 18 Nov", poppins("Medium", 12), INK, anchor="lm")
    disc(d, ix + 222, gy + 7, 5, fill=NAVY)
    text(d, ix + 232, gy + 7, "US strike, Tue 17 Nov", poppins("Medium", 12), INK, anchor="lm")

    # World map band ---------------------------------------------------------
    top = max(lead_bottom, iy + ih) + 14
    rect(d, 28, top - 1, 996, top, fill=INK)
    mx, my, mw = 28, top + 10, 592
    mproj, mh = draw_dot_map(img, land110, mx, my, mw, 74.0, -56.0)
    d = ImageDraw.Draw(img)
    for label, lon, lat in (("AMERICAS", -98, 14), ("EUROPE", 12, 60), ("AFRICA", 18, 2),
                            ("ASIA", 95, 52), ("OCEANIA", 136, -36)):
        px, py = mproj(lon, lat)
        text(d, px, py, label, poppins("Bold", 11.5), (118, 110, 98), anchor="mm",
             stroke=2, stroke_fill=PAPER)
    for n, lon, lat, color in ((1, 48.5, 28.0, RED), (4, 35.5, 46.5, RED),
                               (6, 31.5, 14.5, PLUM), (5, 90.4, 24.0, AMBER),
                               (2, 114.1, 22.5, TEAL)):
        px, py = mproj(lon, lat)
        disc(d, px, py, 12.5, fill=PAPER)
        badge(d, px, py, n, color, r=10.5)
    text(d, mx, my + mh + 2, "Numbers locate the stories on this page.",
         poppins("Regular", 11.5), MUTED)

    # Voyager panel ----------------------------------------------------------
    vx, vy, vw = 640, top + 12, 356
    kicker(d, vx, vy, 3, "SPACE  ·  SCIENCE", INDIGO)
    y = para(d, vx, vy + 24, "Voyager 1 becomes first craft one light-day from Earth",
             poppins("Bold", 20), vw, 26, INK, 2)
    # distance diagram
    dy = y + 30
    disc(d, vx + 12, dy, 9, fill=(37, 99, 235))
    text(d, vx + 12, dy + 22, "Earth", poppins("Medium", 11.5), MUTED, anchor="mm")
    for i in range(int((vw - 60) / 9)):
        sx = vx + 28 + i * 9
        rect(d, sx, dy - 1, sx + 4.5, dy + 1, fill=INDIGO)
    px = vx + vw - 16
    d.polygon([((px - 9) * S, (dy - 6) * S), ((px + 7) * S, dy * S), ((px - 9) * S, (dy + 6) * S)],
              fill=INDIGO)
    text(d, vx + vw, dy + 22, "Voyager 1", poppins("Medium", 11.5), MUTED, anchor="rm")
    text(d, vx + vw / 2, dy - 18, "signal time: 24 hours  ·  ≈25.9 billion km",
         poppins("Bold", 12.5), INDIGO, anchor="mm")
    para(d, vx, dy + 40,
         "At 10:16 UTC the probe, launched in 1977, became the first human-made object "
         "so far away that its radio signals take a full day to reach us.",
         poppins("Regular", 14), vw, 20, (40, 46, 58), 3)

    # Bottom row: four briefs ------------------------------------------------
    by0 = my + mh + 26
    rect(d, 28, by0 - 1, 996, by0, fill=INK)
    cols = 4
    gap = 18
    cw = (968 - gap * (cols - 1)) / cols
    briefs = [
        (2, "ASIA-PACIFIC · APEC", TEAL,
         "Xi greets Trump on the tarmac as APEC opens in Shenzhen",
         "A break with protocol. Next: the first-ever Trump–Xi–Putin summit, on nuclear "
         "arms and the Iran war. Xi vows to resist trade protectionism."),
        (4, "EUROPE · UKRAINE WAR", RED,
         "Crimea bridge severed after Ukrainian strikes",
         "A Kerch Bridge road span lies in the strait after hits on 16–17 Nov; traffic "
         "halted. Western intelligence: Putin not ready for serious peace talks."),
        (5, "SOUTH ASIA · LABOUR", AMBER,
         "Bangladesh garment workers keep up wage protests",
         "Workers block the Dhaka–Mymensingh highway in Gazipur demanding higher pay. "
         "The minimum-wage board next meets on 23 Nov."),
        (6, "AFRICA · SUDAN WAR", PLUM,
         "UN: drones now cause most civilian deaths in Sudan",
         "The UN rights office has verified 2,230 civilians killed in 2026, more than "
         "1,630 of them by drone strikes."),
    ]
    bottoms = []
    for i, (n, label, color, head, deck) in enumerate(briefs):
        cx = 28 + i * (cw + gap)
        rect(d, cx, by0 + 10, cx + cw, by0 + 14, fill=color)
        kicker(d, cx, by0 + 24, n, label, color)
        y = para(d, cx, by0 + 48, head, poppins("Bold", 19), cw, 24, INK, 3)
        y = para(d, cx, y + 6, deck, poppins("Regular", 14.5), cw, 20.5, (40, 46, 58), 6)
        if n == 6:   # share-of-deaths bar: 1,630 of 2,230
            share = 1630 / 2230
            y += 8
            rect(d, cx, y, cx + cw, y + 12, fill=(229, 220, 232))
            rect(d, cx, y, cx + cw * share, y + 12, fill=PLUM)
            text(d, cx, y + 26, "drone strikes ≈ 73% of verified deaths",
                 poppins("Medium", 11.5), PLUM, anchor="lm")
            y += 34
        bottoms.append(y)
        if i:
            rect(d, cx - gap / 2, by0 + 10, cx - gap / 2 + 0.6, max(bottoms) + 4, fill=RULE)

    # Footer -----------------------------------------------------------------
    fy = 974
    if max(bottoms) > fy - 8:
        raise SystemExit(f"briefs overflow into footer: {max(bottoms):.0f}")
    rect(d, 28, fy, 996, fy + 1, fill=INK)
    text(d, 28, fy + 12, "A global snapshot • 18 Nov 2026", poppins("Bold", 12.5), INK)
    text(d, 996, fy + 12, "Illustration & map: original, Natural Earth data",
         poppins("Regular", 11.5), MUTED, anchor="ra")
    text(d, 28, fy + 31,
         "Sources: AP, Reuters, AFP, CNN, NBC News, Al Jazeera, NASA/JPL, UN OHCHR, "
         "Just Security, Morning Star",
         poppins("Regular", 11.5), MUTED)

    return img.resize((W, H), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--land110", required=True)
    ap.add_argument("--land50", required=True)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    img = render(rings(a.land110), rings(a.land50))
    img.save(a.out, "PNG", optimize=True)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
