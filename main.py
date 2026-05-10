# main.py

import os
import json
import logging
from datetime import datetime, timedelta
from uuid import uuid4

from dotenv import load_dotenv

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# =========================
# ЗАГРУЗКА ENV
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")

# =========================
# ЛОГИ
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# =========================
# ФАЙЛ БД
# =========================

DB_FILE = "users.json"

# =========================
# СОСТОЯНИЯ
# =========================

SELECT_SERVICE, SELECT_SLOT, ENTER_CONTACT, REVIEW_RATING, REVIEW_COMMENT = range(5)

# =========================
# ДАННЫЕ
# =========================

SERVICES = {
    "Маникюр": 2500,
    "Педикюр": 3500,
    "Наращивание": 4500,
    "Покрытие гель-лак": 3000,
}

AVAILABLE_SLOTS = [
    "2026-05-10 10:00",
    "2026-05-10 12:00",
    "2026-05-10 14:00",
    "2026-05-10 16:00",
    "2026-05-11 10:00",
    "2026-05-11 12:00",
    "2026-05-11 14:00",
    "2026-05-11 16:00",
]

# =========================
# КНОПКИ
# =========================

MAIN_KEYBOARD = [
    [KeyboardButton("💅 Записаться"), KeyboardButton("📋 Услуги и цены")],
    [KeyboardButton("⭐ Мои баллы"), KeyboardButton("🎁 Акции")],
    [KeyboardButton("📸 Портфолио"), KeyboardButton("📝 Отзывы")],
    [KeyboardButton("👥 Пригласить друга"), KeyboardButton("❓ Помощь")],
]

reply_markup = ReplyKeyboardMarkup(
    MAIN_KEYBOARD,
    resize_keyboard=True,
)

# =========================
# JSON
# =========================

def load_data():
    try:
        if not os.path.exists(DB_FILE):
            return {
                "users": {},
                "appointments": [],
                "reviews": [],
                "broadcasts": [],
            }

        with open(DB_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    except Exception as e:
        logger.error(f"Ошибка загрузки данных: {e}")
        return {
            "users": {},
            "appointments": [],
            "reviews": [],
            "broadcasts": [],
        }


def save_data(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)

    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")

# =========================
# UTILS
# =========================

def get_user(data, user_id):
    user_id = str(user_id)

    if user_id not in data["users"]:
        data["users"][user_id] = {
            "points": 0,
            "visits": 0,
            "referrals": 0,
            "name": "",
            "username": "",
            "ref_code": str(uuid4())[:8],
        }

    return data["users"][user_id]


def slot_taken(data, slot):
    for appointment in data["appointments"]:
        if appointment["slot"] == slot:
            return True
    return False


async def send_admin_notification(context, text):
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=text,
        )
    except Exception as e:
        logger.error(f"Ошибка отправки админу: {e}")

# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = load_data()

        user = update.effective_user
        user_data = get_user(data, user.id)

        user_data["name"] = user.full_name
        user_data["username"] = user.username or ""

        save_data(data)

        text = (
            f"💅 Добро пожаловать, {user.first_name}!\n\n"
            f"Я бот вашего мастера маникюра ✨\n\n"
            f"Выберите нужный пункт меню:"
        )

        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
        )

    except Exception as e:
        logger.error(f"Ошибка start: {e}")

# =========================
# ЗАПИСЬ
# =========================

async def book_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("BOOK START WORKS")
    try:
        keyboard = []

        for service, price in SERVICES.items():
            keyboard.append([
                InlineKeyboardButton(
                    f"{service} — {price}₽",
                    callback_data=f"service_{service}"
                )
            ])

        await update.message.reply_text(
            "💅 Выберите услугу:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

        return SELECT_SERVICE

    except Exception as e:
        logger.error(f"Ошибка выбора услуги: {e}")
        return ConversationHandler.END


async def select_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()

        service = query.data.replace("service_", "")
        context.user_data["service"] = service

        data = load_data()

        keyboard = []

        for slot in AVAILABLE_SLOTS:
            if not slot_taken(data, slot):
                keyboard.append([
                    InlineKeyboardButton(
                        slot,
                        callback_data=f"slot_{slot}"
                    )
                ])

        if not keyboard:
            await query.message.reply_text(
                "❌ Свободных слотов нет."
            )
            return ConversationHandler.END

        await query.message.reply_text(
            "📅 Выберите дату и время:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

        return SELECT_SLOT

    except Exception as e:
        logger.error(f"Ошибка select_service: {e}")
        return ConversationHandler.END


async def select_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()

        slot = query.data.replace("slot_", "")

        data = load_data()

        if slot_taken(data, slot):
            await query.message.reply_text(
                "❌ Этот слот уже занят."
            )
            return ConversationHandler.END

        context.user_data["slot"] = slot

        await query.message.reply_text(
            "📞 Отправьте данные для связи:\n\n"
            "Например:\n"
            "Имя Фамилия\n"
            "@username\n"
            "+79999999999"
        )

        return ENTER_CONTACT

    except Exception as e:
        logger.error(f"Ошибка select_slot: {e}")
        return ConversationHandler.END

async def save_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        contact = update.message.text

        slot = context.user_data["slot"]
        service = context.user_data["service"]

        data = load_data()

        appointment = {
            "user_id": update.effective_user.id,
            "name": update.effective_user.full_name,
            "contact": contact,
            "service": service,
            "slot": slot,
            "created_at": str(datetime.now()),
            "reminded_day": False,
            "reminded_2h": False,
        }

        data["appointments"].append(appointment)

        save_data(data)

        await update.message.reply_text(
            f"✅ Вы успешно записаны!\n\n"
            f"💅 Услуга: {service}\n"
            f"📅 Дата: {slot}\n"
            f"📞 Контакт: {contact}",
            reply_markup=reply_markup,
        )

        await send_admin_notification(
            context,
            (
                f"📥 Новая запись!\n\n"
                f"👤 Клиент: {update.effective_user.full_name}\n"
                f"📞 Контакт: {contact}\n"
                f"💅 Услуга: {service}\n"
                f"📅 Время: {slot}"
            )
        )

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Ошибка save_contact: {e}")
        return ConversationHandler.END


       

    except Exception as e:
        logger.error(f"Ошибка select_slot: {e}")
        return ConversationHandler.END

# =========================
# ПРАЙС
# =========================

async def show_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = "📋 <b>Услуги и цены</b>\n\n"

        for service, price in SERVICES.items():
            text += f"💅 {service} — <b>{price}₽</b>\n"

        text += "\n✨ Работаем только на качественных материалах"

        await update.message.reply_text(
            text,
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Ошибка прайса: {e}")

# =========================
# БАЛЛЫ
# =========================

async def my_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = load_data()

        user = get_user(data, update.effective_user.id)

        text = (
            f"⭐ Ваши баллы: {user['points']}\n\n"
            f"💎 Визитов: {user['visits']}\n\n"
            f"🎁 5 визитов = скидка 10%\n"
            f"🎁 10 визитов = бесплатное покрытие"
        )

        await update.message.reply_text(text)

    except Exception as e:
        logger.error(f"Ошибка баллов: {e}")

# =========================
# ПОРТФОЛИО
# =========================

async def portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = (
            "📸 Мои работы:\n\n"
            "Instagram:\n"
            "https://instagram.com/your_profile\n\n"
            "Pinterest:\n"
            "https://pinterest.com/your_profile"
        )

        await update.message.reply_text(text)

    except Exception as e:
        logger.error(f"Ошибка портфолио: {e}")

# =========================
# АКЦИИ
# =========================

async def promotions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = load_data()
        promo = data.get("promo", "Акций пока нет.")

        await update.message.reply_text(
            f"🎁 Актуальные акции:\n\n{promo}"
        )

    except Exception as e:
        logger.error(f"Ошибка акций: {e}")

# =========================
# РЕФЕРАЛКА
# =========================

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = load_data()

        user = get_user(data, update.effective_user.id)

        bot_username = (await context.bot.get_me()).username

        link = (
            f"https://t.me/{bot_username}"
            f"?start={user['ref_code']}"
        )

        text = (
            "👥 Ваша реферальная ссылка:\n\n"
            f"{link}\n\n"
            "🎁 За каждого приглашенного друга "
            "вы получаете бонусный балл!"
        )

        await update.message.reply_text(text)

    except Exception as e:
        logger.error(f"Ошибка referral: {e}")


        # =========================
# ПОМОЩЬ
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = (
            "❓ <b>Помощь</b>\n\n"
            "💅 <b>Записаться</b> — выбрать дату и время\n"
            "📋 <b>Услуги и цены</b> — полный прайс\n"
            "⭐ <b>Мои баллы</b> — программа лояльности\n"
            "🎁 <b>Акции</b> — текущие скидки\n"
            "📸 <b>Портфолио</b> — примеры работ\n"
            "📝 <b>Отзывы</b> — отзывы клиентов\n"
            "👥 <b>Пригласить друга</b> — реферальная ссылка\n\n"
            "По всем вопросам пишите мастеру: @username_мастера"
        )

        await update.message.reply_text(
            text,
            parse_mode="HTML",
        )

    except Exception as e:
        logger.error(f"Ошибка help: {e}")

# =========================
# ОТЗЫВЫ
# =========================

async def reviews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = load_data()

        if not data["reviews"]:
            await update.message.reply_text(
                "📝 Отзывов пока нет."
            )
            return

        text = "📝 Лучшие отзывы:\n\n"

        for review in data["reviews"][-5:]:
            text += (
                f"⭐ {review['rating']}/5\n"
                f"{review['comment']}\n"
                f"— {review['name']}\n\n"
            )

        await update.message.reply_text(text)

    except Exception as e:
        logger.error(f"Ошибка reviews: {e}")

# =========================
# АДМИН
# =========================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            return

        data = load_data()

        today = datetime.now().strftime("%Y-%m-%d")

        text = "📅 Записи на сегодня:\n\n"

        found = False

        for app in data["appointments"]:
            if today in app["slot"]:
                found = True

                text += (
                    f"👤 {app['name']}\n"
                    f"💅 {app['service']}\n"
                    f"🕐 {app['slot']}\n\n"
                )

        if not found:
            text += "Нет записей."

        await update.message.reply_text(text)

    except Exception as e:
        logger.error(f"Ошибка admin: {e}")

# =========================
# CLIENTS
# =========================

async def clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            return

        data = load_data()

        text = "👥 Клиенты:\n\n"

        for user_id, user in data["users"].items():
            text += (
                f"👤 {user['name']}\n"
                f"⭐ Баллы: {user['points']}\n\n"
            )

        await update.message.reply_text(text)

    except Exception as e:
        logger.error(f"Ошибка clients: {e}")

# =========================
# STATS
# =========================

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            return

        data = load_data()

        service_count = {}

        for app in data["appointments"]:
            service = app["service"]

            if service not in service_count:
                service_count[service] = 0

            service_count[service] += 1

        text = (
            f"📊 Статистика:\n\n"
            f"👥 Клиентов: {len(data['users'])}\n"
            f"📅 Записей: {len(data['appointments'])}\n\n"
            f"🔥 Популярные услуги:\n"
        )

        for service, count in service_count.items():
            text += f"{service}: {count}\n"

        await update.message.reply_text(text)

    except Exception as e:
        logger.error(f"Ошибка stats: {e}")

# =========================
# BROADCAST
# =========================

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            return

        if not context.args:
            await update.message.reply_text(
                "Использование:\n"
                "/broadcast Текст сообщения"
            )
            return

        text = " ".join(context.args)

        data = load_data()

        success = 0

        for user_id in data["users"]:
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=f"🎁 Новость от мастера:\n\n{text}",
                )
                success += 1

            except Exception as e:
                logger.error(f"Ошибка рассылки: {e}")

        await update.message.reply_text(
            f"✅ Отправлено: {success}"
        )

    except Exception as e:
        logger.error(f"Ошибка broadcast: {e}")

# =========================
# НАПОМИНАНИЯ
# =========================

async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        data = load_data()

        now = datetime.now()

        changed = False

        for appointment in data["appointments"]:
            if appointment["reminded"]:
                continue

            appointment_time = datetime.strptime(
                appointment["slot"],
                "%Y-%m-%d %H:%M"
            )

            delta = appointment_time - now

            if timedelta(hours=23) <= delta <= timedelta(hours=24):
                try:
                    await context.bot.send_message(
                        chat_id=appointment["user_id"],
                        text=(
                            "⏰ Напоминание!\n\n"
                            f"Завтра у вас запись:\n"
                            f"💅 {appointment['service']}\n"
                            f"📅 {appointment['slot']}"
                        )
                    )

                    appointment["reminded"] = True
                    changed = True

                except Exception as e:
                    logger.error(f"Ошибка reminder: {e}")

        if changed:
            save_data(data)

    except Exception as e:
        logger.error(f"Ошибка reminder_job: {e}")

# =========================
# ERROR
# =========================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception:", exc_info=context.error)

    # =========================
# УПРАВЛЕНИЕ СЛОТАМИ
# =========================

async def addslot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            return

        if not context.args:
            await update.message.reply_text(
                "Использование:\n"
                "/addslot 2026-05-15 10:00"
            )
            return

        slot = " ".join(context.args)

        # Проверяем формат
        try:
            datetime.strptime(slot, "%Y-%m-%d %H:%M")
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат!\n"
                "Пример: /addslot 2026-05-15 10:00"
            )
            return

        # Проверяем что слот не дублируется
        if slot in AVAILABLE_SLOTS:
            await update.message.reply_text(
                f"❌ Слот {slot} уже существует!"
            )
            return

        AVAILABLE_SLOTS.append(slot)
        AVAILABLE_SLOTS.sort()

        await update.message.reply_text(
            f"✅ Слот добавлен: {slot}\n\n"
            f"📅 Всего слотов: {len(AVAILABLE_SLOTS)}"
        )

    except Exception as e:
        logger.error(f"Ошибка addslot: {e}")


async def deleteslot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            return

        if not context.args:
            # Показываем все слоты с кнопками
            if not AVAILABLE_SLOTS:
                await update.message.reply_text("❌ Нет доступных слотов.")
                return

            text = "📅 Доступные слоты:\n\n"
            for i, slot in enumerate(AVAILABLE_SLOTS, 1):
                text += f"{i}. {slot}\n"
            text += "\nИспользование:\n/deleteslot 2026-05-15 10:00"

            await update.message.reply_text(text)
            return

        slot = " ".join(context.args)

        if slot not in AVAILABLE_SLOTS:
            await update.message.reply_text(
                f"❌ Слот {slot} не найден!"
            )
            return

        AVAILABLE_SLOTS.remove(slot)

        await update.message.reply_text(
            f"✅ Слот удалён: {slot}\n\n"
            f"📅 Осталось слотов: {len(AVAILABLE_SLOTS)}"
        )

    except Exception as e:
        logger.error(f"Ошибка deleteslot: {e}")


async def listslots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            return

        if not AVAILABLE_SLOTS:
            await update.message.reply_text("❌ Нет доступных слотов.")
            return

        text = "📅 Все доступные слоты:\n\n"
        for slot in AVAILABLE_SLOTS:
            text += f"• {slot}\n"

        await update.message.reply_text(text)

    except Exception as e:
        logger.error(f"Ошибка listslots: {e}")


# =========================
# УПРАВЛЕНИЕ ЦЕНАМИ
# =========================

async def setprice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            return

        if len(context.args) < 2:
            text = (
                "Использование:\n"
                "/setprice Маникюр 3000\n\n"
                "📋 Текущие цены:\n\n"
            )
            for service, price in SERVICES.items():
                text += f"• {service} — {price}₽\n"

            await update.message.reply_text(text)
            return

        # Последний аргумент — цена, остальное — название услуги
        price_str = context.args[-1]
        service = " ".join(context.args[:-1])

        try:
            price = int(price_str)
        except ValueError:
            await update.message.reply_text(
                "❌ Цена должна быть числом!\n"
                "Пример: /setprice Маникюр 3000"
            )
            return

        if service not in SERVICES:
            text = (
                f"❌ Услуга '{service}' не найдена!\n\n"
                "Доступные услуги:\n"
            )
            for s in SERVICES:
                text += f"• {s}\n"
            await update.message.reply_text(text)
            return

        old_price = SERVICES[service]
        SERVICES[service] = price

        await update.message.reply_text(
            f"✅ Цена обновлена!\n\n"
            f"💅 Услуга: {service}\n"
            f"💰 Было: {old_price}₽\n"
            f"💰 Стало: {price}₽"
        )

    except Exception as e:
        logger.error(f"Ошибка setprice: {e}")


# =========================
# УПРАВЛЕНИЕ АКЦИЯМИ
# =========================

async def setpromo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.effective_user.id != ADMIN_ID:
            return

        if not context.args:
            await update.message.reply_text(
                "Использование:\n"
                "/setpromo Скидка 20% на маникюр весь май!"
            )
            return

        text = " ".join(context.args)

        data = load_data()
        data["promo"] = text
        save_data(data)

        await update.message.reply_text(
            f"✅ Акция обновлена!\n\n"
            f"🎁 {text}"
        )

    except Exception as e:
        logger.error(f"Ошибка setpromo: {e}")

# =========================
# MAIN
# =========================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Запись
    booking_handler = ConversationHandler(
    entry_points=[
        MessageHandler(
            filters.TEXT & filters.Regex("Записаться"),
            book_start
        )
    ],
    states={
        SELECT_SERVICE: [
            CallbackQueryHandler(
                select_service,
                pattern="^service_"
            )
        ],
        SELECT_SLOT: [
            CallbackQueryHandler(
                select_slot,
                pattern="^slot_"
            )
        ],
        ENTER_CONTACT: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                save_contact
            )
        ],
    },
    fallbacks=[],
)

    app.add_handler(CommandHandler("start", start))

    app.add_handler(booking_handler)

    app.add_handler(
        MessageHandler(
            filters.Regex("^📋 Услуги и цены$"),
            show_prices
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^⭐ Мои баллы$"),
            my_points
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^📸 Портфолио$"),
            portfolio
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^🎁 Акции$"),
            promotions
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^👥 Пригласить друга$"),
            referral
        )
    )

    app.add_handler(
        MessageHandler(
            filters.Regex("^📝 Отзывы$"),
            reviews
        )
    )

    # Админ
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("clients", clients))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("addslot", addslot))
    app.add_handler(CommandHandler("deleteslot", deleteslot))
    app.add_handler(CommandHandler("listslots", listslots))
    app.add_handler(CommandHandler("setprice", setprice))
    app.add_handler(CommandHandler("setpromo", setpromo))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(
        MessageHandler(
            filters.Regex("^❓ Помощь$"),
            help_command
        )
    )

    # Reminder
    app.job_queue.run_repeating(
        reminder_job,
        interval=3600,
        first=10,
    )

    app.add_error_handler(error_handler)

    print("Бот запущен...")

    app.run_polling()

# =========================
# RUN
# =========================

if __name__ == "__main__":
    main()