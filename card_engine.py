"""
=============================================================================
MI NEXUS AI - PREMIUM CARD ENGINE
=============================================================================
Generates the beautiful dark-themed "MI NEXUS" signal / result cards used
for broadcasting inside groups & channels, matching the premium sample
design (logo header, chart image, confidence bar, sentiment, footer).
=============================================================================
"""

import io
import os
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE_DIR, "fonts")
ASSET_DIR = os.path.join(BASE_DIR, "assets")

FONT_BOLD_PATH = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
FONT_REG_PATH = os.path.join(FONT_DIR, "DejaVuSans.ttf")

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
BG_COLOR = (5, 12, 10)
PANEL_BORDER_GREEN = (40, 230, 130)
PANEL_BORDER_RED = (230, 60, 60)
GREEN = (40, 230, 130)
RED = (235, 70, 70)
WHITE = (240, 245, 242)
GREY = (150, 165, 160)
CARD_BG = (8, 18, 15)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _rounded_rect(draw: ImageDraw.ImageDraw, box, radius, outline=None, width=3, fill=None):
    draw.rounded_rectangle(box, radius=radius, outline=outline, width=width, fill=fill)


def _text_w(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _center_text(draw, cx, y, text, font, fill):
    w = _text_w(draw, text, font)
    draw.text((cx - w / 2, y), text, font=font, fill=fill)


def _glow_line(draw, xy, color, width=2, blur_img=None):
    draw.line(xy, fill=color, width=width)


def _load_asset(name: str) -> Optional[Image.Image]:
    path = os.path.join(ASSET_DIR, name)
    if os.path.exists(path):
        return Image.open(path).convert("RGBA")
    return None


def build_signal_card(
    chart_image_bytes: bytes,
    asset_name: str,
    direction: str,          # "UP" or "DOWN"
    confidence: int,         # 0-100
    timeframe: str,
    trend_bias: str,
    market_condition: str,
    sentiment: str,          # "BULLISH" or "BEARISH"
    patterns: list,          # list of (name, reliability_pct)
    tip: str,
    session_label: str = "TRADING SESSION",
) -> io.BytesIO:
    """Builds the full premium MI NEXUS analysis card."""

    is_up = direction.upper() == "UP"
    accent = GREEN if is_up else RED
    border_color = PANEL_BORDER_GREEN if is_up else PANEL_BORDER_RED

    W = 960
    H = 1360
    card = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(card)

    pad = 36

    # ---------------- Header: logo + title ----------------
    logo = _load_asset("logo_round.png")
    logo_size = 110
    if logo:
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
        card.paste(logo, (W // 2 - logo_size // 2, 18), logo)
    y = 18 + logo_size + 10

    f_title = _font(FONT_BOLD_PATH, 50)
    f_sub = _font(FONT_REG_PATH, 20)
    f_pill = _font(FONT_BOLD_PATH, 20)

    _center_text(draw, W / 2, y, "MI NEXUS", f_title, WHITE)
    y += 60
    _center_text(draw, W / 2, y, "A N A L Y Z E   \u2022   P R E D I C T   \u2022   P R O F I T", f_sub, GREY)
    y += 36

    # pill: session label
    pill_text = f"\u2605 {session_label} \u2605"
    pw = _text_w(draw, pill_text, f_pill) + 50
    ph = 42
    px = W / 2 - pw / 2
    _rounded_rect(draw, [px, y, px + pw, y + ph], radius=ph / 2, outline=accent, width=3)
    _center_text(draw, W / 2, y + 8, pill_text, f_pill, accent)
    y += ph + 22

    # ---------------- Chart panel ----------------
    panel_top = y
    panel_h = 560
    _rounded_rect(draw, [pad, panel_top, W - pad, panel_top + panel_h], radius=26, outline=accent, width=4, fill=CARD_BG)

    # status pill (STRONG) top-left, direction pill top-right
    f_small_bold = _font(FONT_BOLD_PATH, 24)
    status_text = "\u25CF STRONG" if confidence >= 70 else ("\u25CF MODERATE" if confidence >= 50 else "\u25CF WEAK")
    sw = _text_w(draw, status_text, f_small_bold) + 34
    sx, sy = pad + 22, panel_top + 20
    _rounded_rect(draw, [sx, sy, sx + sw, sy + 44], radius=22, outline=GREEN, width=2)
    draw.text((sx + 17, sy + 9), status_text, font=f_small_bold, fill=GREEN)

    dir_text = ("\u25B2 UP" if is_up else "\u25BC DOWN")
    dw = _text_w(draw, dir_text, f_small_bold) + 34
    dx = W - pad - 22 - dw
    _rounded_rect(draw, [dx, sy, dx + dw, sy + 44], radius=22, outline=accent, width=2, fill=(accent[0]//5, accent[1]//5, accent[2]//5))
    draw.text((dx + 17, sy + 9), dir_text, font=f_small_bold, fill=accent)

    # chart image itself
    chart_top = sy + 60
    chart_h = panel_h - (chart_top - panel_top) - 30
    chart_w = W - 2 * pad - 44
    try:
        chart_img = Image.open(io.BytesIO(chart_image_bytes)).convert("RGB")
        chart_img = ImageOps.fit(chart_img, (int(chart_w), int(chart_h)), method=Image.LANCZOS)
    except Exception:
        chart_img = Image.new("RGB", (int(chart_w), int(chart_h)), (12, 22, 18))
    cx0 = pad + 22
    cy0 = chart_top
    card.paste(chart_img, (int(cx0), int(cy0)))
    _rounded_rect(draw, [cx0, cy0, cx0 + chart_w, cy0 + chart_h], radius=10, outline=(30, 45, 40), width=2)

    y = panel_top + panel_h + 30

    # ---------------- NEXT CANDLE + confidence bar ----------------
    f_next = _font(FONT_BOLD_PATH, 42)
    next_label = "NEXT CANDLE: "
    dir_word = "UP" if is_up else "DOWN"
    lw = _text_w(draw, next_label, f_next)
    dwid = _text_w(draw, dir_word, f_next)
    total_w = lw + dwid
    start_x = W / 2 - total_w / 2
    draw.text((start_x, y), next_label, font=f_next, fill=WHITE)
    draw.text((start_x + lw, y), dir_word, font=f_next, fill=accent)
    y += 66

    # confidence bar
    bar_x0 = pad + 10
    bar_x1 = W - pad - 130
    bar_y0 = y
    bar_h = 22
    _rounded_rect(draw, [bar_x0, bar_y0, bar_x1, bar_y0 + bar_h], radius=bar_h / 2, outline=(50, 60, 55), width=2, fill=(20, 28, 25))
    fill_w = (bar_x1 - bar_x0 - 4) * (confidence / 100)
    if fill_w > 6:
        _rounded_rect(draw, [bar_x0 + 2, bar_y0 + 2, bar_x0 + 2 + fill_w, bar_y0 + bar_h - 2], radius=(bar_h - 4) / 2, outline=None, width=0, fill=accent)
    f_conf = _font(FONT_BOLD_PATH, 34)
    draw.text((bar_x1 + 15, bar_y0 - 8), f"{confidence}%", font=f_conf, fill=GREEN)
    y += bar_h + 12
    f_conf_lbl = _font(FONT_REG_PATH, 20)
    _center_text(draw, (bar_x0 + bar_x1) / 2, y, "CONFIDENCE", f_conf_lbl, GREY)
    y += 44

    # ---------------- Info panel (two columns) ----------------
    info_top = y
    info_h = 360
    _rounded_rect(draw, [pad, info_top, W - pad, info_top + info_h], radius=22, outline=(40, 60, 55), width=2, fill=CARD_BG)

    left_x = pad + 26
    col_split = W * 0.56
    left_col_right_edge = col_split - 30
    right_x = col_split + 20
    right_w = (W - pad) - right_x - 20

    f_lbl = _font(FONT_REG_PATH, 21)
    f_val = _font(FONT_BOLD_PATH, 21)

    rows = [
        ("\u23F0  Timeframe", timeframe),
        ("\U0001F4C8  Trend Bias", trend_bias),
        ("\U0001F4CA  Condition", market_condition),
    ]
    ry = info_top + 26
    for label, val in rows:
        draw.text((left_x, ry), label, font=f_lbl, fill=WHITE)
        ry += 30
        draw.text((left_x + 10, ry), val, font=f_val, fill=GREEN)
        ry += 40

    ry += 8
    draw.text((left_x, ry), "\U0001F50D  Patterns Detected", font=f_lbl, fill=WHITE)
    ry += 34
    f_pat = _font(FONT_BOLD_PATH, 19)
    f_pat_pct = _font(FONT_REG_PATH, 17)
    for pname, rel in patterns[:3]:
        arrow = "\u25BC" if not is_up else "\u25B2"
        line_txt = f"{arrow} {pname}"
        # wrap long pattern names to fit left column width
        max_w = left_col_right_edge - left_x
        while _text_w(draw, line_txt, f_pat) > max_w and len(line_txt) > 10:
            line_txt = line_txt[:-4] + "\u2026"
        draw.text((left_x, ry), line_txt, font=f_pat, fill=accent)
        ry += 26
        pct_txt = f"{rel}% reliability"
        draw.text((left_x + 16, ry), pct_txt, font=f_pat_pct, fill=GREY)
        ry += 30

    # Right column: Market Sentiment box + Volatility box
    box_h = 155
    sent_box = [right_x, info_top + 22, right_x + right_w, info_top + 22 + box_h]
    _rounded_rect(draw, sent_box, radius=16, outline=accent, width=2)
    f_box_title = _font(FONT_BOLD_PATH, 20)
    _center_text(draw, (sent_box[0] + sent_box[2]) / 2, sent_box[1] + 14, "MARKET SENTIMENT", f_box_title, accent)
    f_sent = _font(FONT_BOLD_PATH, 26)
    _center_text(draw, (sent_box[0] + sent_box[2]) / 2, sent_box[1] + 80, sentiment.upper(), f_sent, accent)
    # dots
    dot_y = sent_box[1] + 118
    dot_count = 6
    filled = 4 if confidence >= 70 else 3
    dot_r = 6
    total_dots_w = dot_count * (dot_r * 2 + 8) - 8
    dot_start = (sent_box[0] + sent_box[2]) / 2 - total_dots_w / 2
    for i in range(dot_count):
        dx0 = dot_start + i * (dot_r * 2 + 8)
        col = accent if i < filled else (60, 70, 65)
        draw.ellipse([dx0, dot_y, dx0 + dot_r * 2, dot_y + dot_r * 2], fill=col)

    vol_box = [right_x, info_top + 22 + box_h + 20, right_x + right_w, info_top + 22 + box_h + 20 + box_h]
    _rounded_rect(draw, vol_box, radius=16, outline=GREEN, width=2)
    _center_text(draw, (vol_box[0] + vol_box[2]) / 2, vol_box[1] + 14, "VOLATILITY", f_box_title, GREEN)
    # simple sine squiggle
    import math
    mid_y = vol_box[1] + 55
    pts = []
    seg_w = right_w - 30
    seg_x0 = vol_box[0] + 15
    for i in range(0, int(seg_w), 4):
        yy = mid_y + 14 * math.sin(i / 10)
        pts.append((seg_x0 + i, yy))
    if len(pts) > 1:
        draw.line(pts, fill=GREEN, width=3)
    vol_label = "MEDIUM" if confidence < 80 else "HIGH"
    f_vol = _font(FONT_BOLD_PATH, 22)
    _center_text(draw, (vol_box[0] + vol_box[2]) / 2, vol_box[1] + 90, vol_label, f_vol, WHITE)

    y = info_top + info_h + 24

    # ---------------- Tip bar ----------------
    tip_h = 60
    _rounded_rect(draw, [pad, y, W - pad, y + tip_h], radius=16, outline=GREEN, width=2, fill=CARD_BG)
    f_tip = _font(FONT_REG_PATH, 21)
    draw.text((pad + 20, y + 18), f"\U0001F4A1 TIP: {tip}", font=f_tip, fill=WHITE)
    y += tip_h + 22

    # ---------------- Footer ----------------
    f_foot = _font(FONT_REG_PATH, 18)
    _center_text(draw, W / 2, y, "Educational analysis only \u2014 not financial advice", f_foot, GREY)
    y += 26
    f_foot_b = _font(FONT_BOLD_PATH, 20)
    _center_text(draw, W / 2, y, "MI NEXUS AI \u00A9 Trading Noah", f_foot_b, GREEN)

    buf = io.BytesIO()
    card.save(buf, format="JPEG", quality=93)
    buf.seek(0)
    return buf


def build_result_card(is_win: bool, win_count: int, loss_count: int, asset_hint: str = "") -> io.BytesIO:
    """Builds a beautiful WIN or LOSS summary card with vote totals."""
    accent = GREEN if is_win else RED
    W, H = 900, 700
    card = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(card)

    _rounded_rect(draw, [24, 24, W - 24, H - 24], radius=34, outline=accent, width=6, fill=CARD_BG)

    logo = _load_asset("logo_round.png")
    if logo:
        logo = logo.resize((110, 110), Image.LANCZOS)
        card.paste(logo, (W // 2 - 55, 50), logo)

    f_title = _font(FONT_BOLD_PATH, 90)
    title = "WIN \u2705" if is_win else "LOSS \u274C"
    _center_text(draw, W / 2, 190, title, f_title, accent)

    f_sub = _font(FONT_REG_PATH, 26)
    _center_text(draw, W / 2, 300, "SESSION RESULT — MI NEXUS AI", f_sub, GREY)

    total = max(1, win_count + loss_count)
    win_pct = round(100 * win_count / total)
    loss_pct = 100 - win_pct

    # vote bars
    bar_y = 380
    bar_x0, bar_x1 = 100, W - 100
    label_font = _font(FONT_BOLD_PATH, 26)

    draw.text((bar_x0, bar_y - 34), f"\u2705 WIN VOTES: {win_count} ({win_pct}%)", font=label_font, fill=GREEN)
    _rounded_rect(draw, [bar_x0, bar_y, bar_x1, bar_y + 26], radius=13, outline=(50, 60, 55), width=2, fill=(18, 26, 22))
    fw = (bar_x1 - bar_x0 - 4) * (win_pct / 100)
    if fw > 4:
        _rounded_rect(draw, [bar_x0 + 2, bar_y + 2, bar_x0 + 2 + fw, bar_y + 24], radius=11, fill=GREEN)

    bar_y2 = bar_y + 80
    draw.text((bar_x0, bar_y2 - 34), f"\u274C LOSS VOTES: {loss_count} ({loss_pct}%)", font=label_font, fill=RED)
    _rounded_rect(draw, [bar_x0, bar_y2, bar_x1, bar_y2 + 26], radius=13, outline=(50, 60, 55), width=2, fill=(18, 26, 22))
    fl = (bar_x1 - bar_x0 - 4) * (loss_pct / 100)
    if fl > 4:
        _rounded_rect(draw, [bar_x0 + 2, bar_y2 + 2, bar_x0 + 2 + fl, bar_y2 + 24], radius=11, fill=RED)

    f_foot = _font(FONT_REG_PATH, 20)
    _center_text(draw, W / 2, H - 70, "Community-verified result \u2022 MI NEXUS AI \u00A9 Trading Noah", f_foot, GREY)

    buf = io.BytesIO()
    card.save(buf, format="JPEG", quality=93)
    buf.seek(0)
    return buf
