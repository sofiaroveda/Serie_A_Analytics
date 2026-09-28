"""Draw the link-preview image and the browser-tab icons (run once, or after renaming the site).

    python tools/make_share_image.py

Writes site/img/share.png (1200 x 630, the size WhatsApp / LinkedIn / X expect),
site/img/apple-touch-icon.png (180 x 180) and site/img/favicon.png (64 x 64).
Uses Avenir Next Condensed, which ships with macOS; the images are committed, so the
daily update never needs to run this.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SITE_NAME = "SERIE A ANALYTICS"
TAGLINE = "Predictions for every Serie A match,\ntested honestly against the betting market"
FEATURES = "Title race  ·  What if? simulator  ·  Updated daily"

OUT = Path(__file__).resolve().parent.parent / "site" / "img"
FONT = "/System/Library/Fonts/Avenir Next Condensed.ttc"
BOLD, DEMI, REGULAR = 0, 2, 7  # font indexes inside the .ttc collection (checked with ImageFont.truetype(...).getname())

PITCH = (12, 18, 16)  # --pitch
WHITE = (255, 255, 255)
MUTED = (159, 179, 168)  # --on-pitch-muted
NEON = (61, 220, 132)  # --neon
LINES = (255, 255, 255, 38)  # faint chalk
FLAG = [(0, 146, 70), (255, 255, 255), (206, 43, 55)]


def font(index: int, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size, index=index)


def draw_ball(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float) -> None:
    """The site's logo: a white ball with a dark pentagon and seams."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
    s = r / 15  # the logo is drawn on a 32-unit grid with radius 15
    pentagon = [(0, -6), (5.7, -1.9), (3.5, 4.9), (-3.5, 4.9), (-5.7, -1.9)]
    draw.polygon([(cx + x * s, cy + y * s) for x, y in pentagon], fill=PITCH)
    seams = [((0, -6), (0, -13.5)), ((5.7, -1.9), (12.7, -4.2)), ((3.5, 4.9), (7.8, 10.9)),
             ((-3.5, 4.9), (-7.8, 10.9)), ((-5.7, -1.9), (-12.7, -4.2))]  # fmt: skip
    for (x1, y1), (x2, y2) in seams:
        draw.line([(cx + x1 * s, cy + y1 * s), (cx + x2 * s, cy + y2 * s)], fill=PITCH, width=max(2, int(1.6 * s)))


def draw_pitch(layer: Image.Image, box: tuple[int, int, int, int]) -> None:
    """A whole pitch in faint chalk lines inside `box` (the same drawing as the site's header)."""
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = box
    sx, sy = (x1 - x0) / 200, (y1 - y0) / 130

    def p(x, y):
        return (x0 + x * sx, y0 + y * sy)

    w = 3
    d.rectangle([p(1, 1), p(199, 129)], outline=LINES, width=w)
    d.line([p(100, 1), p(100, 129)], fill=LINES, width=w)
    d.ellipse([p(80, 45), p(120, 85)], outline=LINES, width=w)
    for left in (True, False):
        bx = 1 if left else 167
        d.rectangle([p(bx, 31), p(bx + 32, 99)], outline=LINES, width=w)
        sb = 1 if left else 188
        d.rectangle([p(sb, 49), p(sb + 11, 81)], outline=LINES, width=w)


def share_image() -> Image.Image:
    img = Image.new("RGB", (1200, 630), PITCH)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_pitch(overlay, (640, 120, 1160, 458))
    img.paste(overlay, (0, 0), overlay)
    d = ImageDraw.Draw(img)

    for i, colour in enumerate(FLAG):  # Italian flag stripe along the top
        d.rectangle([i * 400, 0, (i + 1) * 400, 14], fill=colour)

    draw_ball(d, 110, 150, 46)
    d.text((180, 150), SITE_NAME, font=font(BOLD, 64), fill=WHITE, anchor="lm")
    d.multiline_text((72, 250), TAGLINE, font=font(DEMI, 50), fill=WHITE, spacing=14)
    d.rectangle([72, 420, 150, 426], fill=NEON)
    d.text((72, 460), FEATURES, font=font(REGULAR, 34), fill=MUTED)
    d.text((72, 560), "sofiaroveda.github.io/Serie_A_Analytics", font=font(REGULAR, 28), fill=MUTED)
    return img


def icon(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), PITCH)
    draw_ball(ImageDraw.Draw(img), size / 2, size / 2, size * 0.38)
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    share_image().save(OUT / "share.png", optimize=True)
    icon(180).save(OUT / "apple-touch-icon.png", optimize=True)
    icon(64).save(OUT / "favicon.png", optimize=True)
    print(f"Wrote share.png, apple-touch-icon.png and favicon.png to {OUT}")
