import os
import json
import base64
import re
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
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

user_configs = {}
pending_text = {}
last_card_text = {}


def is_allowed(update: Update) -> bool:
    if not ADMIN_USER_ID:
        return True
    return str(update.effective_user.id) == str(ADMIN_USER_ID)


def cfg_for(user_id):
    if user_id not in user_configs:
        c = DEFAULT_CONFIG.copy()
        try:
            layouts = json.loads(LAYOUT_FILE.read_text("utf-8")) if LAYOUT_FILE.exists() else {}
            saved = layouts.get(str(user_id))
            if isinstance(saved, dict):
                c.update(saved)
        except Exception:
            pass
        user_configs[user_id] = c
    return user_configs[user_id]


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
        [InlineKeyboardButton("↔️ Margens", callback_data="margins_menu"),
         InlineKeyboardButton("↕️ Posição vertical", callback_data="vertical_menu")],
        [InlineKeyboardButton("💾 Salvar layout", callback_data="save_layout"),
         InlineKeyboardButton("📂 Meus layouts", callback_data="layouts")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="back")],
    ])


def show_config_text(c):
    bg = c.get("background_image") or c["background"]
    return (
        "⚙️ *CONFIGURAÇÃO MENTE DIGNA*\n\n"
        f"• Fundo: `{bg}`\n"
        f"• Opacidade do fundo: `{c.get('background_opacity',100)}%`\n"
        f"• Fonte: `{c['font']}`\n"
        f"• Tamanho: `{c.get('text_size',82)} px`\n"
        f"• Espaçamento entre linhas: `{c.get('line_spacing',10)}%`\n"
        f"• Capacidade: `{c.get('text_capacity',100)}%`\n"
        f"• Cor do texto: `{c['text_color']}`\n"
        f"• Cor das aspas: `{c['quote_color']}`\n"
        f"• Aspas vermelhas: `{'SIM' if c['quotes'] else 'NÃO'}`\n"
        f"• Caixa alta: `{'SIM' if c['uppercase'] else 'NÃO'}`\n"
        f"• Alinhamento: `{c['alignment']}`\n"
        f"• Posição vertical: `{c.get('vertical_alignment','center')}`\n"
        f"• Marca d'água: `{c['watermark']}`\n"
        f"• Cor do @: `{c.get('watermark_color','#9A9A9A')}`\n"
        f"• Posição do @: `{c.get('watermark_position','left')}`\n"
        f"• Formato: `{c['width']} × {c['height']}`\n\n"
        "Use os botões abaixo para ajustar."
    )


def simple_menu(title, rows, back="config"):
    rows.append([InlineKeyboardButton("⬅️ Voltar", callback_data=back)])
    return InlineKeyboardMarkup(rows)


def color_value(s):
    return bool(re.fullmatch(r"#[0-9A-Fa-f]{6}", s.strip()))


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
    c = cfg_for(update.effective_user.id)
    await update.message.reply_text(show_config_text(c), reply_markup=config_menu(), parse_mode="Markdown")


async def extract_text_from_image(image_bytes: bytes) -> str:
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
                {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}", "detail": "high"}
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
        c = cfg_for(uid)
        c["background_image"] = str(path)
        context.user_data["waiting_background"] = False
        await update.message.reply_text("🖼️ Imagem de fundo atualizada.", reply_markup=config_menu())
        return

    photo = update.message.photo[-1]
    tg_file = await photo.get_file()
    data = await tg_file.download_as_bytearray()
    await update.message.reply_text("Lendo o texto... 🔎")
    try:
        text = await extract_text_from_image(bytes(data))
    except Exception as e:
        await update.message.reply_text(f"Não consegui ler a imagem. Tente uma imagem mais nítida.\n\nErro: {e}")
        return
    if not text:
        await update.message.reply_text("Não encontrei uma frase principal nessa imagem.")
        return
    pending_text[uid] = text
    await update.message.reply_text(
        f"📄 *Texto identificado:*\n\n{text}\n\nConfira antes de gerar.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ GERAR CARD", callback_data="generate")],
            [InlineKeyboardButton("✏️ COPIAR PARA EDITAR", callback_data="edit")],
        ]), parse_mode="Markdown"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    uid = update.effective_user.id
    text = update.message.text.strip()
    if text.startswith("/"):
        return
    waiting = context.user_data.get("waiting_config_input")
    if waiting:
        c = cfg_for(uid)
        kind = waiting
        if kind in {"text_color", "quote_color", "watermark_color", "background_color"}:
            if not color_value(text):
                await update.message.reply_text("Envie uma cor no formato `#000000`.", parse_mode="Markdown")
                return
            key = {"text_color":"text_color", "quote_color":"quote_color", "watermark_color":"watermark_color", "background_color":"background"}[kind]
            c[key] = text.upper()
        elif kind == "watermark_name":
            if not text.startswith("@"):
                text = "@" + text
            c["watermark"] = text
        elif kind in {"text_size", "watermark_size", "left_margin", "right_margin", "top_margin", "bottom_margin"}:
            try:
                value = int(text)
            except ValueError:
                await update.message.reply_text("Envie apenas um número inteiro.")
                return
            limits = {
                "text_size": (30, 140), "watermark_size": (12, 60),
                "left_margin": (20, 300), "right_margin": (20, 300),
                "top_margin": (50, 500), "bottom_margin": (50, 500),
            }
            lo, hi = limits[kind]
            if not lo <= value <= hi:
                await update.message.reply_text(f"Use um valor entre {lo} e {hi}.")
                return
            key = {"text_size":"text_size","watermark_size":"watermark_size","left_margin":"text_left","right_margin":"text_right","top_margin":"text_top","bottom_margin":"text_bottom"}[kind]
            c[key] = value
        context.user_data["waiting_config_input"] = None
        await update.message.reply_text(show_config_text(c), reply_markup=config_menu(), parse_mode="Markdown")
        return

    if context.user_data.get("waiting_edit"):
        pending_text[uid] = text
        context.user_data["waiting_edit"] = False
        await update.message.reply_text(
            f"📄 *Texto atualizado:*\n\n{pending_text[uid]}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ GERAR CARD", callback_data="generate")],
                [InlineKeyboardButton("✏️ EDITAR NOVAMENTE", callback_data="edit")],
            ]), parse_mode="Markdown"
        )
        return

    pending_text[uid] = text
    await update.message.reply_text(
        f"📄 *Texto recebido:*\n\n{text}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ GERAR CARD", callback_data="generate")],
            [InlineKeyboardButton("✏️ EDITAR TEXTO", callback_data="edit")],
        ]), parse_mode="Markdown"
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_allowed(update):
        return
    uid = update.effective_user.id
    c = cfg_for(uid)
    d = query.data

    if d == "back":
        await query.edit_message_text("Menu principal:", reply_markup=main_menu()); return
    if d == "config":
        await query.edit_message_text(show_config_text(c), reply_markup=config_menu(), parse_mode="Markdown"); return
    if d == "toggle_quotes":
        c["quotes"] = not c["quotes"]
    elif d == "toggle_upper":
        c["uppercase"] = not c["uppercase"]
    elif d == "set_bg_white":
        c["background"] = "#FFFFFF"; c["background_image"] = ""
    elif d == "set_bg_gray":
        c["background"] = "#F5F5F5"; c["background_image"] = ""
    elif d == "clear_bg_image":
        c["background_image"] = ""
    elif d == "set_font_mont": c["font"] = "Montserrat ExtraBold"
    elif d == "set_font_bold": c["font"] = "Montserrat Bold"
    elif d == "set_font_dejavu": c["font"] = "DejaVu Sans Bold"
    elif d == "align_left": c["alignment"] = "left"
    elif d == "align_center": c["alignment"] = "center"
    elif d == "align_right": c["alignment"] = "right"
    elif d == "vertical_top": c["vertical_alignment"] = "top"
    elif d == "vertical_center": c["vertical_alignment"] = "center"
    elif d == "vertical_bottom": c["vertical_alignment"] = "bottom"
    elif d.startswith("spacing_") and d != "spacing_menu": c["line_spacing"] = int(d.split("_")[1])
    elif d.startswith("capacity_") and d != "capacity_menu": c["text_capacity"] = int(d.split("_")[1])
    elif d.startswith("watermark_pos_"): c["watermark_position"] = d.split("_")[-1]
    elif d == "watermark_menu":
        kb = simple_menu("", [
            [InlineKeyboardButton("✍️ Alterar nome do @", callback_data="watermark_name")],
            [InlineKeyboardButton("🎨 Alterar cor do @", callback_data="watermark_color")],
            [InlineKeyboardButton("📍 Posição: esquerda", callback_data="watermark_pos_left")],
            [InlineKeyboardButton("📍 Posição: centro", callback_data="watermark_pos_center")],
            [InlineKeyboardButton("📍 Posição: direita", callback_data="watermark_pos_right")],
            [InlineKeyboardButton("🔠 Tamanho do @", callback_data="watermark_size")],
        ])
        await query.edit_message_text("✍️ *MARCA D'ÁGUA / @*", reply_markup=kb, parse_mode="Markdown"); return
    elif d == "set_bg_menu":
        kb = simple_menu("", [
            [InlineKeyboardButton("⚪ Fundo branco", callback_data="set_bg_white"), InlineKeyboardButton("◻️ Cinza claro", callback_data="set_bg_gray")],
            [InlineKeyboardButton("🎨 Digitar cor HEX", callback_data="background_color")],
            [InlineKeyboardButton("🖼️ Enviar imagem de fundo", callback_data="background_image")],
            [InlineKeyboardButton("❌ Remover imagem de fundo", callback_data="clear_bg_image")],
        ])
        await query.edit_message_text("🎨 *FUNDO*", reply_markup=kb, parse_mode="Markdown"); return
    elif d == "set_font_menu":
        kb = simple_menu("", [
            [InlineKeyboardButton("Montserrat ExtraBold", callback_data="set_font_mont")],
            [InlineKeyboardButton("Montserrat Bold", callback_data="set_font_bold")],
            [InlineKeyboardButton("DejaVu Sans Bold", callback_data="set_font_dejavu")],
        ])
        await query.edit_message_text("🔤 *FONTE*", reply_markup=kb, parse_mode="Markdown"); return
    elif d == "quote_menu":
        kb = simple_menu("", [
            [InlineKeyboardButton("🔴 Ativar/desativar aspas", callback_data="toggle_quotes")],
            [InlineKeyboardButton("🎨 Alterar cor das aspas", callback_data="quote_color")],
        ])
        await query.edit_message_text("🔴 *ASPAS*", reply_markup=kb, parse_mode="Markdown"); return
    elif d == "align_menu":
        kb = simple_menu("", [
            [InlineKeyboardButton("⬅️ Esquerda", callback_data="align_left"), InlineKeyboardButton("↔️ Centro", callback_data="align_center")],
            [InlineKeyboardButton("➡️ Direita", callback_data="align_right")],
        ])
        await query.edit_message_text("↔️ *ALINHAMENTO HORIZONTAL*", reply_markup=kb, parse_mode="Markdown"); return
    elif d == "spacing_menu":
        kb = simple_menu("", [[InlineKeyboardButton(f"{v}%", callback_data=f"spacing_{v}") for v in [0,10,20]], [InlineKeyboardButton(f"{v}%", callback_data=f"spacing_{v}") for v in [30,40]]])
        await query.edit_message_text("📏 *ESPAÇAMENTO ENTRE LINHAS*", reply_markup=kb, parse_mode="Markdown"); return
    elif d == "text_size_menu":
        kb = simple_menu("", [[InlineKeyboardButton(f"{v}px", callback_data=f"set_text_size_{v}") for v in [70,82,90]], [InlineKeyboardButton("✏️ Digitar tamanho", callback_data="text_size")]])
        await query.edit_message_text("🔠 *TAMANHO DA FONTE*", reply_markup=kb, parse_mode="Markdown"); return
    elif d.startswith("set_text_size_"):
        c["text_size"] = int(d.split("_")[-1])
    elif d == "capacity_menu":
        kb = simple_menu("", [[InlineKeyboardButton(f"{v}%", callback_data=f"capacity_{v}") for v in [75,85,100]], [InlineKeyboardButton("110%", callback_data="capacity_110")]])
        await query.edit_message_text("📐 *CAPACIDADE / ÁREA DO TEXTO*", reply_markup=kb, parse_mode="Markdown"); return
    elif d == "margins_menu":
        kb = simple_menu("", [
            [InlineKeyboardButton("↔️ Margem esquerda", callback_data="left_margin"), InlineKeyboardButton("↔️ Margem direita", callback_data="right_margin")],
            [InlineKeyboardButton("↕️ Margem superior", callback_data="top_margin"), InlineKeyboardButton("↕️ Margem inferior", callback_data="bottom_margin")],
        ])
        await query.edit_message_text("↔️ *MARGENS / DISTÂNCIAS DO TEXTO*", reply_markup=kb, parse_mode="Markdown"); return
    elif d == "vertical_menu":
        kb = simple_menu("", [[InlineKeyboardButton("⬆️ Topo", callback_data="vertical_top"), InlineKeyboardButton("↔️ Centro", callback_data="vertical_center"), InlineKeyboardButton("⬇️ Baixo", callback_data="vertical_bottom")]])
        await query.edit_message_text("↕️ *POSIÇÃO VERTICAL DO TEXTO*", reply_markup=kb, parse_mode="Markdown"); return
    elif d in {"text_color","quote_color","watermark_color","background_color","watermark_name","text_size","watermark_size","left_margin","right_margin","top_margin","bottom_margin"}:
        prompts = {
            "text_color":"🎨 Envie a cor do texto em HEX, por exemplo `#000000`.",
            "quote_color":"🔴 Envie a cor das aspas em HEX, por exemplo `#FF1717`.",
            "watermark_color":"🎨 Envie a cor do @ em HEX, por exemplo `#9A9A9A`.",
            "background_color":"🎨 Envie a cor do fundo em HEX, por exemplo `#FFFFFF`.",
            "watermark_name":"✍️ Envie o @ que deseja usar, por exemplo `@mentedigna`.",
            "text_size":"🔠 Envie o tamanho da fonte em pixels, por exemplo `82`.",
            "watermark_size":"🔠 Envie o tamanho do @ em pixels, por exemplo `27`.",
            "left_margin":"↔️ Envie a margem esquerda em pixels, por exemplo `105`.",
            "right_margin":"↔️ Envie a margem direita em pixels, por exemplo `105`.",
            "top_margin":"↕️ Envie a margem superior em pixels, por exemplo `270`.",
            "bottom_margin":"↕️ Envie a margem inferior em pixels, por exemplo `250`.",
        }
        context.user_data["waiting_config_input"] = d
        await query.edit_message_text(prompts[d], parse_mode="Markdown"); return
    elif d == "background_image":
        context.user_data["waiting_background"] = True
        await query.edit_message_text("🖼️ Envie agora a imagem que deseja usar como fundo."); return
    elif d == "save_layout":
        try: layouts = json.loads(LAYOUT_FILE.read_text("utf-8")) if LAYOUT_FILE.exists() else {}
        except Exception: layouts = {}
        layouts[str(uid)] = c
        LAYOUT_FILE.write_text(json.dumps(layouts, ensure_ascii=False, indent=2), encoding="utf-8")
        await query.edit_message_text("💾 Layout Mente Digna salvo.", reply_markup=config_menu()); return
    elif d == "layouts":
        await query.edit_message_text("📂 O layout salvo será carregado automaticamente quando o bot reiniciar.", reply_markup=config_menu()); return
    elif d == "edit":
        context.user_data["waiting_edit"] = True
        await query.edit_message_text("✏️ Envie agora o texto corrigido."); return
    elif d == "generate":
        text = pending_text.get(uid)
        if not text:
            await query.edit_message_text("Envie primeiro uma imagem ou digite uma frase."); return
        await query.edit_message_text("Gerando o card... 🎨")
        try:
            out = render_card(text, c)
            last_card_text[uid] = text
            await query.message.reply_document(document=InputFile(out, filename="mente_digna_card.png"), caption="✅ Card Mente Digna pronto.")
            await query.message.reply_text("Quer uma legenda para esse post?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 GERAR LEGENDA", callback_data="caption")]]))
        except Exception as e:
            await query.message.reply_text(f"Erro ao gerar o card: {e}")
        return
    elif d == "caption":
        text = last_card_text.get(uid) or pending_text.get(uid)
        if not text:
            await query.edit_message_text("Gere um card ou envie uma frase primeiro."); return
        await query.edit_message_text("Gerando legenda... ✍️")
        try:
            response = client.responses.create(model=MODEL, instructions=(
                "Crie uma legenda curta para Instagram baseada na frase enviada. "
                "Escreva em português do Brasil, com tom reflexivo e natural. "
                "Não repita a frase integralmente. Não use hashtags em excesso."
            ), input=text)
            await query.message.reply_text(response.output_text.strip(), reply_markup=main_menu())
        except Exception as e:
            await query.message.reply_text(f"Erro ao gerar legenda: {e}")
        return

    await query.edit_message_text(show_config_text(c), reply_markup=config_menu(), parse_mode="Markdown")


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("config", config_cmd))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()


if __name__ == "__main__":
    main()
