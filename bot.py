import os
import asyncio
import logging
import json
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, TelegramObject
import yt_dlp

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# BOT SOZLAMALARI (TOKEN VA ADMIN ID)
# ==========================================
BOT_TOKEN = "8727972367:AAGNFTNfcbkZrjrmrD5XWad1MeWah3XfWLk"
ADMIN_ID = 8715668931

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==========================================
# MA'LUMOTLAR BAZASI (users.json)
# ==========================================
USERS_FILE = "users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_users(users):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Faylga saqlashda xatolik: {e}")

users_db = load_users()

class UserTrackerMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user:
            uid = str(user.id)
            if uid not in users_db:
                users_db[uid] = {
                    "name": user.full_name or "Foydalanuvchi",
                    "username": f"@{user.username}" if user.username else "yo'q"
                }
                save_users(users_db)
        return await handler(event, data)

dp.message.outer_middleware(UserTrackerMiddleware())
dp.callback_query.outer_middleware(UserTrackerMiddleware())

class AnonState(StatesGroup):
    waiting_for_msg = State()

# ==========================================
# INSTAGRAM / TIKTOK DOWNLOADER
# ==========================================
def download_media(url):
    os.makedirs("downloads", exist_ok=True)
    out_tmpl = 'downloads/%(id)s.%(ext)s'
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': out_tmpl,
        'quiet': True,
        'no_warnings': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename

# ==========================================
# 1. START BUYRUQ VA ANONIM LINK SYSTEM
# ==========================================
@dp.message(Command("start"))
async def start_handler(message: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()
    user_id = str(message.chat.id)
    args = command.args

    # Agar boshqa odamning anonim havolasi orqali kirgan bo'lsa
    if args and args != user_id:
        await state.update_data(target_id=args)
        await state.set_state(AnonState.waiting_for_msg)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_anon")]
        ])
        await message.answer(
            "👤 **Ushbu foydalanuvchiga anonim xabar yuboring:**\n"
            "(Matn, rasm, rasm-fayl, stiker yoki ovozli xabar yuborishingiz mumkin 🤫)",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return

    # Oddiy kirgan bo'lsa
    bot_info = await bot.get_me()
    anon_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    text = (
        f"Assalomu alaykum, **{message.from_user.first_name}**! 👋\n\n"
        f"🔗 **Sizning shaxsiy anonim havolangiz:**\n`{anon_link}`\n\n"
        f"📌 **Bot imkoniyatlari:**\n"
        f"1️⃣ **Anonim Chat:** Havolangizni va hikoyalaringizni (story) do'stlaringizga ulashing va anonim xabarlar oling.\n"
        f"2️⃣ **Instagram & TikTok Downloader:** Botga shunchaki Reels yoki Post havolasini yuboring, bot sizga videoni yuklab beradi!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Havolani do'stlarga ulashish", url=f"https://t.me/share/url?url={anon_link}&text=Menga%20anonim%20xabar%20yuboring!")]
    ])
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

# ==========================================
# 2. ANONIM XABAR YUBORISH
# ==========================================
@dp.message(AnonState.waiting_for_msg)
async def process_anon_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("target_id")

    kb_receiver = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Javob berish", callback_data=f"reply_anon:{message.from_user.id}")]
    ])

    try:
        await message.send_copy(chat_id=target_id, reply_markup=kb_receiver)
        kb_sender = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Yana xabar yozish", callback_data=f"write_again:{target_id}")],
            [InlineKeyboardButton(text="🔗 O'zim uchun havola olish", callback_data="get_my_link")]
        ])
        await message.answer("✅ **Xabaringiz anonim tarzda yetkazildi!**", parse_mode="Markdown", reply_markup=kb_sender)
        await state.clear()
    except Exception:
        await message.answer("❌ Xabar yetkazilmadi. Foydalanuvchi botni bloklagan bo'lishi mumkin.")
        await state.clear()

@dp.callback_query(F.data.startswith("reply_anon:"))
async def reply_anon_callback(call: types.CallbackQuery, state: FSMContext):
    target_id = call.data.split(":")[1]
    await state.update_data(target_id=target_id)
    await state.set_state(AnonState.waiting_for_msg)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_anon")]])
    await call.message.answer("💬 **Anonim javob xabaringizni yozing:**", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("write_again:"))
async def write_again_callback(call: types.CallbackQuery, state: FSMContext):
    target_id = call.data.split(":")[1]
    await state.update_data(target_id=target_id)
    await state.set_state(AnonState.waiting_for_msg)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_anon")]])
    await call.message.edit_text("✍️ **Yana anonim xabaringizni kiriting:**", reply_markup=kb)

@dp.callback_query(F.data == "cancel_anon")
async def cancel_anon(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Bekor qilindi.")

@dp.callback_query(F.data == "get_my_link")
async def get_my_link(call: types.CallbackQuery):
    bot_info = await bot.get_me()
    await call.message.answer(f"🔗 **Sizning havolangiz:**\nhttps://t.me/{bot_info.username}?start={call.from_user.id}")
    await call.answer()

# ==========================================
# 3. ADMIN PANEL (/users)
# ==========================================
@dp.message(Command("users"))
async def admin_users(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    count = len(users_db)
    await message.answer(f"📊 **Bot foydalanuvchilari soni:** {count} ta", parse_mode="Markdown")

# ==========================================
# 4. INSTAGRAM & TIKTOK YUKLAGICH HANDLER
# ==========================================
@dp.message(F.text)
async def media_downloader_handler(message: types.Message):
    text = message.text.strip()
    
    if "instagram.com" in text or "tiktok.com" in text or "youtu" in text:
        msg = await message.answer("📥 **Media yuklanmoqda, kuting...**")
        try:
            file_path = await asyncio.to_thread(download_media, text)
            bot_info = await bot.get_me()
            await message.answer_video(
                video=FSInputFile(file_path),
                caption=f"🎬 @{bot_info.username} orqali yuklab olindi."
            )
            await msg.delete()
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"Yuklashda xatolik: {e}")
            await msg.edit_text("❌ Videoni yuklab bo'lmadi. Havola to'g'riligini yoki akkaunt ochiqligini tekshiring.")
    else:
        await message.answer("ℹ️ Anonim xabar yuborish uchun havola orqali kiring yoki Instagram/TikTok video havolasini yuboring.")

# ==========================================
# 5. RENDER SERVER VA ASOSIY TIKLANISH
# ==========================================
async def main():
    logger.info("Bot ishga tushmoqda...")
    
    # Render uchun Web server (Port bind qilish uchun)
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text="Bot runs successfully!"))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, '0.0.0.0', port).start()

    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
