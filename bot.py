import os
import json
import base64
import re
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from openai import OpenAI

try:
    from renderer import render_card
except ImportError:
    from renderizador import render_card

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "")

if not BOT_TOKEN:
    raise RuntimeError("Defina BOT_TOKEN no arquivo .env")
if not OPENAI_API_KEY:
    raise RuntimeError("Defina OPENAI_API_KEY no arquivo .env")

client = OpenAI(api_key=OPENAI_API_KEY)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
BACKGROUND_DIR = DATA_DIR / "backgrounds"
BACKGROUND_DIR.mkdir(exist_ok=True)
LAYOUT_FILE = DATA_DIR / "layouts.json"

DEFAULT_CONFIG = {
    "background": "#FFFFFF",
    "background_image": "",
    "background_opacity": 100,
    "text_color": "#000000",
    "quote_color": "#FF1717",
    "font": "Montserrat ExtraBold",
    "text_size": 82,
    "line_spacing": 10,
    "text_capacity": 100,
    "text_width": 600,
    "watermark": "@mentedigna",
    "watermark_color": "#9A9A9A",
    "watermark_position": "left",
    "watermark_size": 27,
    "watermark_bottom": 205,
    "alignment": "left",
    "vertical_alignment": "center",
    "uppercase": True,
    "quotes": True,
    "width": 1080,
    "height": 1350,
    "text_left": 105,
    "text_right": 105,
    "text_top": 270,
    "text_bottom": 250,
    "quote_size": 112,
    "quote_offset": 5,
}

# 10 fontes novas + as fontes já existentes.
# O renderer usa o nome recebido aqui; se a sua versão do renderer
# tiver um mapa de fontes, os nomes devem existir nesse mapa também.
FONTS = [
    ("Montserrat ExtraBold", "font_mont_extra"),
    ("Montserrat Bold", "font_mont_bold"),
    ("Open Sans Bold", "font_open_bold"),
    ("Open Sans ExtraBold", "font_open_extra"),
    ("Roboto Bold", "font_roboto"),
    ("Roboto Black", "font_roboto_black"),
    ("Lato Bold", "font_lato"),
    ("Lato Black", "font_lato_black"),
    ("Ubuntu Bold", "font_ubuntu"),
    ("League Spartan", "font_spartan"),
    ("DejaVu Sans Bold", "font_dejavu"),
    ("Liberation Sans Bold", "font_liberation"),
    ("Noto Sans Bold", "font_noto"),
]

user_configs = {}
pending_text = {}
last_card_text = {}


def is_allowed(update):
    if not ADMIN_USER_ID:
        return True
    return str(update.effective_user.id) == str(ADMIN_USER_ID)


def load_layouts():
    if not LAYOUT_FILE.exists():
        return {}
    try:
        data = json.loads(LAYOUT_FILE.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_layouts(data):
    tmp = LAYOUT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(LAYOUT_FILE)


def normalize_user_layouts(uid):
    data = load_layouts()
    key = str(uid)
    user = data.get(key)

    # Migração do formato antigo, que guardava apenas um layout.
    if isinstance(user, dict) and "items" not in user:
        user = {"active": "Meu layout", "items": {"Meu layout": user}}
        data[key] = user
        save_layouts(data)

    if not isinstance(user, dict):
        user = {"active": "", "items": {}}
        data[key] = user

    user.setdefault("active", "")
    user.setdefault("items", {})
    return data, user


def cfg_for(uid):
    if uid not in user_configs:
        c = DEFAULT_CONFIG.copy()
        _, user = normalize_user_layouts(uid)
        active = user.get("active", "")
        saved = user.get("items", {}).get(active)
        if isinstance(saved, dict):
            c.update(saved)
        user_configs[uid] = c
    return user_configs[uid]


def simple_menu(rows, back="config"):
    rows = list(rows)
    rows.append([InlineKeyboardButton("⬅️ Voltar", callback_data=back)])
    return InlineKeyboardMarkup(rows)


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎨 Gerar Card", callback_data="generate")],
        [InlineKeyboardButton("✏️ Editar texto", callback_data="edit")],
        [InlineKeyboardButton("⚙️ Configurar layout", callback_data="config")],
        [InlineKeyboardButton("📝 Gerar legenda", callback_data="caption")],
    ])


def config_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎨 Fundo", callback_data="set_bg_menu"),
         InlineKeyboardButton("🔤 Fonte", callback_data="set_font_menu")],
        [InlineKeyboardButton("🔴 Aspas", callback_data="quote_menu"),
         InlineKeyboardButton("🔠 Caixa alta", callback_data="toggle_upper")],
        [InlineKeyboardButton("↔️ Alinhamento", callback_data="align_menu"),
         InlineKeyboardButton("✍️ Marca d'água", callback_data="watermark_menu")],
        [InlineKeyboardButton("🎨 Cor do texto", callback_data="text_color"),
         InlineKeyboardButton("📏 Espaçamento", callback_data="spacing_menu")],
        [InlineKeyboardButton("🔠 Tamanho", callback_data="text_size_menu"),
         InlineKeyboardButton("📐 Capacidade", callback_data="capacity_menu")],
        [InlineKeyboardButton("📏 Largura da área", callback_data="text_width_menu"),
         InlineKeyboardButton("↔️ Margens", callback_data="margins_menu")],
        [InlineKeyboardButton("↕️ Posição vertical", callback_data="vertical_menu")],
        [InlineKeyboardButton("💾 Salvar layout", callback_data="save_layout"),
         InlineKeyboardButton("📂 Meus layouts", callback_data="layouts")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="back")],
    ])


def show_config_text(c):
    bg = c.get("background_image") or c.get("background", "#FFFFFF")
    return (
        "⚙️ *CONFIGURAÇÃO MENTE DIGNA*\n\n"
        f"• Fundo: `{bg}`\n"
        f"• Opacidade: `{c.get('background_opacity',100)}%`\n"
        f"• Fonte: `{c.get('font')}`\n"
        f"• Tamanho: `{c.get('text_size',82)} px`\n"
        f"• Espaçamento: `{c.get('line_spacing',10)}%`\n"
        f"• Capacidade: `{c.get('text_capacity',100)}%`\n"
        f"• Largura da área: `{c.get('text_width',600)} px`\n"
        f"• Cor do texto: `{c.get('text_color','#000000')}`\n"
        f"• Cor das aspas: `{c.get('quote_color','#FF1717')}`\n"
        f"• Aspas: `{'SIM' if c.get('quotes',True) else 'NÃO'}`\n"
        f"• Caixa alta: `{'SIM' if c.get('uppercase',True) else 'NÃO'}`\n"
        f"• Alinhamento: `{c.get('alignment','left')}`\n"
        f"• Posição vertical: `{c.get('vertical_alignment','center')}`\n"
        f"• @: `{c.get('watermark','@mentedigna')}`\n"
        f"• Cor do @: `{c.get('watermark_color','#9A9A9A')}`\n"
        f"• Posição do @: `{c.get('watermark_position','left')}`\n"
        f"• Tamanho do @: `{c.get('watermark_size',27)} px`\n"
        f"• Margens: `{c.get('text_left',105)} / {c.get('text_right',105)} px`\n"
        f"• Formato: `{c.get('width',1080)} × {c.get('height',1350)}`\n\n"
        "Use os botões abaixo para ajustar."
    )


def color_value(value):
    return bool(re.fullmatch(r"#[0-9A-Fa-f]{6}", value.strip()))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    await update.message.reply_text(
        "Olá! 👋\n\n"
        "Envie uma imagem com uma frase ou digite a frase diretamente.\n\n"
        "Eu identifico o texto e preparo o card no padrão da *Mente Digna*.\n\n"
        "Depois você escolhe *Gerar Card* ou *Editar texto*.",
        reply_markup=main_menu(), parse_mode="Markdown"
    )


async def config_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    await update.message.reply_text(
        show_config_text(cfg_for(update.effective_user.id)),
        reply_markup=config_menu(), parse_mode="Markdown"
    )


async def extract_text_from_image(image_bytes):
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    response = client.responses.create(
        model=MODEL,
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": (
                    "Leia APENAS o texto principal que aparece na imagem. "
                    "Não invente, não corrija e não acrescente palavras. "
                    "Preserve pontuação, acentos e sentido. "
                    "Ignore nomes de usuário, marcas d'água, botões, números de curtidas "
                    "e qualquer texto que não faça parte da frase principal. "
                    "Retorne somente o texto identificado."
                )},
                {"type": "input_image",
                 "image_url": f"data:image/jpeg;base64,{b64}",
                 "detail": "high"}
            ]
        }]
    )
    return response.output_text.strip()


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    uid = update.effective_user.id

    if context.user_data.get("waiting_background"):
        photo = update.message.photo[-1]
        tg_file = await photo.get_file()
        data = await tg_file.download_as_bytearray()
        path = BACKGROUND_DIR / f"{uid}.jpg"
        path.write_bytes(bytes(data))
        cfg_for(uid)["background_image"] = str(path)
        context.user_data["waiting_background"] = False
        await update.message.reply_text(
            "🖼️ Imagem de fundo atualizada.", reply_markup=config_menu()
        )
        return

    photo = update.message.photo[-1]
    tg_file = await photo.get_file()
    data = await tg_file.download_as_bytearray()
    await update.message.reply_text("Lendo o texto... 🔎")

    try:
        text = await extract_text_from_image(bytes(data))
    except Exception as e:
        await update.message.reply_text(
            f"Não consegui ler a imagem.\n\nErro: {e}"
        )
        return

    if not text:
        await update.message.reply_text(
            "Não encontrei uma frase principal nessa imagem."
        )
        return

    pending_text[uid] = text
    await update.message.reply_text(
        f"📄 *Texto identificado:*\n\n{text}\n\nConfira antes de gerar.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ GERAR CARD", callback_data="generate")],
            [InlineKeyboardButton("✏️ COPIAR PARA EDITAR", callback_data="edit")],
        ]),
        parse_mode="Markdown"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return

    uid = update.effective_user.id
    text = update.message.text.strip()
    if text.startswith("/"):
        return

    # SALVAR LAYOUT: o texto recebido aqui é o nome do layout.
    if context.user_data.get("waiting_layout_name"):
        if not text:
            await update.message.reply_text("Digite um nome para o layout.")
            return
        if len(text) > 40:
            await update.message.reply_text(
                "Use no máximo 40 caracteres para o nome."
            )
            return

        data, user = normalize_user_layouts(uid)
        user["items"][text] = cfg_for(uid).copy()
        user["active"] = text
        data[str(uid)] = user
        save_layouts(data)

        context.user_data["waiting_layout_name"] = False
        await update.message.reply_text(
            f"✅ Layout *{text}* salvo com sucesso!\n\n"
            "Ele já está disponível em 📂 *Meus layouts*.",
            reply_markup=config_menu(), parse_mode="Markdown"
        )
        return

    waiting = context.user_data.get("waiting_config_input")
    if waiting:
        c = cfg_for(uid)

        if waiting in {"text_color", "quote_color", "watermark_color", "background_color"}:
            if not color_value(text):
                await update.message.reply_text(
                    "Envie uma cor no formato `#000000`.",
                    parse_mode="Markdown"
                )
                return
            key = {
                "text_color": "text_color",
                "quote_color": "quote_color",
                "watermark_color": "watermark_color",
                "background_color": "background",
            }[waiting]
            c[key] = text.upper()

        elif waiting == "watermark_name":
            c["watermark"] = text if text.startswith("@") else "@" + text

        elif waiting == "font_custom":
            c["font"] = text

        elif waiting in {
            "text_size", "watermark_size", "left_margin", "right_margin",
            "top_margin", "bottom_margin", "watermark_bottom",
            "quote_size", "quote_offset"
        }:
            try:
                value = int(text)
            except ValueError:
                await update.message.reply_text("Envie apenas um número inteiro.")
                return
            limits = {
                "text_size": (30, 180),
                "watermark_size": (10, 80),
                "left_margin": (0, 500),
                "right_margin": (0, 500),
                "top_margin": (0, 700),
                "bottom_margin": (0, 700),
                "watermark_bottom": (20, 700),
                "quote_size": (30, 200),
                "quote_offset": (-100, 100),
            }
            lo, hi = limits[waiting]
            if not lo <= value <= hi:
                await update.message.reply_text(f"Use um valor entre {lo} e {hi}.")
                return
            key = {
                "text_size": "text_size",
                "watermark_size": "watermark_size",
                "left_margin": "text_left",
                "right_margin": "text_right",
                "top_margin": "text_top",
                "bottom_margin": "text_bottom",
                "watermark_bottom": "watermark_bottom",
                "quote_size": "quote_size",
                "quote_offset": "quote_offset",
            }[waiting]
            c[key] = value

        elif waiting == "spacing_custom":
            try:
                value = int(text)
            except ValueError:
                await update.message.reply_text("Envie um número inteiro.")
                return
            if not -50 <= value <= 100:
                await update.message.reply_text("Use entre -50% e 100%.")
                return
            c["line_spacing"] = value

        elif waiting == "capacity_custom":
            try:
                value = int(text)
            except ValueError:
                await update.message.reply_text("Envie um número inteiro.")
                return
            if not 40 <= value <= 140:
                await update.message.reply_text("Use entre 40% e 140%.")
                return
            c["text_capacity"] = value

        elif waiting == "text_width":
            try:
                value = int(text)
            except ValueError:
                await update.message.reply_text("Envie um número inteiro.")
                return
            if not 300 <= value <= 900:
                await update.message.reply_text("Use uma largura entre 300 e 900 px.")
                return
            c["text_width"] = value

        elif waiting == "background_opacity":
            try:
                value = int(text)
            except ValueError:
                await update.message.reply_text("Envie um número inteiro.")
                return
            if not 0 <= value <= 100:
                await update.message.reply_text("Use entre 0 e 100%.")
                return
            c["background_opacity"] = value

        elif waiting == "width_height":
            parts = re.split(r"[xX×,\s]+", text)
            if len(parts) != 2:
                await update.message.reply_text("Use, por exemplo, `1080x1350`.", parse_mode="Markdown")
                return
            try:
                w, h = int(parts[0]), int(parts[1])
            except ValueError:
                await update.message.reply_text("Use dois números.")
                return
            if not (300 <= w <= 3000 and 300 <= h <= 3000):
                await update.message.reply_text("Cada dimensão deve ficar entre 300 e 3000 px.")
                return
            c["width"], c["height"] = w, h

        context.user_data["waiting_config_input"] = None
        await update.message.reply_text(
            show_config_text(c), reply_markup=config_menu(), parse_mode="Markdown"
        )
        return

    if context.user_data.get("waiting_edit"):
        pending_text[uid] = text
        context.user_data["waiting_edit"] = False
        await update.message.reply_text(
            f"📄 *Texto atualizado:*\n\n{text}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ GERAR CARD", callback_data="generate")],
                [InlineKeyboardButton("✏️ EDITAR NOVAMENTE", callback_data="edit")],
            ]),
            parse_mode="Markdown"
        )
        return

    pending_text[uid] = text
    await update.message.reply_text(
        f"📄 *Texto recebido:*\n\n{text}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ GERAR CARD", callback_data="generate")],
            [InlineKeyboardButton("✏️ EDITAR TEXTO", callback_data="edit")],
        ]),
        parse_mode="Markdown"
    )


def font_menu():
    rows = []
    for i in range(0, len(FONTS), 2):
        rows.append([
            InlineKeyboardButton(name, callback_data=callback)
            for name, callback in FONTS[i:i + 2]
        ])
    rows.append([
        InlineKeyboardButton("✏️ Digitar fonte", callback_data="font_custom")
    ])
    return simple_menu(rows)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_allowed(update):
        return

    uid = update.effective_user.id
    c = cfg_for(uid)
    d = query.data

    if d == "back":
        await query.edit_message_text("Menu principal:", reply_markup=main_menu())
        return

    if d == "config":
        await query.edit_message_text(
            show_config_text(c), reply_markup=config_menu(), parse_mode="Markdown"
        )
        return

    if d == "toggle_quotes":
        c["quotes"] = not c.get("quotes", True)

    elif d == "toggle_upper":
        c["uppercase"] = not c.get("uppercase", True)

    # FUNDOS
    elif d == "set_bg_white":
        c["background"], c["background_image"] = "#FFFFFF", ""
    elif d == "set_bg_black":
        c["background"], c["background_image"] = "#000000", ""
    elif d == "set_bg_gray":
        c["background"], c["background_image"] = "#F5F5F5", ""
    elif d == "set_bg_offwhite":
        c["background"], c["background_image"] = "#FAFAFA", ""
    elif d == "set_bg_beige":
        c["background"], c["background_image"] = "#F2EEE7", ""
    elif d == "clear_bg_image":
        c["background_image"] = ""

    # FONTES
    elif d.startswith("font_"):
        font_map = {callback: name for name, callback in FONTS}
        if d in font_map:
            c["font"] = font_map[d]
        elif d == "font_custom":
            context.user_data["waiting_config_input"] = "font_custom"
            await query.edit_message_text(
                "🔤 Envie o nome da fonte.\n\nExemplo: `Open Sans Bold`",
                parse_mode="Markdown"
            )
            return

    # ALINHAMENTO
    elif d == "align_left":
        c["alignment"] = "left"
    elif d == "align_center":
        c["alignment"] = "center"
    elif d == "align_right":
        c["alignment"] = "right"

    # POSIÇÃO VERTICAL
    elif d == "vertical_top":
        c["vertical_alignment"] = "top"
    elif d == "vertical_center":
        c["vertical_alignment"] = "center"
    elif d == "vertical_bottom":
        c["vertical_alignment"] = "bottom"

    # ESPAÇAMENTO
    elif d.startswith("spacing_") and d != "spacing_menu":
        c["line_spacing"] = int(d.split("_")[-1])

    # CAPACIDADE
    elif d.startswith("capacity_") and d != "capacity_menu":
        c["text_capacity"] = int(d.split("_")[-1])
    elif d.startswith("textwidth_"):
        c["text_width"] = int(d.split("_")[-1])

    # TAMANHO
    elif d.startswith("textsize_"):
        c["text_size"] = int(d.split("_")[-1])

    elif d.startswith("watermark_pos_"):
        c["watermark_position"] = d.split("_")[-1]

    # MENUS
    elif d == "set_bg_menu":
        await query.edit_message_text(
            "🎨 *FUNDO*",
            reply_markup=simple_menu([
                [InlineKeyboardButton("⚪ Branco", callback_data="set_bg_white"),
                 InlineKeyboardButton("⚫ Preto", callback_data="set_bg_black")],
                [InlineKeyboardButton("◻️ Cinza", callback_data="set_bg_gray"),
                 InlineKeyboardButton("⬜ Off-white", callback_data="set_bg_offwhite")],
                [InlineKeyboardButton("🟫 Bege", callback_data="set_bg_beige"),
                 InlineKeyboardButton("🎨 Cor HEX", callback_data="background_color")],
                [InlineKeyboardButton("🖼️ Imagem", callback_data="background_image"),
                 InlineKeyboardButton("❌ Remover imagem", callback_data="clear_bg_image")],
                [InlineKeyboardButton("🌫️ Opacidade", callback_data="background_opacity")],
            ]),
            parse_mode="Markdown"
        )
        return

    elif d == "background_image":
        context.user_data["waiting_background"] = True
        await query.edit_message_text("🖼️ Envie agora a imagem que deseja usar como fundo.")
        return

    elif d == "set_font_menu":
        await query.edit_message_text(
            "🔤 *FONTES*\n\nEscolha uma das fontes:",
            reply_markup=font_menu(), parse_mode="Markdown"
        )
        return

    elif d == "quote_menu":
        await query.edit_message_text(
            "🔴 *ASPAS*",
            reply_markup=simple_menu([
                [InlineKeyboardButton("🔴 Ativar/desativar", callback_data="toggle_quotes")],
                [InlineKeyboardButton("🎨 Cor", callback_data="quote_color")],
                [InlineKeyboardButton("🔠 Tamanho", callback_data="quote_size")],
                [InlineKeyboardButton("↔️ Distância", callback_data="quote_offset")],
            ]),
            parse_mode="Markdown"
        )
        return

    elif d == "align_menu":
        await query.edit_message_text(
            "↔️ *ALINHAMENTO*",
            reply_markup=simple_menu([
                [InlineKeyboardButton("⬅️ Esquerda", callback_data="align_left"),
                 InlineKeyboardButton("↔️ Centro", callback_data="align_center"),
                 InlineKeyboardButton("➡️ Direita", callback_data="align_right")]
            ]),
            parse_mode="Markdown"
        )
        return

    elif d == "spacing_menu":
        values = [0, 5, 10, 15, 20, 25, 30, 40, 50, 60, 75]
        rows = []
        for i in range(0, len(values), 3):
            rows.append([
                InlineKeyboardButton(f"{v}%", callback_data=f"spacing_{v}")
                for v in values[i:i + 3]
            ])
        rows.append([InlineKeyboardButton("✏️ Personalizado", callback_data="spacing_custom")])
        await query.edit_message_text(
            "📏 *ESPAÇAMENTO ENTRE LINHAS*\n\n"
            "Controla a distância vertical entre uma linha e a seguinte.",
            reply_markup=simple_menu(rows), parse_mode="Markdown"
        )
        return

    elif d == "text_size_menu":
        values = [60, 65, 70, 75, 80, 82, 85, 90, 95, 100, 110, 120, 130, 140]
        rows = []
        for i in range(0, len(values), 4):
            rows.append([
                InlineKeyboardButton(f"{v}px", callback_data=f"textsize_{v}")
                for v in values[i:i + 4]
            ])
        rows.append([InlineKeyboardButton("✏️ Personalizado", callback_data="text_size")])
        await query.edit_message_text(
            "🔠 *TAMANHO DA FONTE*",
            reply_markup=simple_menu(rows), parse_mode="Markdown"
        )
        return

    elif d == "capacity_menu":
        values = [50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115, 120, 130, 140]
        rows = []
        for i in range(0, len(values), 4):
            rows.append([
                InlineKeyboardButton(f"{v}%", callback_data=f"capacity_{v}")
                for v in values[i:i + 4]
            ])
        rows.append([InlineKeyboardButton("✏️ Personalizado", callback_data="capacity_custom")])
        await query.edit_message_text(
            "📐 *CAPACIDADE / ÁREA DO TEXTO*\n\n"
            "Valores menores deixam o bloco mais estreito. Valores maiores permitem linhas mais largas.",
            reply_markup=simple_menu(rows), parse_mode="Markdown"
        )
        return

    elif d == "text_width_menu":
        values = [450, 475, 500, 525, 550, 575, 600, 625, 650, 675, 700, 725, 750, 800]
        rows = []
        for i in range(0, len(values), 4):
            rows.append([
                InlineKeyboardButton(f"{v}px", callback_data=f"textwidth_{v}")
                for v in values[i:i + 4]
            ])
        rows.append([InlineKeyboardButton("✏️ Personalizado", callback_data="text_width")])
        await query.edit_message_text(
            "📏 *LARGURA DA ÁREA DO TEXTO*\\n\\n"
            "Define o limite horizontal real do bloco de texto.\\n"
            "Para o estilo de referência, comece em *600 px*.",
            reply_markup=simple_menu(rows), parse_mode="Markdown"
        )
        return

    elif d == "margins_menu":
        await query.edit_message_text(
            "↔️ *MARGENS DO TEXTO*",
            reply_markup=simple_menu([
                [InlineKeyboardButton("↔️ Esquerda", callback_data="left_margin"),
                 InlineKeyboardButton("↔️ Direita", callback_data="right_margin")],
                [InlineKeyboardButton("↕️ Superior", callback_data="top_margin"),
                 InlineKeyboardButton("↕️ Inferior", callback_data="bottom_margin")],
                [InlineKeyboardButton("📏 Presets", callback_data="margin_presets")],
            ]),
            parse_mode="Markdown"
        )
        return

    elif d == "margin_presets":
        presets = [
            ("Muito estreita", 40, 40),
            ("Estreita", 70, 70),
            ("Padrão", 105, 105),
            ("Larga", 140, 140),
            ("Muito larga", 180, 180),
            ("Super larga", 220, 220),
        ]
        await query.edit_message_text(
            "📏 *PRESETS DE MARGENS*",
            reply_markup=simple_menu([
                [InlineKeyboardButton(name, callback_data=f"marginpreset_{l}_{r}")]
                for name, l, r in presets
            ]),
            parse_mode="Markdown"
        )
        return

    elif d.startswith("marginpreset_"):
        _, l, r = d.split("_")
        c["text_left"], c["text_right"] = int(l), int(r)

    elif d == "vertical_menu":
        await query.edit_message_text(
            "↕️ *POSIÇÃO VERTICAL*",
            reply_markup=simple_menu([[
                InlineKeyboardButton("⬆️ Topo", callback_data="vertical_top"),
                InlineKeyboardButton("↔️ Centro", callback_data="vertical_center"),
                InlineKeyboardButton("⬇️ Baixo", callback_data="vertical_bottom")
            ]]),
            parse_mode="Markdown"
        )
        return

    elif d == "watermark_menu":
        await query.edit_message_text(
            "✍️ *MARCA D'ÁGUA / @*",
            reply_markup=simple_menu([
                [InlineKeyboardButton("✍️ Alterar @", callback_data="watermark_name")],
                [InlineKeyboardButton("🎨 Cor do @", callback_data="watermark_color")],
                [InlineKeyboardButton("⬅️ Esquerda", callback_data="watermark_pos_left"),
                 InlineKeyboardButton("↔️ Centro", callback_data="watermark_pos_center"),
                 InlineKeyboardButton("➡️ Direita", callback_data="watermark_pos_right")],
                [InlineKeyboardButton("🔠 Tamanho", callback_data="watermark_size")],
                [InlineKeyboardButton("↕️ Distância inferior", callback_data="watermark_bottom")],
            ]),
            parse_mode="Markdown"
        )
        return

    # ENTRADAS MANUAIS
    elif d in {
        "text_color", "quote_color", "watermark_color", "background_color",
        "watermark_name", "font_custom", "text_size", "watermark_size",
        "left_margin", "right_margin", "top_margin", "bottom_margin",
        "watermark_bottom", "quote_size", "quote_offset",
        "background_opacity", "spacing_custom", "capacity_custom", "text_width", "width_height"
    }:
        prompts = {
            "text_color": "🎨 Envie a cor do texto em HEX, por exemplo `#000000`.",
            "quote_color": "🔴 Envie a cor das aspas em HEX, por exemplo `#FF1717`.",
            "watermark_color": "🎨 Envie a cor do @ em HEX, por exemplo `#9A9A9A`.",
            "background_color": "🎨 Envie a cor do fundo em HEX, por exemplo `#FFFFFF`.",
            "watermark_name": "✍️ Envie o @ que deseja usar, por exemplo `@mentedigna`.",
            "font_custom": "🔤 Envie o nome exato da fonte, por exemplo `Open Sans Bold`.",
            "text_size": "🔠 Envie o tamanho da fonte em pixels, por exemplo `82`.",
            "watermark_size": "🔠 Envie o tamanho do @ em pixels, por exemplo `27`.",
            "left_margin": "↔️ Envie a margem esquerda em pixels, por exemplo `105`.",
            "right_margin": "↔️ Envie a margem direita em pixels, por exemplo `105`.",
            "top_margin": "↕️ Envie a margem superior em pixels, por exemplo `270`.",
            "bottom_margin": "↕️ Envie a margem inferior em pixels, por exemplo `250`.",
            "watermark_bottom": "↕️ Envie a distância inferior do @ em pixels, por exemplo `205`.",
            "quote_size": "🔠 Envie o tamanho das aspas em pixels, por exemplo `112`.",
            "quote_offset": "↔️ Envie a distância das aspas em pixels, de -100 a 100.",
            "background_opacity": "🌫️ Envie a opacidade do fundo entre 0 e 100.",
            "spacing_custom": "📏 Digite o espaçamento entre linhas. Exemplo: `15`.",
            "capacity_custom": "📐 Digite a capacidade/área. Exemplo: `92`.",
            "text_width": "📏 Digite a largura da área do texto em pixels. Exemplo: `600`.",
            "width_height": "📐 Envie largura x altura, por exemplo `1080x1350`.",
        }
        context.user_data["waiting_config_input"] = d
        await query.edit_message_text(prompts[d], parse_mode="Markdown")
        return

    # SALVAR LAYOUT: agora pede nome em vez de salvar imediatamente.
    elif d == "save_layout":
        context.user_data["waiting_layout_name"] = True
        await query.edit_message_text(
            "💾 *SALVAR LAYOUT*\n\n"
            "Digite agora o nome que deseja dar a este layout.\n\n"
            "Exemplos:\n"
            "• `Mente Digna`\n"
            "• `Palavrisei`\n"
            "• `Card preto`\n"
            "• `Estilo 2`",
            parse_mode="Markdown"
        )
        return

    # MEUS LAYOUTS
    elif d == "layouts":
        data, user = normalize_user_layouts(uid)
        items = user.get("items", {})
        active = user.get("active", "")

        if not items:
            await query.edit_message_text(
                "📂 *MEUS LAYOUTS*\n\n"
                "Você ainda não salvou nenhum layout.\n\n"
                "Configure o card e toque em 💾 *Salvar layout*.",
                reply_markup=config_menu(), parse_mode="Markdown"
            )
            return

        names = list(items.keys())
        rows = []
        for i, name in enumerate(names):
            prefix = "🟢 " if name == active else ""
            rows.append([InlineKeyboardButton(
                f"{prefix}{name}", callback_data=f"load_layout:{i}"
            )])

        rows.append([InlineKeyboardButton(
            "🗑️ Apagar layout", callback_data="delete_layout_menu"
        )])

        await query.edit_message_text(
            "📂 *MEUS LAYOUTS*\n\n"
            "🟢 = layout atualmente carregado.\n\n"
            "Toque em um nome para carregar o estilo.",
            reply_markup=simple_menu(rows), parse_mode="Markdown"
        )
        return

    elif d.startswith("load_layout:"):
        try:
            index = int(d.split(":")[1])
        except (ValueError, IndexError):
            await query.edit_message_text("Layout inválido.", reply_markup=config_menu())
            return

        data, user = normalize_user_layouts(uid)
        names = list(user.get("items", {}).keys())
        if not 0 <= index < len(names):
            await query.edit_message_text("Layout não encontrado.", reply_markup=config_menu())
            return

        name = names[index]
        saved = user["items"].get(name, {})
        c.clear()
        c.update(DEFAULT_CONFIG)
        c.update(saved)
        user["active"] = name
        data[str(uid)] = user
        save_layouts(data)

        await query.edit_message_text(
            f"📂 Layout *{name}* carregado com sucesso.",
            reply_markup=config_menu(), parse_mode="Markdown"
        )
        return

    elif d == "delete_layout_menu":
        _, user = normalize_user_layouts(uid)
        names = list(user.get("items", {}).keys())
        if not names:
            await query.edit_message_text("Não há layouts salvos.", reply_markup=config_menu())
            return

        await query.edit_message_text(
            "🗑️ *APAGAR LAYOUT*\n\nEscolha qual deseja apagar.",
            reply_markup=simple_menu([
                [InlineKeyboardButton(f"🗑️ {name}", callback_data=f"delete_layout:{i}")]
                for i, name in enumerate(names)
            ], back="layouts"),
            parse_mode="Markdown"
        )
        return

    elif d.startswith("delete_layout:"):
        try:
            index = int(d.split(":")[1])
        except (ValueError, IndexError):
            await query.edit_message_text("Layout inválido.", reply_markup=config_menu())
            return

        data, user = normalize_user_layouts(uid)
        names = list(user.get("items", {}).keys())
        if not 0 <= index < len(names):
            await query.edit_message_text("Layout não encontrado.", reply_markup=config_menu())
            return

        name = names[index]
        del user["items"][name]
        if user.get("active") == name:
            user["active"] = next(iter(user["items"]), "")
        data[str(uid)] = user
        save_layouts(data)

        await query.edit_message_text(
            f"🗑️ Layout *{name}* apagado.",
            reply_markup=config_menu(), parse_mode="Markdown"
        )
        return

    elif d == "edit":
        context.user_data["waiting_edit"] = True
        await query.edit_message_text("✏️ Envie agora o texto corrigido.")
        return

    elif d == "generate":
        text = pending_text.get(uid)
        if not text:
            await query.edit_message_text("Envie primeiro uma imagem ou digite uma frase.")
            return

        await query.edit_message_text("Gerando o card... 🎨")
        try:
            out = render_card(text, c)
            last_card_text[uid] = text
            await query.message.reply_document(
                document=InputFile(out, filename="mente_digna_card.png"),
                caption="✅ Card Mente Digna pronto."
            )
            await query.message.reply_text(
                "Quer uma legenda para esse post?",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📝 GERAR LEGENDA", callback_data="caption")
                ]])
            )
        except Exception as e:
            await query.message.reply_text(f"Erro ao gerar o card: {e}")
        return

    elif d == "caption":
        text = last_card_text.get(uid) or pending_text.get(uid)
        if not text:
            await query.edit_message_text("Gere um card ou envie uma frase primeiro.")
            return

        await query.edit_message_text("Gerando legenda... ✍️")
        try:
            response = client.responses.create(
                model=MODEL,
                instructions=(
                    "Crie uma legenda longa e envolvente para Instagram baseada na frase enviada. "
                    "Escreva em português do Brasil, com tom reflexivo, emocional, natural e profissional. "
                    "A legenda deve ter EXATAMENTE 4 parágrafos, separados por uma linha em branco. "
                    "O primeiro deve criar identificação e reflexão; o segundo aprofundar a mensagem; "
                    "o terceiro transformar a reflexão em uma ideia prática ou mudança de mentalidade; "
                    "o quarto deve terminar com uma pergunta natural que incentive comentários. "
                    "Não repita a frase integralmente. Não use hashtags, títulos, números ou observações."
                ),
                input=text
            )
            await query.message.reply_text(
                response.output_text.strip(), reply_markup=main_menu()
            )
        except Exception as e:
            await query.message.reply_text(f"Erro ao gerar legenda: {e}")
        return

    await query.edit_message_text(
        show_config_text(c), reply_markup=config_menu(), parse_mode="Markdown"
    )


async def error_handler(update, context):
    print(f"Erro no bot: {context.error}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("config", config_cmd))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)
    app.run_polling()


if __name__ == "__main__":
    main()
