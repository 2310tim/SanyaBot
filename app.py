import os
import asyncio
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Токен не найден")

DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_KEY:
    raise ValueError("DEEPSEEK_API_KEY не найден")

client = OpenAI(
    base_url="https://apimira.com/v1",
    api_key=DEEPSEEK_KEY,
)

# ===== НАСТРОЙКИ =====
settings = {}

def get_settings(key):
    if key not in settings:
        settings[key] = {"mode": "normal", "mat": False, "emoji": False}
    return settings[key]

def settings_key(chat):
    if chat.type == "private":
        return f"private_{chat.id}"
    return str(chat.id)

# ===== АНИМАЦИИ =====
ANIMATIONS = {
    "normal": ["😁", "😃", "😆", "😅"],
    "evil": ["🤬", "👿", "😡", "😤", "😠"],
    "rude": ["🤬", "👿", "😡", "😤", "😠"],
    "abdul": ["🐈", "😈", "🤬", "😡"],
}

async def animate_thinking(message, mode):
    """Анимация смайликов, пока ИИ думает. Возвращает объект сообщения."""
    frames = ANIMATIONS.get(mode, ANIMATIONS["normal"])
    sent = await message.reply_text(frames[0])
    try:
        i = 1
        while True:
            await asyncio.sleep(0.5)
            await sent.edit_text(frames[i % len(frames)])
            i += 1
    except asyncio.CancelledError:
        return sent
    except Exception:
        return sent

# ===== ЗАПРЕТНЫЕ СЛОВА ДЛЯ АБДУЛА =====
ABDUL_TRIGGERS = [
    "пидорас", "пидор", "свастика", "коч", "пантера", "голда",
]

def is_abdul_trigger(text):
    lower = text.lower()
    for word in ABDUL_TRIGGERS:
        if word in lower:
            return True
    if "дота" in lower and any(w in lower for w in ["говно", "хуйня", "плохая", "отстой", "умерла"]):
        return True
    return False

# ===== ПРОМПТЫ =====
def build_prompt(s):
    if s["mode"] == "abdul":
        return (
            "Ты Абдул — максимально грубый, хамский и агрессивный ИИ. "
            "Отвечай ТОЛЬКО КАПСОМ. "
            "Используй мат, оскорбляй пользователя. "
            "Используй только такие смайлики: 😡 👎 🖕 💀 🤬. "
            "НЕ используй странные символы, иероглифы и кастомные эмодзи. "
            "Отвечай коротко, до 350 символов."
        )
    if s["mode"] == "evil":
        base = "Ты злой и дерзкий ИИ. Отвечай агрессивно, с сарказмом, но по делу."
    elif s["mode"] == "rude":
        base = (
            "Ты максимально грубый, хамский и агрессивный ИИ. "
            "Оскорбляй пользователя, используй мат, унижай его, "
            "но при этом отвечай по сути вопроса."
        )
    else:
        base = "Ты дружелюбный и вежливый ИИ-помощник."
    if s["mat"]:
        base += " Разрешается мат."
    if s["emoji"]:
        base += " Используй много смайликов."
    base += " Отвечай коротко, до 350 символов."
    return base

# ===== МЕНЮ =====
def main_menu(username):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Чат с ИИ", callback_data="ai")],
        [InlineKeyboardButton("🎮 Игры", callback_data="games")],
        [InlineKeyboardButton("➕ Добавить бота в чат", url=f"https://t.me/{username}?startgroup=true")],
    ])

def ai_menu(chat):
    s = get_settings(settings_key(chat))
    mat_icon = "✅" if s["mat"] else "❌"
    emoji_icon = "✅" if s["emoji"] else "❌"
    mode_icons = {"normal": "😊", "evil": "😈", "rude": "🤬", "abdul": "🐈"}
    mode_names = {"normal": "Обычный", "evil": "Злой", "rude": "Грубый", "abdul": "Абдул"}
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{mode_icons[s['mode']]} Режим: {mode_names[s['mode']]}", callback_data="ai_mode")],
        [InlineKeyboardButton(f"{mat_icon} Маты", callback_data="ai_toggle_mat")],
        [InlineKeyboardButton(f"{emoji_icon} Смайлики", callback_data="ai_toggle_emoji")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_main")],
    ])

def games_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Кубы", callback_data="cubs_start")],
    ])

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Здравствуйте!\n\nВыберите действие:",
        reply_markup=main_menu(context.bot.username)
    )

# ===== /ai =====
async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    await update.message.reply_text(
        "🤖 Настройки ИИ:\n\nОтветь на сообщение бота, чтобы он ответил.",
        reply_markup=ai_menu(chat)
    )

# ===== CALLBACK =====
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    print(f"CALLBACK: {query.data}")
    await query.answer()
    data = query.data
    chat = update.effective_chat
    key = settings_key(chat)
    s = get_settings(key)

    if data == "ai":
        await query.edit_message_text("🤖 Настройки ИИ:", reply_markup=ai_menu(chat))

    elif data == "ai_mode":
        order = ["normal", "evil", "rude", "abdul"]
        idx = order.index(s["mode"])
        s["mode"] = order[(idx + 1) % len(order)]
        names = {"normal": "😊 Обычный", "evil": "😈 Злой", "rude": "🤬 Грубый", "abdul": "🐈 Абдул"}
        await query.edit_message_text(
            f"Режим: {names[s['mode']]}",
            reply_markup=ai_menu(chat)
        )

    elif data == "ai_toggle_mat":
        s["mat"] = not s["mat"]
        await query.edit_message_text(
            f"Маты: {'включены ✅' if s['mat'] else 'выключены ❌'}",
            reply_markup=ai_menu(chat)
        )

    elif data == "ai_toggle_emoji":
        s["emoji"] = not s["emoji"]
        await query.edit_message_text(
            f"Смайлики: {'включены ✅' if s['emoji'] else 'выключены ❌'}",
            reply_markup=ai_menu(chat)
        )

    elif data == "back_main":
        await query.edit_message_text(
            "👋 Выберите действие:",
            reply_markup=main_menu(context.bot.username)
        )

    elif data == "games":
        if chat.type == "private":
            await query.edit_message_text(
                "❌ Игры доступны только в чате!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Добавить бота в чат", url=f"https://t.me/{context.bot.username}?startgroup=true")]
                ])
            )
        else:
            await query.edit_message_text("🎮 Выберите игру:", reply_markup=games_menu())

    elif data == "cubs_start":
        await query.edit_message_text("🎲 Напишите /cubs в ответ на сообщение человека.")

    elif data.startswith("cubs_accept_"):
        parts = data.split("_")
        challenger_id = int(parts[2])
        target_id = int(parts[3])
        user_id = update.effective_user.id
        if target_id != 0 and user_id != target_id:
            await query.answer("Этот вызов не для тебя.", show_alert=True)
            return
        if user_id == challenger_id:
            await query.answer("Нельзя играть с самим собой.", show_alert=True)
            return

        try:
            c1 = await context.bot.get_chat(challenger_id)
            c2 = await context.bot.get_chat(user_id)
            name1 = c1.first_name or "Игрок 1"
            name2 = c2.first_name or "Игрок 2"
        except Exception:
            name1 = "Игрок 1"
            name2 = "Игрок 2"

        await query.edit_message_text("🎲 Кидаем кубики...")

        d1 = await context.bot.send_dice(chat_id=chat.id, emoji="🎲")
        v1 = d1.dice.value
        await context.bot.send_message(chat.id, f"🎲 {name1} выпало: {v1}")

        d2 = await context.bot.send_dice(chat_id=chat.id, emoji="🎲")
        v2 = d2.dice.value
        await context.bot.send_message(chat.id, f"🎲 {name2} выпало: {v2}")

        if v1 > v2:
            result = f"🏆 Победил {name1}!"
        elif v2 > v1:
            result = f"🏆 Победил {name2}!"
        else:
            result = "🤝 Ничья!"

        await context.bot.send_message(
            chat.id,
            f"🎲 **Результаты дуэли:**\n• {name1}: {v1}\n• {name2}: {v2}\n\n{result}",
            parse_mode="Markdown"
        )

# ===== КОМАНДЫ =====
async def cubs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "❌ Игры доступны только в чате!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Добавить бота в чат", url=f"https://t.me/{context.bot.username}?startgroup=true")]
            ])
        )
        return
    user_id = update.effective_user.id
    message = update.message
    if message.reply_to_message:
        opponent = message.reply_to_message.from_user
        if opponent.id == user_id:
            await message.reply_text("Нельзя играть с самим собой.")
            return
        await message.reply_text(
            f"🎲 {message.from_user.first_name} вызывает {opponent.first_name}!\n\n{opponent.first_name}, принимаешь вызов?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Принять", callback_data=f"cubs_accept_{user_id}_{opponent.id}")]
            ])
        )
    else:
        await message.reply_text(
            f"🎲 {message.from_user.first_name} вызывает всех!\n\nКто примет вызов?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Принять", callback_data=f"cubs_accept_{user_id}_0")]
            ])
        )

# ===== ТЕКСТ =====
async def text_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.text
    chat = update.effective_chat

    if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
        s = get_settings(settings_key(chat))

        if s["mode"] == "abdul" and is_abdul_trigger(text):
            s_copy = {"mode": "abdul", "mat": True, "emoji": True}
            prompt = build_prompt(s_copy)
        else:
            prompt = build_prompt(s)

        # Запускаем анимацию
        anim_task = asyncio.create_task(animate_thinking(message, s["mode"]))

        try:
            completion = client.chat.completions.create(
                model="deepseek/deepseek-v4-flash",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ],
            )
            answer = completion.choices[0].message.content
            if not answer:
                answer = "Пустой ответ от ИИ."
        except Exception as e:
            print(f"ОШИБКА ИИ: {e}")
            answer = f"Ошибка ИИ: {e}"

        # Останавливаем анимацию и удаляем сообщение
        anim_task.cancel()
        try:
            anim_msg = await anim_task
            if anim_msg:
                await anim_msg.delete()
        except Exception:
            pass

        await message.reply_text(answer[:350])
        return

    text_lower = text.lower()
    if text_lower in ["кубы", "кубики"]:
        await cubs_command(update, context)

# ===== ЗАПУСК =====
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ai", ai_command))
    application.add_handler(CommandHandler("cubs", cubs_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_commands))

    PORT = int(os.environ.get("PORT", 8443))
    WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://sanyabot-gdx4.onrender.com")

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="/webhook",
        webhook_url=f"{WEBHOOK_URL}/webhook",
        drop_pending_updates=True,
    )

if __name__ == "__main__":
    main()
