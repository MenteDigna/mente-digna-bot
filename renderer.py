
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/montserrat/Montserrat-ExtraBold.ttf",
    "/usr/share/fonts/truetype/montserrat/Montserrat-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

def find_font():
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return p
    raise FileNotFoundError("Nenhuma fonte compatível encontrada.")

def fit_text(draw, text, max_width, max_height, font_path, start_size=78, min_size=32):
    text = text.strip()
    for size in range(start_size, min_size - 1, -2):
        font = ImageFont.truetype(font_path, size)
        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = word if not current else current + " " + word
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)

        spacing = int(size * 0.04)
        heights = []
        widths = []
        for line in lines:
            b = draw.textbbox((0, 0), line, font=font)
            widths.append(b[2] - b[0])
            heights.append(b[3] - b[1])

        total_h = sum(heights) + spacing * max(0, len(lines)-1)
        if total_h <= max_height:
            return font, lines, spacing

    font = ImageFont.truetype(font_path, min_size)
    return font, [text], 0

def render_card(text, cfg):
    W, H = cfg["width"], cfg["height"]
    img = Image.new("RGB", (W, H), cfg["background"])
    draw = ImageDraw.Draw(img)

    font_path = find_font()

    if cfg.get("uppercase", True):
        text = text.upper()

    left = cfg["text_left"]
    right = cfg["text_right"]
    top = cfg["text_top"]
    bottom = cfg["text_bottom"]
    max_w = W - left - right
    max_h = H - top - bottom

    font, lines, spacing = fit_text(
        draw, text, max_w, max_h, font_path,
        start_size=82, min_size=30
    )

    line_heights = []
    line_widths = []
    for line in lines:
        b = draw.textbbox((0, 0), line, font=font)
        line_widths.append(b[2] - b[0])
        line_heights.append(b[3] - b[1])

    total_h = sum(line_heights) + spacing * max(0, len(lines)-1)
    y = top + max(0, (max_h - total_h) // 2)

    for i, line in enumerate(lines):
        width = line_widths[i]
        if cfg["alignment"] == "center":
            x = (W - width) // 2
        else:
            x = left
        draw.text((x, y), line, font=font, fill=cfg["text_color"])
        y += line_heights[i] + spacing

    if cfg.get("quotes", True):
        quote_font = ImageFont.truetype(font_path, cfg["quote_size"])
        qcolor = cfg["quote_color"]
        draw.text((left + 5, 175), "“", font=quote_font, fill=qcolor)
        b = draw.textbbox((0, 0), "”", font=quote_font)
        draw.text((W - right - (b[2]-b[0]) - 5, H - 210), "”", font=quote_font, fill=qcolor)

    wm = cfg.get("watermark", "@mentedigna")
    wm_font = ImageFont.truetype(font_path, cfg.get("watermark_size", 27))
    wm_color = cfg.get("watermark_color", "#9A9A9A")
    draw.text((left, H - 205), wm, font=wm_font, fill=wm_color)

    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out
