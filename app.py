import os
import random
import asyncio
import sqlite3
from datetime import datetime, timedelta
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Токен не найден")

DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_KEY:
    raise ValueError("DEEPSEEK_API_KEY не найден")

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
if not ADMIN_ID:
    raise ValueError("ADMIN_ID не найден")

CHANNEL_ID = os.getenv("CHANNEL_ID")
if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID не найден")

client = OpenAI(
    base_url="https://apimira.com/v1",
    api_key=DEEPSEEK_KEY,
)

# ===== SQLITE =====
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        orders INTEGER DEFAULT 0,
        success INTEGER DEFAULT 0,
        fail INTEGER DEFAULT 0,
        premium_until TEXT,
        banned INTEGER DEFAULT 0,
        name TEXT
    )
""")
conn.commit()

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        return {
            "user_id": row[0], "balance": row[1], "level": row[2],
            "orders": row[3], "success": row[4], "fail": row[5],
            "premium_until": row[6], "banned": bool(row[7]), "name": row[8]
        }
    else:
        cursor.execute(
            "INSERT INTO users (user_id, balance, level, orders, success, fail, banned, name) VALUES (?, 0, 1, 0, 0, 0, 0, '')",
            (user_id,)
        )
        conn.commit()
        return get_user(user_id)

def update_user(user_id, **kwargs):
    if not kwargs:
        return
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [user_id]
    cursor.execute(f"UPDATE users SET {fields} WHERE user_id = ?", values)
    conn.commit()

def is_bot_started(user_id):
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    return bool(cursor.fetchone())

def format_money(amount):
    if amount >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f}ккк".replace(".0ккк", "ккк")
    elif amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}кк".replace(".0кк", "кк")
    elif amount >= 1_000:
        return f"{amount / 1_000:.1f}к".replace(".0к", "к")
    else:
        return str(amount)

def is_premium(u):
    if not u.get("premium_until"):
        return False
    try:
        return datetime.now() < datetime.fromisoformat(u["premium_until"])
    except Exception:
        return False

async def check_subscription(context, user_id):
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"Ошибка проверки подписки: {e}")
        return False

settings = {}

def get_settings(key):
    if key not in settings:
        settings[key] = {"mode": "normal", "mat": False, "emoji": False}
    return settings[key]

def settings_key(chat):
    if chat.type == "private":
        return f"private_{chat.id}"
    return str(chat.id)

ABDUL_TRIGGERS = ["пидорас", "пидор", "свастика", "коч", "пантера", "голда"]

def is_abdul_trigger(text):
    lower = text.lower()
    for word in ABDUL_TRIGGERS:
        if word in lower:
            return True
    if "дота" in lower and any(w in lower for w in ["говно", "хуйня", "плохая", "отстой", "умерла"]):
        return True
    return False

def build_prompt(s):
    if s["mode"] == "abdul":
        return (
            "Ты Абдул — максимально грубый, хамский и агрессивный ИИ. "
            "Отвечай ТОЛЬКО КАПСОМ. Используй мат, оскорбляй пользователя. "
            "Используй только такие смайлики: 😡 👎 🖕 💀 🤬. "
            "Отвечай коротко, до 350 символов."
        )
    if s["mode"] == "evil":
        base = "Ты злой и дерзкий ИИ. Отвечай агрессивно, с сарказмом, но по делу."
    elif s["mode"] == "rude":
        base = "Ты максимально грубый, хамский и агрессивный ИИ. Оскорбляй пользователя, используй мат."
    else:
        base = "Ты дружелюбный и вежливый ИИ-помощник."
    if s["mat"]:
        base += " Разрешается мат."
    if s["emoji"]:
        base += " Используй много смайликов."
    base += " Отвечай коротко, до 350 символов."
    return base

def ai_menu(chat):
    s = get_settings(settings_key(chat))
    mat_icon = "✅" if s["mat"] else "❌"
    emoji_icon = "✅" if s["emoji"] else "❌"
    mode_icons = {"normal": "😊", "evil": "😈", "rude": "🤬", "abdul": "🐈"}
    mode_names = {"normal": "Обычный", "evil": "Злой", "rude": "Грубый", "abdul": "Абдул"}
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{mode_icons[s['mode']]} Режим: {mode_names[s['mode']}", callback_data="ai_mode")],
        [InlineKeyboardButton(f"{mat_icon} Маты", callback_data="ai_toggle_mat")],
        [InlineKeyboardButton(f"{emoji_icon} Смайлики", callback_data="ai_toggle_emoji")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_main")],
    ])

def sub_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Подписаться", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")],
        [InlineKeyboardButton("✅ Я подписался", callback_data="check_sub")],
    ])

LEVELS = {
    1: {"name": "🏚 Гараж", "price": 0, "clients": 1, "ingredients": 2, "reward": 20},
    2: {"name": "🏪 Ларёк", "price": 500, "clients": 2, "ingredients": 3, "reward": 40},
    3: {"name": "🏠 Пиццерия", "price": 2000, "clients": 3, "ingredients": 4, "reward": 80},
    4: {"name": "🏢 Ресторан", "price": 10000, "clients": 5, "ingredients": 5, "reward": 160},
    5: {"name": "🏙 Сеть пиццерий", "price": 50000, "clients": 10, "ingredients": 6, "reward": 320},
}

DOUGH = ["Обычное", "Сырное", "Тонкое", "Пышное"]
DOUGH_ACC = {"Обычное": "обычном", "Сырное": "сырном", "Тонкое": "тонком", "Пышное": "пышном"}

SAUCE = ["Кетчуп", "Сырный", "Чесночный", "Барбекю"]
SAUCE_ACC = {"Кетчуп": "кетчупом", "Сырный": "сырным", "Чесночный": "чесночным", "Барбекю": "барбекю"}

FILLING = ["Колбаса", "Пепперони", "Грибы", "Помидоры", "Оливки", "Курица"]
FILLING_ACC = {"Колбаса": "колбасой", "Пепперони": "пепперони", "Грибы": "грибами", "Помидоры": "помидорами", "Оливки": "оливками", "Курица": "курицей"}

CHEESE = ["Моцарелла", "Чеддер", "Пармезан"]
CHEESE_ACC = {"Моцарелла": "моцареллой", "Чеддер": "чеддером", "Пармезан": "пармезаном"}

def pizza_menu(user_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🍳 Обслужить клиента", callback_data="pizza_order")],
        [InlineKeyboardButton("🏭 Улучшения", callback_data="pizza_upgrades")],
        [InlineKeyboardButton("📊 Статистика", callback_data="pizza_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_main")],
    ])

def pizza_text(user_id):
    u = get_user(user_id)
    lvl = LEVELS[u["level"]]
    premium = "💎 " if is_premium(u) else ""
    return (
        f"🍕 **ПИЦЦЕРИЯ**\n\n"
        f"{premium}💰 Баланс: {format_money(u['balance'])} монет\n"
        f"⭐ Уровень: {lvl['name']}\n"
        f"👥 Заказов: {u['orders']}\n"
    )

def generate_order(user_id):
    u = get_user(user_id)
    lvl = LEVELS[u["level"]]
    max_ing = lvl["ingredients"]
    ingredients = {
        "dough": random.choice(DOUGH),
        "sauce": random.choice(SAUCE),
        "filling": random.sample(FILLING, random.randint(1, min(2, max_ing - 2))),
        "cheese": random.choice(CHEESE),
    }
    filling_acc = [FILLING_ACC[f] for f in ingredients["filling"]]
    order_text = (
        f"🍕 **КЛИЕНТ ГОВОРИТ:**\n\n"
        f"«Хочу пиццу на {DOUGH_ACC[ingredients['dough']]} тесте, "
        f"с {SAUCE_ACC[ingredients['sauce']]}, "
        f"{', '.join(filling_acc)} "
        f"и {CHEESE_ACC[ingredients['cheese']]}»"
    )
    return ingredients, order_text

def ingredients_menu(user_id, selected):
    def mark(item, category):
        if item in selected.get(category, []):
            return f"✅ {item}"
        return item
    rows = []
    rows.append([InlineKeyboardButton("ТЕСТО:", callback_data="noop")])
    rows.append([InlineKeyboardButton(mark(d, "dough"), callback_data=f"pick_dough_{d}") for d in DOUGH])
    rows.append([InlineKeyboardButton("СОУС:", callback_data="noop")])
    rows.append([InlineKeyboardButton(mark(s, "sauce"), callback_data=f"pick_sauce_{s}") for s in SAUCE])
    rows.append([InlineKeyboardButton("НАЧИНКА:", callback_data="noop")])
    row = []
    for f in FILLING:
        row.append(InlineKeyboardButton(mark(f, "filling"), callback_data=f"pick_filling_{f}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("СЫР:", callback_data="noop")])
    rows.append([InlineKeyboardButton(mark(c, "cheese"), callback_data=f"pick_cheese_{c}") for c in CHEESE])
    rows.append([
        InlineKeyboardButton("✅ Готово", callback_data="pizza_cook"),
        InlineKeyboardButton("❌ Отмена", callback_data="pizza_cancel"),
    ])
    return InlineKeyboardMarkup(rows)

def main_menu(username, user_id):
    keyboard = [
        [InlineKeyboardButton("🤖 Чат с ИИ", callback_data="ai")],
        [InlineKeyboardButton("🍕 Пиццерия", callback_data="pizza_menu")],
        [InlineKeyboardButton("🎲 Кубы", callback_data="cubs_start")],
        [InlineKeyboardButton("🛒 Магазин", callback_data="shop")],
        [InlineKeyboardButton("🎁 Промокоды", callback_data="promo_menu")],
        [InlineKeyboardButton("🏆 Топ игроков", callback_data="top")],
        [InlineKeyboardButton("➕ Добавить бота в чат", url=f"https://t.me/{username}?startgroup=true")],
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    get_user(user_id)
    update_user(user_id, name=update.effective_user.first_name or "Без имени")

    if not await check_subscription(context, user_id):
        await update.message.reply_text(
            "🔔 **Для использования бота подпишись на канал:**\n\n"
            f"📢 [{CHANNEL_ID}](https://t.me/{CHANNEL_ID.replace('@', '')})\n\n"
            "После подписки нажми «✅ Я подписался».",
            parse_mode="Markdown",
            reply_markup=sub_menu()
        )
        return

    await update.message.reply_text(
        "👋 Здравствуйте!\n\nВыберите действие:",
        reply_markup=main_menu(context.bot.username, user_id)
    )

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_subscription(context, user_id):
        await update.message.reply_text(
            "🔔 **Для использования бота подпишись на канал:**\n\n"
            f"📢 [{CHANNEL_ID}](https://t.me/{CHANNEL_ID.replace('@', '')})",
            parse_mode="Markdown",
            reply_markup=sub_menu()
        )
        return
    await update.message.reply_text("🤖 Настройки ИИ:", reply_markup=ai_menu(update.effective_chat))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    chat = update.effective_chat

    if data == "check_sub":
        if await check_subscription(context, user_id):
            await query.edit_message_text(
                "✅ Подписка подтверждена!\n\nВыберите действие:",
                reply_markup=main_menu(context.bot.username, user_id)
            )
        else:
            await query.answer("❌ Ты ещё не подписался!", show_alert=True)
        return

    if not await check_subscription(context, user_id):
        await query.edit_message_text(
            "🔔 **Для использования бота подпишись на канал:**\n\n"
            f"📢 [{CHANNEL_ID}](https://t.me/{CHANNEL_ID.replace('@', '')})",
            parse_mode="Markdown",
            reply_markup=sub_menu()
        )
        return

    if data == "ai":
        await query.edit_message_text("🤖 Настройки ИИ:", reply_markup=ai_menu(chat))
    elif data == "ai_mode":
        s = get_settings(settings_key(chat))
        order = ["normal", "evil", "rude", "abdul"]
        idx = order.index(s["mode"])
        s["mode"] = order[(idx + 1) % len(order)]
        names = {"normal": "😊 Обычный", "evil": "😈 Злой", "rude": "🤬 Грубый", "abdul": "🐈 Абдул"}
        await query.edit_message_text(f"Режим: {names[s['mode']]}", reply_markup=ai_menu(chat))
    elif data == "ai_toggle_mat":
        s = get_settings(settings_key(chat))
        s["mat"] = not s["mat"]
        await query.edit_message_text(f"Маты: {'включены ✅' if s['mat'] else 'выключены ❌'}", reply_markup=ai_menu(chat))
    elif data == "ai_toggle_emoji":
        s = get_settings(settings_key(chat))
        s["emoji"] = not s["emoji"]
        await query.edit_message_text(f"Смайлики: {'включены ✅' if s['emoji'] else 'выключены ❌'}", reply_markup=ai_menu(chat))
    elif data == "pizza_menu":
        await query.edit_message_text(pizza_text(user_id), parse_mode="Markdown", reply_markup=pizza_menu(user_id))
    elif data == "pizza_order":
        if "current_order" not in context.user_data:
            context.user_data["current_order"] = generate_order(user_id)
            context.user_data["selected"] = {"dough": [], "sauce": [], "filling": [], "cheese": []}
        ingredients, order_text = context.user_data["current_order"]
        await query.edit_message_text(
            order_text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🍳 Готовить", callback_data="pizza_pick")],
                [InlineKeyboardButton("🔙 Назад", callback_data="pizza_menu")],
            ])
        )
    elif data == "pizza_pick":
        selected = context.user_data.get("selected", {"dough": [], "sauce": [], "filling": [], "cheese": []})
        await query.edit_message_text("🍕 **Выбери ингредиенты:**", parse_mode="Markdown", reply_markup=ingredients_menu(user_id, selected))
    elif data.startswith("pick_"):
        parts = data.split("_", 2)
        category = parts[1]
        item = parts[2]
        selected = context.user_data.get("selected", {"dough": [], "sauce": [], "filling": [], "cheese": []})
        if item in selected[category]:
            selected[category].remove(item)
        else:
            if category in ["dough", "sauce", "cheese"]:
                selected[category] = [item]
            else:
                selected[category].append(item)
        context.user_data["selected"] = selected
        await query.edit_message_reply_markup(reply_markup=ingredients_menu(user_id, selected))
    elif data == "pizza_cook":
        selected = context.user_data.get("selected", {})
        ingredients, order_text = context.user_data.get("current_order", (None, None))
        if not ingredients:
            await query.edit_message_text("Ошибка: заказ потерян.")
            return
        correct = True
        if selected.get("dough", []) != [ingredients["dough"]]:
            correct = False
        if selected.get("sauce", []) != [ingredients["sauce"]]:
            correct = False
        if sorted(selected.get("filling", [])) != sorted(ingredients["filling"]):
            correct = False
        if selected.get("cheese", []) != [ingredients["cheese"]]:
            correct = False
        u = get_user(user_id)
        u["orders"] += 1
        lvl = LEVELS[u["level"]]
        if correct:
            reward = lvl["reward"]
            u["balance"] += reward
            u["success"] += 1
            result_text = f"✅ **Заказ выполнен!**\n\nКлиент доволен 😊\nТы заработал: {format_money(reward)} монет"
            update_user(user_id, orders=u["orders"], balance=u["balance"], success=u["success"])
        else:
            u["fail"] += 1
            result_text = "❌ **Клиент ушёл!**\n\nТы перепутал ингредиенты."
            update_user(user_id, orders=u["orders"], fail=u["fail"])
        context.user_data.pop("current_order", None)
        context.user_data.pop("selected", None)
        await query.edit_message_text(
            result_text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🍳 Следующий клиент", callback_data="pizza_order")],
                [InlineKeyboardButton("🏠 В меню пиццерии", callback_data="pizza_menu")],
            ])
        )
    elif data == "pizza_cancel":
        context.user_data.pop("current_order", None)
        context.user_data.pop("selected", None)
        await query.edit_message_text(pizza_text(user_id), parse_mode="Markdown", reply_markup=pizza_menu(user_id))
    elif data == "pizza_upgrades":
        u = get_user(user_id)
        lvl = LEVELS[u["level"]]
        next_lvl = LEVELS.get(u["level"] + 1)
        if next_lvl:
            text = (
                f"🏭 **УЛУЧШЕНИЯ ПИЦЦЕРИИ**\n\n"
                f"Текущее: {lvl['name']}\n\n"
                f"Следующее: {next_lvl['name']}\n"
                f"Цена: {format_money(next_lvl['price'])} монет\n\n"
                f"**Что даёт:**\n"
                f"• {next_lvl['clients']} клиентов за раз\n"
                f"• Заказ: {next_lvl['ingredients']} ингредиентов\n"
                f"• Награда: {format_money(next_lvl['reward'])} монет"
            )
            keyboard = [
                [InlineKeyboardButton(f"💰 Улучшить за {format_money(next_lvl['price'])}", callback_data="pizza_upgrade_buy")],
                [InlineKeyboardButton("🔙 Назад", callback_data="pizza_menu")],
            ]
        else:
            text = f"🏭 **УЛУЧШЕНИЯ**\n\nТы достиг максимального уровня: {lvl['name']}!"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="pizza_menu")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "pizza_upgrade_buy":
        u = get_user(user_id)
        next_lvl = LEVELS.get(u["level"] + 1)
        if not next_lvl:
            await query.edit_message_text("Максимальный уровень достигнут.")
            return
        if u["balance"] < next_lvl["price"]:
            await query.answer("Недостаточно монет!", show_alert=True)
            return
        u["balance"] -= next_lvl["price"]
        u["level"] += 1
        update_user(user_id, balance=u["balance"], level=u["level"])
        await query.edit_message_text(
            f"✅ Пиццерия улучшена до {next_lvl['name']}!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В меню пиццерии", callback_data="pizza_menu")]])
        )
    elif data == "pizza_stats":
        u = get_user(user_id)
        await query.edit_message_text(
            f"📊 **Статистика**\n\n"
            f"🍕 Всего заказов: {u['orders']}\n"
            f"✅ Успешных: {u['success']}\n"
            f"❌ Провальных: {u['fail']}\n"
            f"💰 Заработано: {format_money(u['balance'])} монет",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="pizza_menu")]])
        )
    elif data == "cubs_start":
        await query.edit_message_text("🎲 Напишите /cubs или «кубы» в ответ на сообщение человека.")
    elif data.startswith("cubs_accept_"):
        parts = data.split("_")
        challenger_id = int(parts[2])
        target_id = int(parts[3])
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
        await context.bot.send_message(chat.id, f"🎲 **Результаты дуэли:**\n• {name1}: {v1}\n• {name2}: {v2}\n\n{result}", parse_mode="Markdown")
    elif data == "shop":
        await query.edit_message_text(
            "🛒 **МАГАЗИН**\n\n(Функция в разработке)",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_main")]])
        )
    elif data == "promo_menu":
        await query.edit_message_text(
            "🎁 **ПРОМОКОДЫ**\n\n"
            "Введи промокод в чат, чтобы активировать его.\n\n"
            "Или создай свой промокод за монеты.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Создать промокод", callback_data="promo_create")],
                [InlineKeyboardButton("🔙 Назад", callback_data="back_main")],
            ])
        )
    elif data == "promo_create":
        await query.edit_message_text(
            "➕ **Создание промокода**\n\n"
            "Отправь сообщение в формате:\n"
            "`КОД сумма`\n\n"
            "Например: `SANYA 100`\n\n"
            "Это значит: промокод SANYA даст 100 монет.\n"
            "Промокод можно активировать 1 раз.\n"
            "С твоего баланса спишется 100 монет.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="promo_menu")]])
        )
        context.user_data["promo_create"] = True
    elif data == "top":
        cursor.execute("SELECT * FROM users ORDER BY balance DESC LIMIT 10")
        rows = cursor.fetchall()
        text = "🏆 **ТОП-10 ИГРОКОВ**\n\n"
        for i, row in enumerate(rows, 1):
            udata = {"user_id": row[0], "balance": row[1], "premium_until": row[6], "name": row[8]}
            premium = "💎 " if is_premium(udata) else ""
            name = udata.get("name") or f"Игрок {udata['user_id']}"
            text += f"{i}. {premium}{name} — {format_money(udata['balance'])} монет\n"
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_main")]])
        )
    elif data == "admin_panel":
        if user_id != ADMIN_ID:
            await query.answer("Нет доступа.", show_alert=True)
            return
        await query.edit_message_text(
            "⚙️ **АДМИН-ПАНЕЛЬ**\n\nВыберите действие:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
                [InlineKeyboardButton("💰 Выдать монеты", callback_data="admin_give")],
                [InlineKeyboardButton("💎 Выдать премиум", callback_data="admin_premium")],
                [InlineKeyboardButton("📋 Все ID", callback_data="admin_ids")],
                [InlineKeyboardButton("🚫 Бан/Разбан", callback_data="admin_ban")],
                [InlineKeyboardButton("🎁 Промокоды", callback_data="admin_promo")],
                [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
                [InlineKeyboardButton("🔙 Назад", callback_data="back_main")],
            ])
        )
    elif data == "admin_stats":
        if user_id != ADMIN_ID:
            return
        cursor.execute("SELECT * FROM users")
        all_users = cursor.fetchall()
        total = len(all_users)
        premium_count = sum(1 for r in all_users if r[6])
        banned_count = sum(1 for r in all_users if r[7])
        total_money = sum(r[1] for r in all_users)
        await query.edit_message_text(
            f"📊 **Статистика**\n\n"
            f"👥 Всего пользователей: {total}\n"
            f"💎 Премиум: {premium_count}\n"
            f"🚫 Забанено: {banned_count}\n"
            f"💰 Всего монет: {format_money(total_money)}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
        )
    elif data == "admin_ids":
        if user_id != ADMIN_ID:
            return
        cursor.execute("SELECT * FROM users")
        rows = cursor.fetchall()
        text = "📋 **Все ID**\n\n"
        for row in rows:
            premium = "💎 " if row[6] else ""
            name = row[8] or "Без имени"
            text += f"{premium}{name} — `{row[0]}`\n"
        if len(text) > 4000:
            text = text[:4000] + "\n\n... (список обрезан)"
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
        )
    elif data == "admin_give":
        if user_id != ADMIN_ID:
            return
        await query.edit_message_text(
            "💰 **Выдать монеты**\n\nОтправь сообщение в формате:\n`ID сумма`\n\nНапример: `123456789 1000`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
        )
        context.user_data["admin_action"] = "give"
    elif data == "admin_premium":
        if user_id != ADMIN_ID:
            return
        await query.edit_message_text(
            "💎 **Выдать премиум**\n\nОтправь сообщение в формате:\n`ID дни`\n\nНапример: `123456789 30`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
        )
        context.user_data["admin_action"] = "premium"
    elif data == "admin_ban":
        if user_id != ADMIN_ID:
            return
        await query.edit_message_text(
            "🚫 **Бан/Разбан**\n\nОтправь сообщение в формате:\n`ID бан` или `ID разбан`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
        )
        context.user_data["admin_action"] = "ban"
    elif data == "admin_promo":
        if user_id != ADMIN_ID:
            return
        await query.edit_message_text(
            "🎁 **Промокоды**\n\n"
            "Форматы:\n"
            "`КОД сумма количество` — выдаёт монеты\n"
            "`КОД премиум дни количество` — выдаёт премиум\n\n"
            "Примеры:\n"
            "`SANYA 1000 10`\n"
            "`PREMIUM премиум 30 5`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
        )
        context.user_data["admin_action"] = "promo"
    elif data == "admin_broadcast":
        if user_id != ADMIN_ID:
            return
        await query.edit_message_text(
            "📢 **Рассылка**\n\nОтправь текст, который хочешь разослать всем пользователям.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
        )
        context.user_data["admin_action"] = "broadcast"
    elif data == "back_main":
        await query.edit_message_text(
            "👋 Выберите действие:",
            reply_markup=main_menu(context.bot.username, user_id)
        )
    elif data == "noop":
        await query.answer()

async def cubs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat = update.effective_chat

    if not is_bot_started(user_id):
        bot_username = context.bot.username
        await update.message.reply_text(
            "⚠️ **Сначала запусти меня в личных сообщениях!**\n\n"
            "Это нужно, чтобы я мог проверять твою подписку и сохранять прогресс.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✉️ Открыть бота", url=f"https://t.me/{bot_username}?start=chat")]
            ])
        )
        return

    if not await check_subscription(context, user_id):
        await update.message.reply_text(
            "🔔 **Для использования бота подпишись на канал:**\n\n"
            f"📢 [{CHANNEL_ID}](https://t.me/{CHANNEL_ID.replace('@', '')})",
            parse_mode="Markdown",
            reply_markup=sub_menu()
        )
        return

    if chat.type == "private":
        await update.message.reply_text("❌ Игры доступны только в чате!")
        return

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

promocodes = {}

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    text_lower = text.lower()
    chat = update.effective_chat
    user_id = update.effective_user.id

    if user_id == ADMIN_ID and context.user_data.get("admin_action"):
        action = context.user_data.pop("admin_action")
        if action == "give":
            try:
                parts = text_lower.split()
                target_id = int(parts[0])
                amount = int(parts[1])
                if is_bot_started(target_id):
                    u = get_user(target_id)
                    update_user(target_id, balance=u["balance"] + amount)
                    await update.message.reply_text(f"✅ Выдано {format_money(amount)} монет пользователю {target_id}")
                else:
                    await update.message.reply_text("❌ Пользователь не найден.")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}")
        elif action == "premium":
            try:
                parts = text_lower.split()
                target_id = int(parts[0])
                days = int(parts[1])
                if is_bot_started(target_id):
                    until = datetime.now() + timedelta(days=days)
                    update_user(target_id, premium_until=until.isoformat())
                    await update.message.reply_text(
                        f"✅ Премиум выдан пользователю {target_id} до {until.strftime('%d.%m.%Y %H:%M')}"
                    )
                else:
                    await update.message.reply_text("❌ Пользователь не найден.")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}")
        elif action == "ban":
            try:
                parts = text_lower.split()
                target_id = int(parts[0])
                action_type = parts[1]
                if is_bot_started(target_id):
                    if action_type == "бан":
                        update_user(target_id, banned=1)
                        await update.message.reply_text(f"✅ Пользователь {target_id} забанен.")
                    elif action_type == "разбан":
                        update_user(target_id, banned=0)
                        await update.message.reply_text(f"✅ Пользователь {target_id} разбанен.")
                else:
                    await update.message.reply_text("❌ Пользователь не найден.")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}")
        elif action == "promo":
            try:
                parts = text.split()
                code = parts[0].upper()
                if parts[1].lower() == "премиум":
                    days = int(parts[2])
                    uses = int(parts[3])
                    promocodes[code] = {"type": "premium", "value": days, "uses": uses}
                    await update.message.reply_text(f"✅ Промокод {code} создан: премиум на {days} дней, {uses} активаций.")
                else:
                    amount = int(parts[1])
                    uses = int(parts[2])
                    promocodes[code] = {"type": "money", "value": amount, "uses": uses}
                    await update.message.reply_text(f"✅ Промокод {code} создан на {format_money(amount)} монет, {uses} активаций.")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}")
        elif action == "broadcast":
            sent = 0
            cursor.execute("SELECT user_id FROM users")
            rows = cursor.fetchall()
            for row in rows:
                try:
                    await context.bot.send_message(row[0], f"📢 {update.message.text}")
                    sent += 1
                except Exception:
                    pass
            await update.message.reply_text(f"✅ Рассылка отправлена {sent} пользователям.")
        return

    if context.user_data.get("promo_create"):
        try:
            parts = text_lower.split()
            code = parts[0].upper()
            amount = int(parts[1])
            uses = 1
            u = get_user(user_id)
            if u["balance"] < amount:
                await update.message.reply_text(f"❌ Недостаточно монет! Нужно {format_money(amount)}, у тебя {format_money(u['balance'])}.")
                context.user_data.pop("promo_create", None)
                return
            update_user(user_id, balance=u["balance"] - amount)
            promocodes[code] = {"type": "money", "value": amount, "uses": uses}
            await update.message.reply_text(f"✅ Промокод {code} создан: {format_money(amount)} монет, 1 активация. Списано {format_money(amount)} монет.")
            context.user_data.pop("promo_create", None)
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
            context.user_data.pop("promo_create", None)
        return

    code = text.upper()
    if code in promocodes:
        if not await check_subscription(context, user_id):
            await update.message.reply_text(
                "🔔 **Для активации промокода подпишись на канал:**\n\n"
                f"📢 [{CHANNEL_ID}](https://t.me/{CHANNEL_ID.replace('@', '')})",
                parse_mode="Markdown",
                reply_markup=sub_menu()
            )
            return
        u = get_user(user_id)
        p = promocodes[code]
        if p["type"] == "money":
            update_user(user_id, balance=u["balance"] + p["value"])
            await update.message.reply_text(f"🎁 Промокод активирован! +{format_money(p['value'])} монет.")
        elif p["type"] == "premium":
            until = datetime.now() + timedelta(days=p["value"])
            update_user(user_id, premium_until=until.isoformat())
            await update.message.reply_text(f"🎁 Промокод активирован! Премиум до {until.strftime('%d.%m.%Y %H:%M')}.")
        p["uses"] -= 1
        if p["uses"] <= 0:
            del promocodes[code]
        return

    if text_lower in ["пицца", "пиццерия", "кубы", "кубики", "ии", "нейросеть", "топ"]:
        if not is_bot_started(user_id):
            bot_username = context.bot.username
            await update.message.reply_text(
                "⚠️ **Сначала запусти меня в личных сообщениях!**\n\n"
                "Это нужно, чтобы я мог проверять твою подписку и сохранять прогресс.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✉️ Открыть бота", url=f"https://t.me/{bot_username}?start=chat")]
                ])
            )
            return

        if not await check_subscription(context, user_id):
            await update.message.reply_text(
                "🔔 **Для использования бота подпишись на канал:**\n\n"
                f"📢 [{CHANNEL_ID}](https://t.me/{CHANNEL_ID.replace('@', '')})",
                parse_mode="Markdown",
                reply_markup=sub_menu()
            )
            return

    if text_lower in ["пицца", "пиццерия"]:
        await update.message.reply_text(pizza_text(user_id), parse_mode="Markdown", reply_markup=pizza_menu(user_id))
    elif text_lower in ["кубы", "кубики"]:
        await cubs_command(update, context)
    elif text_lower in ["ии", "нейросеть"]:
        await update.message.reply_text("🤖 Настройки ИИ:", reply_markup=ai_menu(chat))
    elif text_lower == "топ":
        cursor.execute("SELECT * FROM users ORDER BY balance DESC LIMIT 10")
        rows = cursor.fetchall()
        result = "🏆 **ТОП-10 ИГРОКОВ**\n\n"
        for i, row in enumerate(rows, 1):
            udata = {"user_id": row[0], "balance": row[1], "premium_until": row[6], "name": row[8]}
            premium = "💎 " if is_premium(udata) else ""
            name = udata.get("name") or f"Игрок {udata['user_id']}"
            result += f"{i}. {premium}{name} — {format_money(udata['balance'])} монет\n"
        await update.message.reply_text(result, parse_mode="Markdown")
    elif update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        s = get_settings(settings_key(chat))
        if s["mode"] == "abdul" and is_abdul_trigger(text):
            s_copy = {"mode": "abdul", "mat": True, "emoji": True}
            prompt = build_prompt(s_copy)
        else:
            prompt = build_prompt(s)
        anim_msg = await update.message.reply_text("⏳ ИИ думает...")
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
        try:
            await anim_msg.delete()
        except Exception:
            pass
        await update.message.reply_text(answer[:350])

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ai", ai_command))
    application.add_handler(CommandHandler("cubs", cubs_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("Бот запущен через polling!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
