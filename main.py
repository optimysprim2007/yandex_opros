import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "1043717905"))
BASE_TRACKING_LINK = os.getenv("BASE_TRACKING_LINK", "https://trk.ppdu.ru/click?uid=107877&oid=2304")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class Questionnaire(StatesGroup):
    city = State()
    transport = State()
    age = State()
    experience = State()
    full_time = State()
    name = State()
    phone = State()

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    try:
        await message.answer(
            "Привет! 👋\n\n"
            "Хочешь работать курьером Яндекс.Еда / Лавка к партнёру?\n"
            "Ответь на несколько вопросов и получи персональную ссылку.\n\n"
            "В каком городе планируешь работать?"
        )
        await state.set_state(Questionnaire.city)
    except Exception:
        pass

@dp.message(Questionnaire.city)
async def process_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text.strip())

    kb = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=t)] for t in ["Пеший", "Велосипед", "Авто"]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer("Какой транспорт планируешь использовать?", reply_markup=kb)
    await state.set_state(Questionnaire.transport)

@dp.message(Questionnaire.transport)
async def process_transport(message: types.Message, state: FSMContext):
    transport = message.text
    await state.update_data(transport=transport)

    if transport == "Авто":
        await message.answer("Сколько тебе лет? (Автокурьеры — до 65 лет)")
    else:
        await message.answer("Сколько тебе лет? (Пеший и велокурьеры — до 55 лет)")
    
    await state.set_state(Questionnaire.age)

@dp.message(Questionnaire.age)
async def process_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Напиши возраст цифрами.")
    
    age = int(message.text)
    data = await state.get_data()
    transport = data.get("transport")

    if transport == "Авто" and age > 65:
        return await message.answer("Для автокурьеров максимальный возраст — 65 лет.")
    if transport in ["Пеший", "Велосипед"] and age > 55:
        return await message.answer("Для пеших и велокурьеров максимальный возраст — 55 лет.")

    await state.update_data(age=age)
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
        keyboard=[[types.KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )
    await message.answer(
        "Теперь отправь номер телефона.\n\n"
        "Можешь нажать кнопку ниже или написать вручную в формате 7XXXXXXXXXX",
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
        await message.answer("Номер должен быть в формате 7XXXXXXXXXX. Попробуй ещё раз.")
        return

    data = await state.get_data()

    # Заменяем пробелы на _ чтобы ссылка не ломалась
    city = data['city'].replace(" ", "_")
    transport = data['transport'].replace(" ", "_")
    experience = data['experience'].replace(" ", "_")
    full_time = data['full_time'].replace(" ", "_")

    tracking_link = (
        f"{BASE_TRACKING_LINK}"
        f"&sub1={city}"
        f"&sub2={data['age']}"
        f"&sub3={transport}"
        f"&sub4={experience}"
        f"&sub5={full_time}"
    )

    await message.answer(
        f"✅ Отлично, {data['name']}!\n\n"
        f"Вот твоя персональная ссылка:\n\n{tracking_link}\n\n"
        f"Переходи по ссылке и завершай регистрацию. У тебя будет 7 дней на активацию. Выплаты ежедневные (для граждан РФ и ЕАЭС).",
        reply_markup=types.ReplyKeyboardRemove()
    )

    logging.info(f"НОВАЯ ЗАЯВКА | {data['name']} | {phone} | {data['city']} | {data['age']}")

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

# Fallback + Webhook (оставил как было)
@dp.message()
async def fallback_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await message.answer("Что-то пошло не так. Напиши /start чтобы начать заново.")
    else:
        await message.answer("Напиши /start чтобы начать оформление.")

async def on_startup(app: web.Application):
    bot: Bot = app["bot"]
    if os.getenv("WEBHOOK_URL"):
        await bot.set_webhook(f"{os.getenv('WEBHOOK_URL')}/webhook")

async def on_shutdown(app: web.Application):
    bot: Bot = app["bot"]
    await bot.delete_webhook()

def main():
    app = web.Application()
    app["bot"] = bot
    setup_application(app, dp, bot=bot)
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path="/webhook")
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    port = int(os.getenv("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()