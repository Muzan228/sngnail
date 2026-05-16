# api_server.py
# Запускается вместе с ботом — добавь в main.py вызов run_api()

import os
import json
import asyncio
import logging
from datetime import datetime
from aiohttp import web
from aiohttp.web_middlewares import middleware

logger = logging.getLogger(__name__)

DB_FILE = "users.json"
ADMIN_IDS = [628854840]  # Твой ID + ID владельца салона


def load_data():
    try:
        if not os.path.exists(DB_FILE):
            return {"users": {}, "appointments": [], "reviews": [], "broadcasts": []}
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"load_data error: {e}")
        return {"users": {}, "appointments": [], "reviews": [], "broadcasts": []}


def save_data(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"save_data error: {e}")


# Слоты хранятся в памяти (можно вынести в DB)
AVAILABLE_SLOTS = [
    "2026-05-20 10:00", "2026-05-20 12:00", "2026-05-20 14:00", "2026-05-20 16:00",
    "2026-05-21 10:00", "2026-05-21 12:00", "2026-05-21 14:00",
    "2026-05-22 11:00", "2026-05-22 13:00", "2026-05-22 15:00",
]

# Ссылка на bot для уведомлений (заполняется при старте)
_bot_app = None

def set_bot_app(app):
    global _bot_app
    _bot_app = app


# ── CORS middleware ──
@middleware
async def cors_middleware(request, handler):
    response = await handler(request)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


async def handle_options(request):
    return web.Response(headers={
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
    })


# ── GET /api/slots ──
async def api_slots(request):
    data = load_data()
    taken = [
        a["slot"] for a in data["appointments"]
        if a.get("status", "new") != "cancelled"
    ]
    return web.json_response({
        "slots": AVAILABLE_SLOTS,
        "taken": taken
    })


# ── POST /api/book ──
async def api_book(request):
    try:
        body = await request.json()
        user_id = body.get("user_id")
        user_name = body.get("user_name", "Клиент")
        service = body.get("service")
        price = body.get("price", 0)
        slot = body.get("slot")

        if not all([user_id, service, slot]):
            return web.json_response({"ok": False, "error": "Не хватает данных"}, status=400)

        data = load_data()

        # Проверяем что слот не занят
        for a in data["appointments"]:
            if a["slot"] == slot and a.get("status", "new") != "cancelled":
                return web.json_response({"ok": False, "error": "Слот уже занят"}, status=409)

        appointment = {
            "user_id": user_id,
            "user_name": user_name,
            "contact": "",
            "service": service,
            "price": price,
            "slot": slot,
            "status": "pending",
            "created_at": str(datetime.now()),
        }

        data["appointments"].append(appointment)
        save_data(data)

        # Уведомляем всех админов через бота
        if _bot_app:
            text = (
                f"📥 Новая запись!\n\n"
                f"👤 {user_name}\n"
                f"💅 {service}\n"
                f"📅 {slot}\n"
                f"💰 {price}₽"
            )
            for admin_id in ADMIN_IDS:
                try:
                    await _bot_app.bot.send_message(chat_id=admin_id, text=text)
                except Exception as e:
                    logger.error(f"Notify admin error: {e}")

        return web.json_response({"ok": True})

    except Exception as e:
        logger.error(f"api_book error: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── GET /api/bookings?user_id=xxx ──
async def api_bookings(request):
    user_id = request.rel_url.query.get("user_id")
    if not user_id:
        return web.json_response({"bookings": []})

    data = load_data()
    bookings = [
        a for a in data["appointments"]
        if str(a.get("user_id")) == str(user_id)
    ]
    return web.json_response({"bookings": bookings})


# ── GET /api/admin/data?admin_id=xxx ──
async def api_admin_data(request):
    admin_id = int(request.rel_url.query.get("admin_id", 0))
    if admin_id not in ADMIN_IDS:
        return web.json_response({"error": "Forbidden"}, status=403)

    data = load_data()
    return web.json_response({"bookings": data["appointments"]})


# ── POST /api/admin/confirm ──
async def api_admin_confirm(request):
    try:
        body = await request.json()
        admin_id = body.get("admin_id", 0)
        slot = body.get("slot")
        user_id = body.get("user_id")

        if int(admin_id) not in ADMIN_IDS:
            return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

        data = load_data()
        for a in data["appointments"]:
            if a["slot"] == slot and str(a["user_id"]) == str(user_id):
                a["status"] = "confirmed"
                save_data(data)

                # Уведомить клиента
                if _bot_app:
                    try:
                        await _bot_app.bot.send_message(
                            chat_id=int(user_id),
                            text=f"✅ Ваша запись подтверждена!\n\n💅 {a['service']}\n📅 {a['slot']}"
                        )
                    except Exception as e:
                        logger.error(f"Notify client error: {e}")

                return web.json_response({"ok": True})

        return web.json_response({"ok": False, "error": "Запись не найдена"}, status=404)

    except Exception as e:
        logger.error(f"api_admin_confirm error: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── POST /api/admin/cancel ──
async def api_admin_cancel(request):
    try:
        body = await request.json()
        admin_id = body.get("admin_id", 0)
        slot = body.get("slot")
        user_id = body.get("user_id")

        if int(admin_id) not in ADMIN_IDS:
            return web.json_response({"ok": False, "error": "Forbidden"}, status=403)

        data = load_data()
        for a in data["appointments"]:
            if a["slot"] == slot and str(a["user_id"]) == str(user_id):
                a["status"] = "cancelled"
                save_data(data)

                # Вернуть слот
                if slot not in AVAILABLE_SLOTS:
                    AVAILABLE_SLOTS.append(slot)
                    AVAILABLE_SLOTS.sort()

                # Уведомить клиента
                if _bot_app:
                    try:
                        await _bot_app.bot.send_message(
                            chat_id=int(user_id),
                            text=f"❌ Ваша запись отменена.\n\n💅 {a['service']}\n📅 {a['slot']}\n\nДля новой записи откройте приложение."
                        )
                    except Exception as e:
                        logger.error(f"Notify client error: {e}")

                return web.json_response({"ok": True})

        return web.json_response({"ok": False, "error": "Запись не найдена"}, status=404)

    except Exception as e:
        logger.error(f"api_admin_cancel error: {e}")
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── ЗАПУСК API ──
async def run_api(bot_app=None):
    if bot_app:
        set_bot_app(bot_app)

    app = web.Application(middlewares=[cors_middleware])
    app.router.add_route('OPTIONS', '/{path_info:.*}', handle_options)
    app.router.add_get('/api/slots', api_slots)
    app.router.add_post('/api/book', api_book)
    app.router.add_get('/api/bookings', api_bookings)
    app.router.add_get('/api/admin/data', api_admin_data)
    app.router.add_post('/api/admin/confirm', api_admin_confirm)
    app.router.add_post('/api/admin/cancel', api_admin_cancel)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"API запущен на порту {port}")
