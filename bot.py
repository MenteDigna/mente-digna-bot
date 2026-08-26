
import os
import json
import base64
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from openai import OpenAI

from renderer import render_card

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
LAYOUT_FILE = DATA_DIR / "layouts.json"

DEFAULT_CONFIG = {
    "background": "#FFFFFF",
    "text_color": "#000000",
    "quote_color": "#FF1717",
    "font": "Montserrat ExtraBold",
    "watermark": "@mentedigna",
    "watermark_color": "#9A9A9A",
    "alignment": "left",
    "uppercase": True,
    "quotes": True,
    "width": 1080,
    "height": 1350,
    "text_left": 105,
    "text_right": 105,
    "text_top": 270,
    "text_bottom": 250,
    "quote_size": 112,
    "watermark_size": 27,
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
        user_configs[user_id] = DEFAULT_CONFIG.copy()
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
        [InlineKeyboardButton("🎨 Fundo", callback_data="set_bg"),
         InlineKeyboardButton("🔤 Fonte", callback_data="set_font")],
        [InlineKeyboardButton("🔴 Aspas", callback_data="toggle_quotes"),
         InlineKeyboardButton("🔠 Caixa alta", callback_data="toggle_upper")],
        [InlineKeyboardButton("↔️ Alinhamento", callback_data="align"),
         InlineKeyboardButton("✍️ Marca d'água", callback_data="watermark")],
        [InlineKeyboardButton("💾 Salvar layout", callback_data="save_layout"),
         InlineKeyboardButton("📂 Meus layouts", callback_data="layouts")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="back")],
    ])

def show_config_text(c):
    return (
        "⚙️ *CONFIGURAÇÃO MENTE DIGNA*\n\n"
        f"• Fundo: `{c['background']}`\n"
        f"• Fonte: `{c['font']}`\n"
        f"• Cor do texto: `{c['text_color']}`\n"
        f"• Cor das aspas: `{c['quote_color']}`\n"
        f"• Aspas vermelhas: `{'SIM' if c['quotes'] else 'NÃO'}`\n"
        f"• Caixa alta: `{'SIM' if c['uppercase'] else 'NÃO'}`\n"
        f"• Alinhamento: `{c['alignment']}`\n"
        f"• Marca d'água: `{c['watermark']}`\n"
        f"• Formato: `{c['width']} × {c['height']}`\n\n"
        "Use os botões abaixo para ajustar."
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    await update.message.reply_text(
        "Olá! 👋\n\n"
        "Envie uma imagem com uma frase ou digite a frase diretamente.\n\n"
        "Eu identifico o texto e preparo o card no padrão da *Mente Digna*:\n"
        "fundo branco, tipografia pesada, aspas vermelhas e @mentedigna.\n\n"
        "Depois você escolhe *Gerar Card* ou *Editar texto*.",
        reply_markup=main_menu(),
        parse_mode="Markdown"
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
                {
                    "type": "input_text",
                    "text": (
                        "Leia APENAS o texto principal que aparece na imagem. "
                        "Não invente, não corrija e não acrescente palavras. "
                        "Preserve pontuação, acentos e sentido. "
                        "Ignore nomes de usuário, marcas d'água, botões, números de curtidas "
                        "e qualquer texto que não faça parte da frase principal. "
                        "Retorne somente o texto identificado."
                    )
                },
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{b64}",
                    "detail": "high"
                }
            ]
        }]
    )
    return response.output_text.strip()

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
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

    uid = update.effective_user.id
    pending_text[uid] = text
    await update.message.reply_text(
        f"📄 *Texto identificado:*\n\n{text}\n\n"
        "Confira antes de gerar.",
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
    pending_text[uid] = text
    await update.message.reply_text(
        f"📄 *Texto recebido:*\n\n{text}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ GERAR CARD", callback_data="generate")],
            [InlineKeyboardButton("✏️ EDITAR TEXTO", callback_data="edit")],
        ]),
        parse_mode="Markdown"
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_allowed(update):
        return
    uid = update.effective_user.id
    c = cfg_for(uid)

    if query.data == "back":
        await query.edit_message_text("Menu principal:", reply_markup=main_menu())
        return

    if query.data == "config":
        await query.edit_message_text(show_config_text(c), reply_markup=config_menu(), parse_mode="Markdown")
        return

    if query.data == "toggle_quotes":
        c["quotes"] = not c["quotes"]
        await query.edit_message_text(show_config_text(c), reply_markup=config_menu(), parse_mode="Markdown")
        return

    if query.data == "toggle_upper":
        c["uppercase"] = not c["uppercase"]
        await query.edit_message_text(show_config_text(c), reply_markup=config_menu(), parse_mode="Markdown")
        return

    if query.data == "align":
        c["alignment"] = "center" if c["alignment"] == "left" else "left"
        await query.edit_message_text(show_config_text(c), reply_markup=config_menu(), parse_mode="Markdown")
        return

    if query.data == "set_bg":
        c["background"] = "#FFFFFF" if c["background"] != "#FFFFFF" else "#F5F5F5"
        await query.edit_message_text(show_config_text(c), reply_markup=config_menu(), parse_mode="Markdown")
        return

    if query.data == "set_font":
        c["font"] = "Montserrat ExtraBold" if c["font"] != "Montserrat ExtraBold" else "DejaVu Sans Bold"
        await query.edit_message_text(show_config_text(c), reply_markup=config_menu(), parse_mode="Markdown")
        return

    if query.data == "watermark":
        c["watermark"] = "@mentedigna" if c["watermark"] != "@mentedigna" else "@mente_digna_"
        await query.edit_message_text(show_config_text(c), reply_markup=config_menu(), parse_mode="Markdown")
        return

    if query.data == "save_layout":
        try:
            layouts = json.loads(LAYOUT_FILE.read_text("utf-8")) if LAYOUT_FILE.exists() else {}
        except Exception:
            layouts = {}
        layouts[str(uid)] = c
        LAYOUT_FILE.write_text(json.dumps(layouts, ensure_ascii=False, indent=2), encoding="utf-8")
        await query.edit_message_text("💾 Layout Mente Digna salvo.", reply_markup=config_menu())
        return

    if query.data == "layouts":
        await query.edit_message_text(
            "📂 Seu layout salvo está disponível automaticamente neste bot.\n"
            "Ao reiniciar, você pode carregá-lo no código/configuração.",
            reply_markup=config_menu()
        )
        return

    if query.data == "edit":
        await query.edit_message_text(
            "✏️ Envie agora o texto corrigido.\n\n"
            "Depois eu mostro novamente o botão *GERAR CARD*.",
            parse_mode="Markdown"
        )
        context.user_data["waiting_edit"] = True
        return

    if query.data == "generate":
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
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📝 GERAR LEGENDA", callback_data="caption")]
                ])
            )
        except Exception as e:
            await query.message.reply_text(f"Erro ao gerar o card: {e}")
        return

    if query.data == "caption":
        text = last_card_text.get(uid) or pending_text.get(uid)
        if not text:
            await query.edit_message_text("Gere um card ou envie uma frase primeiro.")
            return
        await query.edit_message_text("Gerando legenda... ✍️")
        try:
            response = client.responses.create(
                model=MODEL,
                instructions=(
                    "Crie uma legenda curta para Instagram baseada na frase enviada. "
                    "Escreva em português do Brasil, com tom reflexivo e natural. "
                    "Não repita a frase integralmente. Não use hashtags em excesso."
                ),
                input=text
            )
            await query.message.reply_text(
                response.output_text.strip(),
                reply_markup=main_menu()
            )
        except Exception as e:
            await query.message.reply_text(f"Erro ao gerar legenda: {e}")

async def edited_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    if not context.user_data.get("waiting_edit"):
        return
    uid = update.effective_user.id
    pending_text[uid] = update.message.text.strip()
    context.user_data["waiting_edit"] = False
    await update.message.reply_text(
        f"📄 *Texto atualizado:*\n\n{pending_text[uid]}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ GERAR CARD", callback_data="generate")],
            [InlineKeyboardButton("✏️ EDITAR NOVAMENTE", callback_data="edit")],
        ]),
        parse_mode="Markdown"
    )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("config", config_cmd))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, edited_text))
    app.run_polling()

if __name__ == "__main__":
    main()
