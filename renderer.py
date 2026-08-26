from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = {
    "Montserrat ExtraBold": [
        "/usr/share/fonts/truetype/montserrat/Montserrat-ExtraBold.ttf",
        "/usr/share/fonts/truetype/montserrat/Montserrat-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "Montserrat Bold": [
        "/usr/share/fonts/truetype/montserrat/Montserrat-Bold.ttf",
        "/usr/share/fonts/truetype/montserrat/Montserrat-ExtraBold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "DejaVu Sans Bold": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
}


def find_font(name="Montserrat ExtraBold"):
    candidates = FONT_CANDIDATES.get(name, FONT_CANDIDATES["Montserrat ExtraBold"])
    for p in candidates:
        if Path(p).exists():
            return p
    raise FileNotFoundError("Nenhuma fonte compatível encontrada.")


def fit_text(draw, text, max_width, max_height, font_path, start_size=82, min_size=30, line_spacing_pct=10):
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

        spacing = max(0, round(size * (line_spacing_pct / 100)))
        heights = []
        widths = []
        for line in lines:
            b = draw.textbbox((0, 0), line, font=font)
            widths.append(b[2] - b[0])
            heights.append(b[3] - b[1])

        total_h = sum(heights) + spacing * max(0, len(lines) - 1)
        if total_h <= max_height:
            return font, lines, spacing

    font = ImageFont.truetype(font_path, min_size)
    return font, [text], max(0, round(min_size * (line_spacing_pct / 100)))


def load_background(path, size, opacity=100):
    img = Image.open(path).convert("RGB")
    W, H = size
    scale = max(W / img.width, H / img.height)
    nw, nh = max(1, round(img.width * scale)), max(1, round(img.height * scale))
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - W) // 2
    top = (nh - H) // 2
    img = img.crop((left, top, left + W, top + H))
    if opacity < 100:
        white = Image.new("RGB", (W, H), "#FFFFFF")
        img = Image.blend(white, img, max(0, min(100, opacity)) / 100)
    return img


def render_card(text, cfg):
    W, H = cfg["width"], cfg["height"]

    bg_path = cfg.get("background_image", "")
    if bg_path and Path(bg_path).exists():
        img = load_background(bg_path, (W, H), cfg.get("background_opacity", 100))
    else:
        img = Image.new("RGB", (W, H), cfg["background"])

    draw = ImageDraw.Draw(img)
    font_path = find_font(cfg.get("font", "Montserrat ExtraBold"))

    if cfg.get("uppercase", True):
        text = text.upper()

    left = int(cfg.get("text_left", 105))
    right = int(cfg.get("text_right", 105))
    top = int(cfg.get("text_top", 270))
    bottom = int(cfg.get("text_bottom", 250))
    capacity = max(50, min(120, int(cfg.get("text_capacity", 100)))) / 100
    max_w = max(100, W - left - right)
    max_h = max(100, int((H - top - bottom) * capacity))
    text_font_size = int(cfg.get("text_size", 82))
    min_size = max(24, int(text_font_size * 0.40))

    font, lines, spacing = fit_text(
        draw, text, max_w, max_h, font_path,
        start_size=text_font_size,
        min_size=min_size,
        line_spacing_pct=int(cfg.get("line_spacing", 10)),
    )

    line_heights = []
    line_widths = []
    for line in lines:
        b = draw.textbbox((0, 0), line, font=font)
        line_widths.append(b[2] - b[0])
        line_heights.append(b[3] - b[1])

    total_h = sum(line_heights) + spacing * max(0, len(lines) - 1)
    vertical_mode = cfg.get("vertical_alignment", "center")
    if vertical_mode == "top":
        y = top
    elif vertical_mode == "bottom":
        y = top + max(0, max_h - total_h)
    else:
        y = top + max(0, (max_h - total_h) // 2)

    for i, line in enumerate(lines):
        width = line_widths[i]
        if cfg.get("alignment", "left") == "center":
            x = (W - width) // 2
        elif cfg.get("alignment") == "right":
            x = W - right - width
        else:
            x = left
        draw.text((x, y), line, font=font, fill=cfg["text_color"])
        y += line_heights[i] + spacing

    if cfg.get("quotes", True):
        quote_size = int(cfg.get("quote_size", 112))
        quote_font = ImageFont.truetype(font_path, quote_size)
        qcolor = cfg["quote_color"]
        quote_offset = int(cfg.get("quote_offset", 5))
        draw.text((left + quote_offset, 175), "“", font=quote_font, fill=qcolor)
        b = draw.textbbox((0, 0), "”", font=quote_font)
        draw.text((W - right - (b[2] - b[0]) - quote_offset, H - 210), "”", font=quote_font, fill=qcolor)

    wm = cfg.get("watermark", "@mentedigna")
    wm_font = ImageFont.truetype(font_path, int(cfg.get("watermark_size", 27)))
    wm_color = cfg.get("watermark_color", "#9A9A9A")
    wm_pos = cfg.get("watermark_position", "left")
    wb = draw.textbbox((0, 0), wm, font=wm_font)
    ww = wb[2] - wb[0]
    wh = wb[3] - wb[1]
    wm_y = H - int(cfg.get("watermark_bottom", 205))
    if wm_pos == "center":
        wm_x = (W - ww) // 2
    elif wm_pos == "right":
        wm_x = W - right - ww
    else:
        wm_x = left
    draw.text((wm_x, wm_y), wm, font=wm_font, fill=wm_color)

    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out
