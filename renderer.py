from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Fontes suportadas pelo menu do bot.
# O Dockerfile instala as famílias adicionais no ambiente do Railway.
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
    "Open Sans Bold": [
        "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf",
        "/usr/share/fonts/truetype/open-sans/OpenSans-ExtraBold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "Open Sans ExtraBold": [
        "/usr/share/fonts/truetype/open-sans/OpenSans-ExtraBold.ttf",
        "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "Roboto Bold": [
        "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Bold.ttf",
        "/usr/share/fonts/truetype/roboto/Roboto-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "Roboto Black": [
        "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Black.ttf",
        "/usr/share/fonts/truetype/roboto/Roboto-Black.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "Lato Bold": [
        "/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
        "/usr/share/fonts/truetype/lato/Lato-Heavy.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "Lato Black": [
        "/usr/share/fonts/truetype/lato/Lato-Black.ttf",
        "/usr/share/fonts/truetype/lato/Lato-Heavy.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "Liberation Sans Bold": [
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "Noto Sans Bold": [
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "Ubuntu Bold": [
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "League Spartan": [
        "/usr/share/fonts/truetype/league-spartan/LeagueSpartan-Bold.ttf",
        "/usr/share/fonts/truetype/league-spartan/LeagueSpartan-Bold.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "League Spartan Bold": [
        "/usr/share/fonts/truetype/league-spartan/LeagueSpartan-Bold.ttf",
        "/usr/share/fonts/truetype/league-spartan/LeagueSpartan-Bold.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "DejaVu Sans Bold": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
}

# Fallback por padrões de nome. Isso torna o renderer mais resistente a pequenas
# diferenças de caminho entre imagens Debian/Ubuntu.
FONT_GLOBS = {
    "Open Sans Bold": ["OpenSans-Bold.ttf", "OpenSans-ExtraBold.ttf"],
    "Open Sans ExtraBold": ["OpenSans-ExtraBold.ttf", "OpenSans-Bold.ttf"],
    "Roboto Bold": ["Roboto-Bold.ttf"],
    "Roboto Black": ["Roboto-Black.ttf", "Roboto-Bold.ttf"],
    "Lato Bold": ["Lato-Bold.ttf", "Lato-Heavy.ttf"],
    "Lato Black": ["Lato-Black.ttf", "Lato-Heavy.ttf"],
    "Liberation Sans Bold": ["LiberationSans-Bold.ttf"],
    "Noto Sans Bold": ["NotoSans-Bold.ttf"],
    "Ubuntu Bold": ["Ubuntu-B.ttf", "Ubuntu-Bold.ttf"],
    "League Spartan": ["LeagueSpartan-Bold.ttf", "LeagueSpartan-Bold.otf"],
    "League Spartan Bold": ["LeagueSpartan-Bold.ttf", "LeagueSpartan-Bold.otf"],
}


def find_font(name="Montserrat ExtraBold"):
    candidates = FONT_CANDIDATES.get(
        name,
        FONT_CANDIDATES["Montserrat ExtraBold"]
    )

    for p in candidates:
        if Path(p).exists():
            return p

    # Procura em diretórios padrão por nome de arquivo.
    patterns = FONT_GLOBS.get(name, [])
    roots = [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path("fonts"),
    ]
    for root in roots:
        if not root.exists():
            continue
        for filename in patterns:
            matches = list(root.rglob(filename))
            if matches:
                return str(matches[0])

    # Última tentativa: localizar a família pelo nome informado.
    # Isso também permite fontes personalizadas sem quebrar o gerador.
    normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in str(name)).split()
    if normalized:
        roots = [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path("fonts")]
        for root in roots:
            if not root.exists():
                continue
            for fp in root.rglob("*"):
                if not fp.is_file() or fp.suffix.lower() not in {".ttf", ".otf"}:
                    continue
                fn = fp.stem.lower().replace("-", " ").replace("_", " ")
                if all(part in fn for part in normalized):
                    return str(fp)

    # Último fallback: DejaVu Sans Bold.
    fallback = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    if fallback.exists():
        return str(fallback)

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
    # A largura da área é um limite horizontal real e independente das margens.
    # 600 px reproduz aproximadamente o bloco estreito e organizado do modelo de referência.
    available_w = max(100, W - left - right)
    configured_w = int(cfg.get("text_width", 600))
    max_w = max(100, min(available_w, configured_w))
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
            x = left + max(0, (max_w - width) // 2)
        elif cfg.get("alignment") == "right":
            x = left + max(0, max_w - width)
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
    wm_y = H - int(cfg.get("watermark_bottom", 205)) - wh
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
