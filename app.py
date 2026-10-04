import os
import random
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

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
if not ADMIN_ID:
    raise ValueError("ADMIN_ID не найден")

client = OpenAI(
    base_url="https://apimira.com/v1",
    api_key=DEEPSEEK_KEY,
)

# ===== ФОРМАТИРОВАНИЕ =====
def format_money(amount):
    if amount >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f}ккк".replace(".0ккк", "ккк")
    elif amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}кк".replace(".0кк", "кк")
    elif amount >= 1_000:
        return f"{amount / 1_000:.1f}к".replace(".0к", "к")
    else:
        return str(amount)

# ===== НАСТРОЙКИ ИИ =====
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
        [InlineKeyboardButton(f"{mode_icons[s['mode']]} Режим: {mode_names[s['mode']]}", callback_data="ai_mode")],
        [InlineKeyboardButton(f"{mat_icon} Маты", callback_data="ai_toggle_mat")],
        [InlineKeyboardButton(f"{emoji_icon} Смайлики", callback_data="ai_toggle_emoji")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_main")],
    ])

# ===== ПИЦЦЕРИЯ =====
users = {}

def get_user(user_id):
    if user_id not in users:
        users[user_id] = {
            "balance": 0, "level": 1, "orders": 0, "success": 0, "fail": 0,
            "premium": False, "banned": False, "name": ""
        }
    return users[user_id]

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
    premium = "💎 " if u["premium"] else ""
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
        [InlineKeyboardButton("🏆 Топ игроков", callback_data="top")],
        [InlineKeyboardButton("➕ Добавить бота в чат", url=f"https://t.me/{username}?startgroup=true")],
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    u["name"] = update.effective_user.first_name or "Без имени"
    await update.message.reply_text(
        "👋 Здравствуйте!\n\nВыберите действие:",
        reply_markup=main_menu(context.bot.username, user_id)
    )

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Настройки ИИ:", reply_markup=ai_menu(update.effective_chat))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    chat = update.effective_chat
    u = get_user(user_id)

    # ---- ИИ ----
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

    # ---- ПИЦЦЕРИЯ ----
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
        u["orders"] += 1
        lvl = LEVELS[u["level"]]
        if correct:
            reward = lvl["reward"]
            u["balance"] += reward
            u["success"] += 1
            result_text = f"✅ **Заказ выполнен!**\n\nКлиент доволен 😊\nТы заработал: {format_money(reward)} монет"
        else:
            u["fail"] += 1
            result_text = "❌ **Клиент ушёл!**\n\nТы перепутал ингредиенты."
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

    # ---- КУБЫ ----
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

    # ---- МАГАЗИН ----
    elif data == "shop":
        await query.edit_message_text(
            "🛒 **МАГАЗИН**\n\n(Функция в разработке)",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_main")]])
        )

    # ---- ТОП ИГРОКОВ ----
    elif data == "top":
        sorted_users = sorted(users.items(), key=lambda x: x[1]["balance"], reverse=True)[:10]
        text = "🏆 **ТОП-10 ИГРОКОВ**\n\n"
        for i, (uid, udata) in enumerate(sorted_users, 1):
            premium = "💎 " if udata.get("premium") else ""
            name = udata.get("name") or f"Игрок {uid}"
            text += f"{i}. {premium}{name} — {format_money(udata['balance'])} монет\n"
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_main")]])
        )

    # ---- АДМИН-ПАНЕЛЬ ----
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
                [InlineKeyboardButton("🚫 Бан/Разбан", callback_data="admin_ban")],
                [InlineKeyboardButton("🎁 Промокоды", callback_data="admin_promo")],
                [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
                [InlineKeyboardButton("🔙 Назад", callback_data="back_main")],
            ])
        )
    elif data == "admin_stats":
        if user_id != ADMIN_ID:
            return
        total = len(users)
        premium_count = sum(1 for u in users.values() if u.get("premium"))
        banned_count = sum(1 for u in users.values() if u.get("banned"))
        total_money = sum(u["balance"] for u in users.values())
        await query.edit_message_text(
            f"📊 **Статистика**\n\n"
            f"👥 Всего пользователей: {total}\n"
            f"💎 Премиум: {premium_count}\n"
            f"🚫 Забанено: {banned_count}\n"
            f"💰 Всего монет: {format_money(total_money)}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
        )
    elif data == "admin_give":
        if user_id != A
