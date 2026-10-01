import os
import asyncio
import logging
import random
import json
import pytz
import re
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import yt_dlp

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sozlamalar
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8772192229:AAGP_TiLNzROuCW2n_CvDcDTeTVieSSiwxs")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 8715668931))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Foydalanuvchilar va ularning kelgan manbasini saqlash
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
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

users_db = load_users()

# FSM Shtatlari (Anonim Chat uchun)
class AnonState(StatesGroup):
    waiting_for_msg = State()

# Avto-xabarlar ro'yxati
RANDOM_MESSAGES = [
    "Bilasizmi? Dunyodagi eng qisqa urush 1896-yilda Angliya va Zanzibar o'rtasida bo'lgan. U atigi 38 daqiqa davom etgan! ⏱",
    "Muvaffaqiyat - bu yiqilishdan qo'rqmaslik, balki har yiqilganda qayta turishdir. 🚀",
    "Hazil vaqti: Dasturchining hayoti – 10% kod yozish, 90% esa uning xatosini qidirish. 💻😅",
    "Vaqt — bu eng qimmatli resurs. Uni to'g'ri sarflang! ⏳",
    "Qiziqarli fakt: Inson miyasi tunda, uxlashga yotganda faolroq ishlaydi. 🧠✨",
    "O'zingizga eslatma: Suv ichishni unutmang! Salomatlik hamma narsadan muhim. 💧"
]

# ==========================================
# 1. MEDIA YUKLAB OLISH (YouTube, Instagram, TikTok)
# ==========================================

def search_youtube_music(query):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        res = ydl.extract_info(f"ytsearch5:{query}", download=False)
        results = []
        if 'entries' in res:
            for entry in res['entries']:
                results.append({
                    'id': entry.get('id'),
                    'title': entry.get('title', 'Noma\'lum qo\'shiq'),
                    'duration': entry.get('duration', 0),
                    'url': f"https://www.youtube.com/watch?v={entry.get('id')}"
                })
        return results

def download_social_media(url, download_type='video'):
    os.makedirs("downloads", exist_ok=True)
    out_tmpl = 'downloads/%(id)s.%(ext)s'
    
    if download_type == 'audio':
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': out_tmpl,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True
        }
    else:
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': out_tmpl,
            'quiet': True,
            'no_warnings': True
        }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        if download_type == 'audio':
            filename = os.path.splitext(filename)[0] + '.mp3'
        return filename, info.get('title', 'Media')

# ==========================================
# 2. START VA ANONIM CHAT
# ==========================================

@dp.message(Command("start"))
async def start_handler(message: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()
    user_id = str(message.chat.id)
    args = command.args

    if user_id not in users_db:
        users_db[user_id] = {
            "referrer": args if args else "direct",
            "name": message.from_user.full_name
        }
        save_users(users_db)

    if args and args != user_id:
        target_id = args
        await state.update_data(target_id=target_id)
        await state.set_state(AnonState.waiting_for_msg)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_anon")]
        ])

        await message.answer(
            "👤 **Siz ushbu foydalanuvchiga anonim xabar yozmoqdasiz!**\n\n"
            "Matn, rasm, ovozli xabar yoki video yuborishingiz mumkin. Shaxsingiz sir saqlanadi 🤫",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return

    bot_info = await bot.get_me()
    anon_link = f"https://t.me/{bot_info.username}?start={user_id}"

    text = (
        f"Xush kelibsiz, **{message.from_user.first_name}**! 👋\n\n"
        f"🔗 **Sizning shaxsiy anonim havolangiz:**\n`{anon_link}`\n\n"
        f"Ushbu havolani ijtimoiy tarmoqlarga qo'ying. Odamlar sizga anonim xabar yuborishlari mumkin!\n\n"
        f"📥 **Media Yuklagich:**\n"
        f"• **Instagram** (Reels / Post / Stories)\n"
        f"• **TikTok** (Suv belgisisiz)\n"
        f"• **YouTube** (Video & MP3)\n\n"
        f"Shunchaki havolani yuboring yoki qo'shiq nomini yozing!"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Havolani ulashish", url=f"https://t.me/share/url?url={anon_link}&text=Menga%20anonim%20xabar%20yuboring!")],
    ])

    await message.answer(text, parse_mode="Markdown", reply_markup=kb)

# Anonim xabar yuborish
@dp.message(AnonState.waiting_for_msg)
async def process_anon_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get("target_id")

    kb_receiver = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Anonim javob berish", callback_data=f"reply_anon:{message.from_user.id}")]
    ])

    try:
        await message.send_copy(chat_id=target_id, reply_markup=kb_receiver)
        
        kb_sender = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Yana xabar yozish", callback_data=f"write_again:{target_id}")],
            [InlineKeyboardButton(text="🔗 O'zim uchun havola olish", callback_data="get_my_link")]
        ])

        await message.answer("✅ **Xabaringiz anonim ravishda yetkazildi!**", parse_mode="Markdown", reply_markup=kb_sender)
        await state.clear()

    except Exception as e:
        await message.answer("❌ Xabar yuborishda xatolik bo'ldi. Foydalanuvchi botni bloklagan bo'lishi mumkin.")
        await state.clear()

@dp.callback_query(F.data.startswith("write_again:"))
async def write_again_callback(call: types.CallbackQuery, state: FSMContext):
    target_id = call.data.split(":")[1]
    await state.update_data(target_id=target_id)
    await state.set_state(AnonState.waiting_for_msg)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_anon")]
    ])
    await call.message.edit_text("✍ **Yana anonim xabaringizni yozib yuboring:**", parse_mode="Markdown", reply_markup=kb)

@dp.callback_query(F.data.startswith("reply_anon:"))
async def reply_anon_callback(call: types.CallbackQuery, state: FSMContext):
    target_id = call.data.split(":")[1]
    await state.update_data(target_id=target_id)
    await state.set_state(AnonState.waiting_for_msg)

    await call.message.answer("💬 **Javob xabaringizni yozing:**")
    await call.answer()

@dp.callback_query(F.data == "cancel_anon")
async def cancel_anon(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Bekor qilindi.")

@dp.callback_query(F.data == "get_my_link")
async def get_my_link(call: types.CallbackQuery):
    bot_info = await bot.get_me()
    anon_link = f"https://t.me/{bot_info.username}?start={call.from_user.id}"
    await call.message.answer(f"🔗 **Sizning havolangiz:**\n`{anon_link}`", parse_mode="Markdown")
    await call.answer()

# ==========================================
# 3. ADMIN PANEL (/users)
# ==========================================

@dp.message(Command("users"))
async def admin_users_handler(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Sizda bu buyruqdan foydalanish huquqi yo'q! ❌")
        return

    count = len(users_db)
    if count == 0:
        await message.answer("Hozircha botda foydalanuvchilar yo'q.")
        return

    text = f"📊 **Umumiy foydalanuvchilar:** {count} ta\n\n**Ro'yxat va kelgan manbasi (Link):**\n"
    for i, (uid, uinfo) in enumerate(users_db.items(), 1):
        ref = uinfo.get("referrer", "direct")
        source = f"Direct (O'zi kirgan)" if ref == "direct" else f"Link: {ref}"
        text += f"{i}. `{uid}` | Manba: {source}\n"
        if i >= 40:
            text += "...va boshqalar."
            break

    await message.answer(text, parse_mode="Markdown")

# ==========================================
# 4. INSTAGRAM, TIKTOK, YOUTUBE & MUSIC HANDLER
# ==========================================

@dp.message(F.text)
async def media_search_handler(message: types.Message):
    text = message.text

    # 1. Instagram yoki TikTok havolasi yuborilganda
    if "instagram.com" in text or "tiktok.com" in text:
        msg = await message.answer("📥 **Video yuklanmoqda...**\nIltimos, ozgina kuting.", parse_mode="Markdown")
        try:
            file_path, title = await asyncio.to_thread(download_social_media, text, 'video')
            video_file = FSInputFile(file_path)

            await message.answer_video(
                video=video_file,
                caption=f"🎬 @{(await bot.get_me()).username} orqali yuklab olindi."
            )
            await msg.delete()
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"Social download error: {e}")
            await msg.edit_text("❌ Videoni yuklashda xatolik yuz berdi. Havola ochiq (public) ekanligini tekshiring.")
        return

    # 2. YouTube havolasi yuborilganda
    if "youtube.com" in text or "youtu.be" in text:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🎵 MP3 (Audio)", callback_data="dl_yt:audio"),
                InlineKeyboardButton(text="🎬 MP4 (Video)", callback_data="dl_yt:video")
            ]
        ])
        await message.answer("🎬 YouTube havolasi aniqlandi. Qaysi formatda yuklamoqchisiz?", reply_markup=kb)
        return

    # 3. Oddiy matn yozilganda - Musiqa qidirish
    msg = await message.answer("🔍 Qo'shiq qidirilmoqda, kuting...")
    results = await asyncio.to_thread(search_youtube_music, text)

    if not results:
        await msg.edit_text("❌ Hech narsa topilmadi. Boshqacha nom yozib ko'ring.")
        return

    buttons = []
    for i, item in enumerate(results, 1):
        dur = f"{item['duration'] // 60}:{item['duration'] % 60:02d}"
        buttons.append([InlineKeyboardButton(
            text=f"{i}. {item['title'][:35]} ({dur})",
            callback_data=f"dl_music:{item['id']}"
        )])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await msg.edit_text(f"🎶 **'{text}' bo'yicha topilgan natijalar:**\nYuklab olish uchun birini tanlang:", parse_mode="Markdown", reply_markup=kb)

# YouTube / Musiqa yuklab berish Callbacklari
@dp.callback_query(F.data.startswith("dl_music:"))
async def download_music_callback(call: types.CallbackQuery):
    video_id = call.data.split(":")[1]
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    await call.message.edit_text("📥 Musiqa yuklab olinmoqda...")

    try:
        file_path, title = await asyncio.to_thread(download_social_media, url, 'audio')
        audio_file = FSInputFile(file_path)
        
        await call.message.answer_audio(audio=audio_file, caption=f"🎶 **{title}**\n\n@{(await bot.get_me()).username} orqali yuklandi.", parse_mode="Markdown")
        await call.message.delete()
        
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.error(f"Download error: {e}")
        await call.message.answer("❌ Faylni yuklashda xatolik bo'ldi.")

@dp.callback_query(F.data.startswith("dl_yt:"))
async def download_yt_direct(call: types.CallbackQuery):
    dl_type = call.data.split(":")[1]
    url = call.message.reply_to_message.text if call.message.reply_to_message else None

    if not url:
        await call.message.edit_text("❌ Havola topilmadi.")
        return

    await call.message.edit_text("📥 Yuklanmoqda, kuting...")

    try:
        file_path, title = await asyncio.to_thread(download_social_media, url, dl_type)
        media_file = FSInputFile(file_path)

        if dl_type == 'audio':
            await call.message.answer_audio(audio=media_file, caption=f"🎵 {title}")
        else:
            await call.message.answer_video(video=media_file, caption=f"🎬 {title}")

        await call.message.delete()
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.error(f"Download error: {e}")
        await call.message.answer("❌ Yuklashda xatolik yuz berdi.")

# ==========================================
# 5. HAR 12 SOATDA XABAR YUBORISH
# ==========================================

async def send_periodic_messages():
    if not users_db:
        return
    message_text = random.choice(RANDOM_MESSAGES)
    for uid in list(users_db.keys()):
        try:
            await bot.send_message(chat_id=int(uid), text=message_text)
            await asyncio.sleep(0.05)
        except Exception:
            pass

async def main():
    logger.info("Bot ishga tushmoqda...")

    # Render uchun Web Server
    async def handle(request):
        return web.Response(text="Bot is running smoothly!")

    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    # Scheduler (12 soat)
    tashkent_tz = pytz.timezone("Asia/Tashkent")
    scheduler = AsyncIOScheduler(timezone=tashkent_tz)
    scheduler.add_job(send_periodic_messages, 'interval', hours=12)
    scheduler.start()

    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
