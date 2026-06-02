import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "1043717905"))
BASE_TRACKING_LINK = os.getenv("BASE_TRACKING_LINK", "https://trk.ppdu.ru/click?uid=107877&oid=2304&erid=CQH36pWzJqVGXC5oLP8WVVNCNqJmbhiUPijGiu4zpwPd7G&landingId=2489")

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN")  # Railway сам подставит

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class Questionnaire(StatesGroup):
    city = State()
    age = State()
    transport = State()
    experience = State()
    full_time = State()
    name = State()
    phone = State()

# === все обработчики (start, city, age, transport, experience, full_time, name, phone) ===
# я скопировал их из предыдущей версии, они не изменились

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    args = message.text.split()
    clickid = args[1] if len(args) > 1 else None
    await state.update_data(clickid=clickid)
    await message.answer("Привет! Ответь на 6 вопросов — данные уйдут в Пампаду.\n\nВ каком городе живёшь?")
    await state.set_state(Questionnaire.city)

# ... (остальные process_ функции точно такие же, как в прошлом сообщении)

@dp.message(Questionnaire.phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.isdigit() or len(phone) != 11 or not phone.startswith("7"):
        return await message.answer("Номер в формате 7XXXXXXXXXX")

    data = await state.get_data()

    tracking_link = (
        f"{BASE_TRACKING_LINK}"
        f"&sub1={data['city']}&sub2={data['age']}&sub3={data['transport']}"
        f"&sub4={data['experience']}&sub5={data['full_time']}"
    )

    await message.answer(f"✅ Готово!\n\nВот твоя ссылка:\n{tracking_link}\n\nПереходи и завершай регистрацию.")

    logging.info(f"НОВАЯ ЗАЯВКА | {data['name']} | {phone} | {data['city']} | {data['age']}")

    try:
        admin_text = f"🆕 Заявка!\nИмя: {data['name']}\nТел: {phone}\nГород: {data['city']}\nСсылка: {tracking_link}"
        await bot.send_message(ADMIN_CHAT_ID, admin_text)
    except:
        pass

    await state.clear()

# ================= WEBHOOK =================
async def on_startup(bot: Bot):
    if WEBHOOK_URL:
        await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}")
        logging.info(f"Webhook установлен: {WEBHOOK_URL}{WEBHOOK_PATH}")

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()

def main():
    app = web.Application()
    setup_application(app, dp, bot=bot)

    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    port = int(os.getenv("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()