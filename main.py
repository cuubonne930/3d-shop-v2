import os
import asyncio
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from db import add_model, get_models, init_db

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
WEBAPP_URL = os.getenv("WEBAPP_URL", "")

bot = Bot(token=TOKEN)
dp = Dispatcher()

class AddModel(StatesGroup):
    waiting_photo = State()
    waiting_title = State()
    waiting_desc = State()
    waiting_price = State()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not WEBAPP_URL:
        await message.answer("⚠️ Ошибка: Ссылка на магазин не настроена.")
        return

    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Открыть магазин", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    reply_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🎁 Магазин", web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True
    )
    await message.answer("Каталог открывается внутри Telegram.\nНажми кнопку ниже 👇", reply_markup=inline_kb)
    await message.answer("Или используй меню внизу экрана:", reply_markup=reply_kb)

@dp.message(Command("add"))
async def cmd_add(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📸 Отправьте фотографию модели (или /cancel):")
    await state.set_state(AddModel.waiting_photo)

@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.")

@dp.message(AddModel.waiting_photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    os.makedirs("uploads", exist_ok=True)
    file_path = f"uploads/{photo.file_id}.jpg"
    await bot.download_file(file.file_path, file_path)
    await state.update_data(photo_path=file_path)
    await message.answer("✅ Фото сохранено. Введите название:")
    await state.set_state(AddModel.waiting_title)

@dp.message(AddModel.waiting_title)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("✍️ Введите описание:")
    await state.set_state(AddModel.waiting_desc)

@dp.message(AddModel.waiting_desc)
async def process_desc(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("💰 Введите цену (цифрами):")
    await state.set_state(AddModel.waiting_price)

@dp.message(AddModel.waiting_price)
async def process_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Только цифры!")
        return
    data = await state.get_data()
    add_model(title=data['title'], description=data['description'], price=int(message.text), photo_path=data['photo_path'])
    await state.clear()
    await message.answer("✅ Модель добавлена в каталог!")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asyncio.create_task(dp.start_polling(bot))
    yield
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
WEBAPP_DIR = os.path.join(BASE_DIR, "webapp")

os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/webapp", StaticFiles(directory=WEBAPP_DIR), name="webapp")

@app.get("/api/models")
async def api_get_models():
    return JSONResponse(content=get_models())

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(WEBAPP_DIR, "index.html"))