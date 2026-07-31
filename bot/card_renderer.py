"""
Renders a branded MI NEXUS signal card (PNG) from the parsed Gemini result,
styled like the reference sample: black background, green neon accents,
UP/DOWN badge, confidence bar.
"""
import os
from PIL import Image, ImageDraw, ImageFont
from bot.config import BRAND_NAME, BRAND_TAGLINE, BRAND_FOOTER, DISCLAIMER_TEXT

WIDTH, HEIGHT = 940, 1180

GREEN = (57, 255, 20)
GREEN_DIM = (30, 140, 20)
RED = (255, 60, 60)
WHITE = (235, 235, 235)
GRAY = (150, 150, 150)
BLACK = (8, 10, 8)
PANEL_BG = (14, 18, 14)

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
FONT_REGULAR = os.path.join(FONT_DIR, "DejaVuSans.ttf")


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _rounded_panel(draw, box, radius, outline, width=2, fill=PANEL_BG):
    draw.rounded_rectangle(box, radius=radius, outline=outline, width=width, fill=fill)


def render_signal_card(result: dict, out_path: str):
    """
    result: dict from gemini_analyzer.analyze_chart()
    Writes a PNG to out_path.
    """
    img = Image.new("RGB", (WIDTH, HEIGHT), BLACK)
    draw = ImageDraw.Draw(img)

    f_brand = _font(FONT_BOLD, 54)
    f_tagline = _font(FONT_REGULAR, 20)
    f_h1 = _font(FONT_BOLD, 30)
    f_body = _font(FONT_REGULAR, 24)
    f_body_bold = _font(FONT_BOLD, 24)
    f_big = _font(FONT_BOLD, 46)
    f_pct = _font(FONT_BOLD, 40)
    f_small = _font(FONT_REGULAR, 18)

    y = 40
    draw.text((WIDTH / 2, y), BRAND_NAME, font=f_brand, fill=WHITE, anchor="ma")
    y += 70
    draw.text((WIDTH / 2, y), BRAND_TAGLINE, font=f_tagline, fill=GREEN, anchor="ma")
    y += 50

    direction = result.get("direction", "UP")
    is_up = direction == "UP"
    dcolor = GREEN if is_up else RED
    darrow = "▲" if is_up else "▼"

    badge_w, badge_h = 220, 56
    badge_box = (WIDTH - badge_w - 40, y, WIDTH - 40, y + badge_h)
    _rounded_panel(draw, badge_box, 14, dcolor, width=3, fill=BLACK)
    draw.text(
        ((badge_box[0] + badge_box[2]) / 2, (badge_box[1] + badge_box[3]) / 2),
        f"{darrow} {direction}", font=f_h1, fill=dcolor, anchor="mm"
    )

    y += badge_h + 30
    panel_top = y
    panel_bottom = y + 560
    _rounded_panel(draw, (40, panel_top, WIDTH - 40, panel_bottom), 24, GREEN, width=3)

    inner_y = panel_top + 30
    draw.text((70, inner_y), f"🪙 {result.get('asset', 'N/A')}", font=f_body, fill=WHITE)
    inner_y += 40
    draw.text((70, inner_y), f"⏱️ Timeframe: {result.get('timeframe', 'N/A')}", font=f_body, fill=WHITE)
    inner_y += 40
    draw.text((70, inner_y), f"📈 Trend: {result.get('trend', 'N/A')}", font=f_body, fill=GREEN)
    inner_y += 60

    draw.line((70, inner_y, WIDTH - 70, inner_y), fill=GREEN_DIM, width=2)
    inner_y += 40

    draw.text((WIDTH / 2, inner_y), "NEXT CANDLE:", font=f_body, fill=WHITE, anchor="ma")
    inner_y += 40
    draw.text((WIDTH / 2, inner_y), direction, font=f_big, fill=dcolor, anchor="ma")
    inner_y += 80

    # Confidence bar
    conf = result.get("confidence", 50)
    bar_x0, bar_x1 = 90, WIDTH - 260
    bar_y = inner_y
    bar_h = 26
    draw.rounded_rectangle((bar_x0, bar_y, bar_x1, bar_y + bar_h), radius=13, fill=(40, 40, 40))
    fill_x1 = bar_x0 + int((bar_x1 - bar_x0) * (conf / 100))
    draw.rounded_rectangle((bar_x0, bar_y, fill_x1, bar_y + bar_h), radius=13, fill=dcolor)
    draw.text((WIDTH - 220, bar_y + bar_h / 2), f"{conf}%", font=f_pct, fill=GREEN, anchor="lm")
    inner_y += bar_h + 15
    draw.text((WIDTH / 2, inner_y), "CONFIDENCE", font=f_small, fill=GRAY, anchor="ma")
    inner_y += 45

    draw.text((70, inner_y), f"⏳ Expiry: {result.get('expiry', 'N/A')}", font=f_body, fill=WHITE)

    # Bottom info panel
    y2 = panel_bottom + 30
    _rounded_panel(draw, (40, y2, WIDTH - 40, HEIGHT - 90), 24, GREEN, width=3)
    ty = y2 + 30
    draw.text((70, ty), "💡 TIP:", font=f_body_bold, fill=GREEN)
    ty += 36
    tip = "Wait for confirmation candle before entering a trade."
    draw.text((70, ty), tip, font=f_body, fill=WHITE)
    ty += 60
    warn = "⚠️ " + DISCLAIMER_TEXT
    draw.text((WIDTH / 2, HEIGHT - 130), warn, font=f_small, fill=GRAY, anchor="ma")
    draw.text((WIDTH / 2, HEIGHT - 100), BRAND_FOOTER, font=f_small, fill=GREEN_DIM, anchor="ma")

    img.save(out_path, "PNG")
    return out_path
