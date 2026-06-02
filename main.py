import os
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
BASE_TRACKING_LINK = os.getenv(
    "BASE_TRACKING_LINK",
    "https://trk.ppdu.ru/click?uid=107877&oid=2304&erid=CQH36pWzJqVGXC5oLP8WVVNCNqJmbhiUPijGiu4zpwPd7G"
)
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = "/webhook"

logging.basicConfig(level=logging.INFO)

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в переменных окружения!")

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

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    clickid = args[1] if len(args) > 1 else None
    await state.update_data(clickid=clickid)

    try:
        await message.answer(
            "Привет! 👋\n\n"
            "Хочешь работать курьером в Яндекс Еда / Лавка?\n"
            "Тогда ответь всего на 6 вопросов.\n\n"
            "В каком городе ты живёшь?"
        )
        await state.set_state(Questionnaire.city)
    except Exception:
        pass   # пользователь заблокировал бота

@dp.message(Questionnaire.city)
async def process_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await message.answer("Сколько тебе лет? (только цифры)")
    await state.set_state(Questionnaire.age)

@dp.message(Questionnaire.age)
async def process_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Напиши возраст цифрами.")
    age = int(message.text)
    if age < 18 or age > 70:
        return await message.answer("Возраст от 18 до 70 лет.")
    await state.update_data(age=age)
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=t)] for t in ["Пеший", "Велосипед", "Авто"]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("Какой транспорт будешь использовать?", reply_markup=kb)
    await state.set_state(Questionnaire.transport)

@dp.message(Questionnaire.transport)
async def process_transport(message: types.Message, state: FSMContext):
    await state.update_data(transport=message.text)
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=t)] for t in ["Да", "Нет"]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("Есть опыт работы курьером?", reply_markup=kb)
    await state.set_state(Questionnaire.experience)

@dp.message(Questionnaire.experience)
async def process_experience(message: types.Message, state: FSMContext):
    await state.update_data(experience=message.text)
    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=t)] for t in ["Полный день", "Подработка"]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("Какой график тебе удобен?", reply_markup=kb)
    await state.set_state(Questionnaire.full_time)

@dp.message(Questionnaire.full_time)
async def process_full_time(message: types.Message, state: FSMContext):
    await state.update_data(full_time=message.text)
    await message.answer("Как тебя зовут? (имя и фамилия)", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(Questionnaire.name)

@dp.message(Questionnaire.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())

    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer(
        "Теперь отправь номер телефона.\n\n"
        "Можешь нажать кнопку ниже (отправится автоматически), "
        "или просто напиши номер в формате 7XXXXXXXXXX",
        reply_markup=kb
    )
    await state.set_state(Questionnaire.phone)

@dp.message(Questionnaire.phone)
async def process_phone(message: types.Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
    else:
        phone = message.text.strip()

    phone = phone.replace("+", "").replace(" ", "").replace("-", "")

    if not phone.isdigit() or len(phone) != 11 or not phone.startswith("7"):
        await message.answer("Номер должен быть в формате 7XXXXXXXXXX (11 цифр). Попробуй ещё раз.")
        return

    data = await state.get_data()

    tracking_link = (
        f"{BASE_TRACKING_LINK}"
        f"&sub1={data['city']}"
        f"&sub2={data['age']}"
        f"&sub3={data['transport']}"
        f"&sub4={data['experience']}"
        f"&sub5={data['full_time']}"
    )

    await message.answer(
        f"✅ Отлично, {data['name']}!\n\n"
        f"Вот твоя персональная ссылка:\n\n{tracking_link}\n\n"
        f"Переходи и завершай регистрацию. Данные уже переданы менеджеру.",
        reply_markup=types.ReplyKeyboardRemove()
    )

    logging.info(f"НОВАЯ ЗАЯВКА | {data['name']} | {phone} | {data['city']} | {data['age']}")

    # Отправка уведомления админу с защитой
    try:
        admin_text = (
            f"🆕 Новая заявка!\n"
            f"Имя: {data['name']}\n"
            f"Тел: {phone}\n"
            f"Город: {data['city']}\n"
            f"Возраст: {data['age']}\n"
            f"Транспорт: {data['transport']}\n"
            f"Опыт: {data['experience']}\n"
            f"График: {data['full_time']}\n\n"
            f"Ссылка: {tracking_link}"
        )
        await bot.send_message(ADMIN_CHAT_ID, admin_text)
    except Exception:
        pass

    await state.clear()

# ================= FALLBACK =================
@dp.message()
async def fallback_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await message.answer("Что-то пошло не так. Напиши /start чтобы начать заново.")
    else:
        await message.answer("Напиши /start чтобы начать оформление.")

# ================= WEBHOOK =================
async def on_startup(app: web.Application):
    bot: Bot = app["bot"]
    if WEBHOOK_URL:
        await bot.set_webhook(f"{WEBHOOK_URL}{WEBHOOK_PATH}")
        logging.info(f"Webhook установлен: {WEBHOOK_URL}{WEBHOOK_PATH}")

async def on_shutdown(app: web.Application):
    bot: Bot = app["bot"]
    await bot.delete_webhook()

def main():
    app = web.Application()
    app["bot"] = bot
    setup_application(app, dp, bot=bot)

    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=WEBHOOK_PATH)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    port = int(os.getenv("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()