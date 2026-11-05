"""Kitna logo kit: SVG masters (text outlined, so it looks the same everywhere) + PNG exports + social images."""
import os
import zipfile

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

OUT = "/home/claude/kitna-kit/Kitna-logo-kit"
INK, INDIGO, MARIGOLD, CREAM, WHITE, LILAC = "#1c1b22", "#34378a", "#f2a93b", "#f6f4ef", "#ffffff", "#d9daf2"
TAGLINE = "Pehle Kitna, phir kharcha."
FONTS = {"semibold": "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf",
         "bold": "/usr/share/fonts/opentype/inter/Inter-Bold.otf"}
_fonts = {}


def text_path(text, weight="semibold", size=32, tracking=-0.01):
    """Outline text with Inter: returns (path d, width, cap height) with the baseline at y=0."""
    f = _fonts.setdefault(weight, TTFont(FONTS[weight]))
    gs, cmap, hmtx = f.getGlyphSet(), f.getBestCmap(), f["hmtx"]
    upm = f["head"].unitsPerEm
    s = size / upm
    pen = SVGPathPen(gs)
    x = 0.0
    for ch in text:
        g = cmap.get(ord(ch))
        if g is None:
            continue
        gs[g].draw(TransformPen(pen, (s, 0, 0, -s, x, 0)))
        x += hmtx[g][0] * s + tracking * size
    cap = f["OS/2"].sCapHeight * s
    return pen.getCommands(), x - tracking * size, cap


# Wordmark drawn by hand on a 264-wide grid; bounds of the ink: x 4..260, y 14..106.
WM_W, WM_H, WM_X, WM_Y = 256, 92, 4, 14


def wordmark(ink, dot=MARIGOLD):
    return (f'<g fill="none" stroke="{ink}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M10 20V100M10 74L46 50M26 63L48 100"/><path d="M70 50V100"/>'
            '<path d="M102 28V86Q102 100 116 100M92 54H118"/>'
            '<path d="M142 100V50M142 72A20 20 0 0 1 182 72V100"/><circle cx="229" cy="75" r="25"/><path d="M254 50V100"/></g>'
            f'<circle cx="70" cy="28" r="9" fill="{dot}"/>')


def icon(bg=INDIGO, fg=WHITE, dot=MARIGOLD, radius=15):
    return (f'<rect width="64" height="64" rx="{radius}" fill="{bg}"/>'
            f'<g fill="none" stroke="{fg}" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M22 13V51M22 38L39 26.5M29.5 33L40 51"/></g>'
            f'<circle cx="45" cy="15" r="5" fill="{dot}"/>')


def svg(w, h, body, bg=None):
    back = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.2f} {h:.2f}" width="{w:.0f}" height="{h:.0f}">'
            f'<title>Kitna</title>{back}{body}</svg>')


def place_wm(x, y, height, ink, dot=MARIGOLD):
    k = height / WM_H
    return f'<g transform="translate({x - WM_X * k:.2f} {y - WM_Y * k:.2f}) scale({k:.4f})">{wordmark(ink, dot)}</g>'


def place_icon(x, y, size, **kw):
    return f'<g transform="translate({x:.2f} {y:.2f}) scale({size / 64:.4f})">{icon(**kw)}</g>'


def place_text(x, baseline, text, color, size, weight="semibold", anchor="start", tracking=-0.01):
    d, w, _ = text_path(text, weight, size, tracking)
    if anchor == "middle":
        x -= w / 2
    return f'<path transform="translate({x:.2f} {baseline:.2f})" d="{d}" fill="{color}"/>', w


# ─── Logo layouts (transparent, cropped to the ink with a little air) ──
# The wordmark IS the logo; the "k" icon is only for square spaces (app icon, profile pictures).
def logo(ink, dot=MARIGOLD, tag=None, tag_color=None, align="start"):
    pad, h = 10, WM_H
    body = place_wm(pad, pad, h, ink, dot)
    w, total = pad * 2 + WM_W, pad * 2 + h
    if tag:
        size = 40
        _, tw, _ = text_path(tag, "semibold", size)
        size *= WM_W / tw  # the tagline exactly as wide as the name
        t, _ = place_text(pad, pad + h + 10 + size * 0.76, tag, tag_color, size)
        body += t
        total = pad + h + 10 + size * 1.02 + pad
    return svg(w, total, body)


def wm_with_tag(cx, top, height, ink, tag_color, sub=None, sub_color=None, anchor="middle"):
    """Wordmark + tagline sized to its width, for social images. Returns (svg body, bottom y)."""
    width = WM_W * height / WM_H
    x = cx - width / 2 if anchor == "middle" else cx
    body = place_wm(x, top, height, ink)
    size = 40
    _, tw, _ = text_path(TAGLINE, "bold", size, -0.015)
    size *= width / tw
    y = top + height + size * 1.25
    t, _ = place_text(x, y, TAGLINE, tag_color, size, "bold", tracking=-0.015)
    body += t
    if sub:
        sz = size * 0.62
        y += sz * 1.9
        u, _ = place_text(x + width / 2 if anchor == "middle" else x, y, sub, sub_color, sz, "semibold",
                          "middle" if anchor == "middle" else "start")
        body += u
    return body, y


# ─── Social images ────────────────────────────────────────────
def social(w, h, layout):
    if layout == "avatar":
        return svg(w, h, place_icon(0, 0, w, radius=0))
    if layout in ("square", "story"):
        body, bottom = wm_with_tag(w / 2, 0, w * 0.27, WHITE, MARIGOLD, "Know before you spend.", LILAC)
        dy = (h - bottom) / 2 - w * 0.012
        return svg(w, h, f'<g transform="translate(0 {dy:.1f})">{body}</g>', INDIGO)
    if w / h > 3.2:  # very wide banners: name left, tagline right
        height = h * 0.30
        x0 = w * 0.27  # the profile picture covers the left of LinkedIn and X banners
        body = place_wm(x0, h / 2 - height / 2, height, WHITE)
        size = height * 0.40
        _, tw, _ = text_path(TAGLINE, "bold", size, -0.015)
        t, _ = place_text(w * 0.93 - tw, h / 2 + size * 0.36, TAGLINE, MARIGOLD, size, "bold", tracking=-0.015)
        return svg(w, h, body + t, INDIGO)
    if w / h >= 2.5:  # X header: profile picture sits bottom-left, so centre the logo a little right
        body, bottom = wm_with_tag(w * 0.6, 0, h * 0.34, WHITE, MARIGOLD, "Know before you spend.", LILAC)
        dy = (h - bottom) / 2 - h * 0.01
        return svg(w, h, f'<g transform="translate(0 {dy:.1f})">{body}</g>', INDIGO)
    body, bottom = wm_with_tag(w * 0.09, 0, h * 0.34, WHITE, MARIGOLD, "Know before you spend.", LILAC, anchor="start")
    dy = (h - bottom) / 2 - h * 0.01
    return svg(w, h, f'<g transform="translate(0 {dy:.1f})">{body}</g>', INDIGO)


FILES = {
    "logo/kitna-logo.svg": logo(INK),
    "logo/kitna-logo-white.svg": logo(WHITE),
    "logo/kitna-logo-indigo.svg": logo(INDIGO),
    "logo/kitna-logo-black.svg": logo(INK, INK),
    "logo/kitna-logo-tagline.svg": logo(INK, tag=TAGLINE, tag_color=INDIGO),
    "logo/kitna-logo-tagline-white.svg": logo(WHITE, tag=TAGLINE, tag_color=MARIGOLD),
    "logo/kitna-icon.svg": svg(64, 64, icon()),
    "social/profile-picture-1080.svg": social(1080, 1080, "avatar"),
    "social/instagram-post-1080x1080.svg": social(1080, 1080, "square"),
    "social/instagram-story-1080x1920.svg": social(1080, 1920, "story"),
    "social/link-preview-1200x630.svg": social(1200, 630, "wide"),
    "social/x-header-1500x500.svg": social(1500, 500, "wide"),
    "social/linkedin-banner-1584x396.svg": social(1584, 396, "wide"),
}

README = f"""KITNA LOGO KIT
Pehle Kitna, phir kharcha.  ·  Know before you spend.

FILES
  logo/     SVG masters (any size, text already outlined) + PNG at large size, transparent.
            kitna-logo            the main logo, for light backgrounds
            kitna-logo-white      for indigo, dark or photo backgrounds
            kitna-logo-indigo     brand-colour version for light backgrounds
            kitna-logo-black      one colour (stamps, single-colour print)
            kitna-logo-tagline    with "Pehle Kitna, phir kharcha." underneath (-white for dark)
            kitna-icon            the "k" icon: ONLY for square spaces (app icon, favicon, profile pictures).
                                  Never put it next to the name: the name already starts with k.
  social/   ready to post: profile picture, Instagram post and story, link preview
            (WhatsApp, LinkedIn, X), X header, LinkedIn banner.

COLOURS
  Ink indigo   #34378A   main brand colour, backgrounds, buttons
  Marigold     #F2A93B   the coin dot and highlights only; never for long text
  Ink          #1C1B22   text and the logo on light backgrounds
  Cream        #F6F4EF   page background
  Lilac        #D9DAF2   secondary text on indigo

TYPE   Inter (free, Google Fonts). Headlines Bold/ExtraBold, body Regular.

RULES
  - Keep clear space around the logo at least the height of the coin dot x 2.
  - Don't stretch, rotate, outline or add shadows. Don't recolour the coin except in the one-colour version.
  - Smallest size: wordmark 64 px wide on screen (12 mm in print); below that use the icon.
  - On photos, use the white logo on a dark, calm area, or the icon.
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, content in FILES.items():
        path = os.path.join(OUT, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
    with open(os.path.join(OUT, "README.txt"), "w") as f:
        f.write(README)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, content in FILES.items():
            import re

            w, h = (float(v) for v in re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', content).groups())
            scale = 1 if name.startswith("social/") else (2048 / 64 if "icon" in name else 3000 / w)
            pw, ph = round(w * scale), round(h * scale)
            pg = b.new_page(viewport={"width": pw, "height": ph})
            pg.set_content(f'<html><body style="margin:0;background:transparent">'
                           f'{content.replace("<svg ", f"<svg style=\'display:block;width:{pw}px;height:{ph}px\' ", 1)}</body></html>')
            pg.screenshot(path=os.path.join(OUT, name.replace(".svg", ".png")), omit_background=True)
            pg.close()
        b.close()
    zp = "/home/claude/kitna-kit/Kitna-logo-kit.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(OUT):
            for fn in sorted(files):
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, os.path.dirname(OUT)))
    print("ok", zp)


if __name__ == "__main__":
    main()
