import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Токен не найден")

# ===== ПИЦЦЕРИЯ =====
users = {}

def get_user(user_id):
    if user_id not in users:
        users[user_id] = {"balance": 0, "level": 1, "orders": 0, "success": 0, "fail": 0}
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
        [InlineKeyboardButton("🏭 Развитие", callback_data="pizza_upgrades")],
        [InlineKeyboardButton("📊 Статистика", callback_data="pizza_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_main")],
    ])

def pizza_text(user_id):
    u = get_user(user_id)
    lvl = LEVELS[u["level"]]
    return (
        f"🍕 **ПИЦЦЕРИЯ**\n\n"
        f"💰 Баланс: {u['balance']} монет\n"
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

def main_menu(username):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🍕 Пиццерия", callback_data="pizza_menu")],
        [InlineKeyboardButton("➕ Добавить бота в чат", url=f"https://t.me/{username}?startgroup=true")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Здравствуйте!\n\nВыберите действие:",
        reply_markup=main_menu(context.bot.username)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "pizza_menu":
        await query.edit_message_text(
            pizza_text(user_id),
            parse_mode="Markdown",
            reply_markup=pizza_menu(user_id)
        )

    elif data == "pizza_order":
        if "current_order" not in context.user_data:
            context.user_data["current_order"] = generate_order(user_id)
            context.user_data["selected"] = {"dough": [], "sauce": [], "filling": [], "cheese": []}
        ingredients, order_text = context.user_data["current_order"]
        await query.edit_message_text(
            order_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🍳 Готовить", callback_data="pizza_pick")],
                [InlineKeyboardButton("🔙 Назад", callback_data="pizza_menu")],
            ])
        )

    elif data == "pizza_pick":
        selected = context.user_data.get("selected", {"dough": [], "sauce": [], "filling": [], "cheese": []})
        await query.edit_message_text(
            "🍕 **Выбери ингредиенты:**",
            parse_mode="Markdown",
            reply_markup=ingredients_menu(user_id, selected)
        )

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
            result_text = f"✅ **Заказ выполнен!**\n\nКлиент доволен 😊\nТы заработал: {reward} монет"
        else:
            u["fail"] += 1
            result_text = "❌ **Клиент ушёл!**\n\nТы перепутал ингредиенты."
        context.user_data.pop("current_order", None)
        context.user_data.pop("selected", None)
        await query.edit_message_text(
            result_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🍳 Следующий клиент", callback_data="pizza_order")],
                [InlineKeyboardButton("🏠 В меню пиццерии", callback_data="pizza_menu")],
            ])
        )

    elif data == "pizza_cancel":
        context.user_data.pop("current_order", None)
        context.user_data.pop("selected", None)
        await query.edit_message_text(
            pizza_text(user_id),
            parse_mode="Markdown",
            reply_markup=pizza_menu(user_id)
        )

    elif data == "pizza_upgrades":
        u = get_user(user_id)
        lvl = LEVELS[u["level"]]
        next_lvl = LEVELS.get(u["level"] + 1)
        if next_lvl:
            text = (
                f"🏭 **РАЗВИТИЕ ПИЦЦЕРИИ**\n\n"
                f"Текущий уровень: {lvl['name']}\n\n"
                f"Следующий уровень: {next_lvl['name']}\n"
                f"Цена: {next_lvl['price']} монет\n\n"
                f"**Что даёт:**\n"
                f"• {next_lvl['clients']} клиентов за раз\n"
                f"• Заказ: {next_lvl['ingredients']} ингредиентов\n"
                f"• Награда: {next_lvl['reward']} монет"
            )
            keyboard = [
                [InlineKeyboardButton(f"💰 Улучшить за {next_lvl['price']}", callback_data="pizza_upgrade_buy")],
                [InlineKeyboardButton("🔙 Назад", callback_data="pizza_menu")],
            ]
        else:
            text = f"🏭 **РАЗВИТИЕ ПИЦЦЕРИИ**\n\nТы достиг максимального уровня: {lvl['name']}!"
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
            f"✅ Пиццерия улучшена до {next_lvl['name']}!\n\n"
            f"Теперь ты можешь обслуживать {next_lvl['clients']} клиентов за раз.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В меню пиццерии", callback_data="pizza_menu")]])
        )

    elif data == "pizza_stats":
        u = get_user(user_id)
        await query.edit_message_text(
            f"📊 **Статистика**\n\n"
            f"🍕 Всего заказов: {u['orders']}\n"
            f"✅ Успешных: {u['success']}\n"
            f"❌ Провальных: {u['fail']}\n"
            f"💰 Заработано: {u['balance']} монет",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="pizza_menu")]])
        )

    elif data == "back_main":
        await query.edit_message_text(
            "👋 Выберите действие:",
            reply_markup=main_menu(context.bot.username)
        )

    elif data == "noop":
        await query.answer()

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

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
