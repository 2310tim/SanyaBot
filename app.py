import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("Токен не найден")

# ===== ХРАНИЛИЩЕ =====
users = {}  # {user_id: {"balance": 0, "level": 1, "orders": 0, "success": 0, "fail": 0, "last_order": None}}

def get_user(user_id):
    if user_id not in users:
        users[user_id] = {
            "balance": 0,
            "level": 1,
            "orders": 0,
            "success": 0,
            "fail": 0,
            "last_order": None,
        }
    return users[user_id]

# ===== УРОВНИ =====
LEVELS = {
    1: {"name": "Гараж", "min_ingredients": 2},
    2: {"name": "Ларёк", "min_ingredients": 3},
    3: {"name": "Кафе", "min_ingredients": 4},
    4: {"name": "Ресторан", "min_ingredients": 5},
    5: {"name": "Сеть", "min_ingredients": 6},
}

# ===== ИНГРЕДИЕНТЫ =====
DOUGH = ["Обычное", "Сырное", "Тонкое", "Пышное"]
SAUCE = ["Кетчуп", "Сырный", "Чесночный", "Барбекю"]
FILLING = ["Колбаса", "Пепперони", "Грибы", "Помидоры", "Оливки", "Курица"]
CHEESE = ["Моцарелла", "Чеддер", "Пармезан"]

# ===== МЕНЮ ПИЦЦЕРИИ =====
def pizza_menu(user_id):
    u = get_user(user_id)
    level_name = LEVELS[u["level"]]["name"]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🍳 Обслужить клиента", callback_data="pizza_order")],
        [InlineKeyboardButton("🏭 Улучшения", callback_data="pizza_upgrades")],
        [InlineKeyboardButton("📊 Статистика", callback_data="pizza_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_main")],
    ])

def pizza_text(user_id):
    u = get_user(user_id)
    level_name = LEVELS[u["level"]]["name"]
    return (
        f"🍕 **ПИЦЦЕРИЯ**\n\n"
        f"💰 Баланс: {u['balance']} монет\n"
        f"⭐ Уровень: {u['level']} ({level_name})\n"
        f"👥 Заказов: {u['orders']}\n"
    )

# ===== ГЕНЕРАЦИЯ ЗАКАЗА =====
def generate_order(user_id):
    u = get_user(user_id)
    lvl = u["level"]
    min_ing = LEVELS[lvl]["min_ingredients"]
    max_ing = min_ing + 2

    ingredients = {
        "dough": random.choice(DOUGH),
        "sauce": random.choice(SAUCE),
        "filling": random.sample(FILLING, random.randint(1, 2)),
        "cheese": random.choice(CHEESE),
    }

    order_text = (
        f"🍕 **КЛИЕНТ ГОВОРИТ:**\n\n"
        f"«Хочу пиццу на {ingredients['dough'].lower()} тесте, "
        f"с {ingredients['sauce'].lower()}, "
        f"{', '.join(ingredients['filling']).lower()} "
        f"и {ingredients['cheese'].lower()}»"
    )

    return ingredients, order_text

# ===== МЕНЮ ИНГРЕДИЕНТОВ =====
def ingredients_menu(user_id, selected):
    u = get_user(user_id)

    def mark(item, category):
        if item in selected.get(category, []):
            return f"✅ {item}"
        return item

    rows = []

    # Тесто
    rows.append([InlineKeyboardButton("ТЕСТО:", callback_data="noop")])
    row = []
    for d in DOUGH:
        row.append(InlineKeyboardButton(mark(d, "dough"), callback_data=f"pick_dough_{d}"))
    rows.append(row)

    # Соус
    rows.append([InlineKeyboardButton("СОУС:", callback_data="noop")])
    row = []
    for s in SAUCE:
        row.append(InlineKeyboardButton(mark(s, "sauce"), callback_data=f"pick_sauce_{s}"))
    rows.append(row)

    # Начинка
    rows.append([InlineKeyboardButton("НАЧИНКА:", callback_data="noop")])
    row = []
    for f in FILLING:
        row.append(InlineKeyboardButton(mark(f, "filling"), callback_data=f"pick_filling_{f}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    # Сыр
    rows.append([InlineKeyboardButton("СЫР:", callback_data="noop")])
    row = []
    for c in CHEESE:
        row.append(InlineKeyboardButton(mark(c, "cheese"), callback_data=f"pick_cheese_{c}"))
    rows.append(row)

    # Кнопки управления
    rows.append([
        InlineKeyboardButton("✅ Готово", callback_data="pizza_cook"),
        InlineKeyboardButton("❌ Отмена", callback_data="pizza_cancel"),
    ])

    return InlineKeyboardMarkup(rows)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Здравствуйте!\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🍕 Пиццерия", callback_data="pizza_menu")],
        ])
    )

# ===== CALLBACK =====
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    u = get_user(user_id)

    # ---- ПИЦЦЕРИЯ ----
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
            if category == "dough" or category == "sauce" or category == "cheese":
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

        # Проверка
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

        if correct:
            reward = 20 * u["level"]
            u["balance"] += reward
            u["success"] += 1
            result_text = (
                f"✅ **Заказ выполнен!**\n\n"
                f"Клиент доволен 😊\n"
                f"Ты заработал: {reward} монет"
            )
        else:
            u["fail"] += 1
            result_text = (
                f"❌ **Клиент ушёл!**\n\n"
                f"Ты перепутал ингредиенты."
            )

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
        await query.edit_message_text(
            "🏭 **Улучшения**\n\n(Функция в разработке)",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="pizza_menu")]
            ])
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
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="pizza_menu")]
            ])
        )

    elif data == "back_main":
        await query.edit_message_text(
            "👋 Выберите действие:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🍕 Пиццерия", callback_data="pizza_menu")],
            ])
        )

    elif data == "noop":
        await query.answer()

# ===== ЗАПУСК =====
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
