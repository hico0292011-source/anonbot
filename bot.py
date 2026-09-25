# ============================================================
# ANONBOX - TELEGRAM BOT (Tayyor variant)
# ============================================================

import asyncio
import logging
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)
from aiogram.exceptions import TelegramForbiddenError


# ============================================================
# SOZLAMALAR
# ============================================================

BOT_TOKEN = "8727972367:AAEKrhzo4E8Ma_b_j9cye9pf3e5-UT-X9kU"
ADMIN_ID = 0  # Telegram ID ingizni yozishingiz mumkin
BOT_NAME = "AnonBox"
MAX_FILE_MB = 50
MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024
DATABASE = "anonbox.db"


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("anonbox")


# ============================================================
# BOT OBJECTS
# ============================================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# sender_id -> receiver_id
anonymous_sessions = {}


# ============================================================
# DATABASE
# ============================================================

def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_database():
    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            full_name TEXT,
            anonymous_code TEXT UNIQUE,
            created_at TEXT,
            last_seen TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            url TEXT,
            media_type TEXT,
            title TEXT,
            created_at TEXT
        )
        """
    )

    connection.commit()
    connection.close()


# ============================================================
# USER SAVE
# ============================================================

def save_user(user):
    connection = get_db()
    cursor = connection.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    existing = cursor.execute(
        "SELECT anonymous_code FROM users WHERE user_id = ?",
        (user.id,)
    ).fetchone()

    if existing:
        anonymous_code = existing["anonymous_code"]
        cursor.execute(
            """
            UPDATE users
            SET username = ?, first_name = ?, last_name = ?, full_name = ?, last_seen = ?
            WHERE user_id = ?
            """,
            (user.username, user.first_name, user.last_name, user.full_name, current_time, user.id)
        )
    else:
        anonymous_code = "u" + format(user.id, "x")
        cursor.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name, full_name, anonymous_code, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user.id, user.username, user.first_name, user.last_name, user.full_name, anonymous_code, current_time, current_time)
        )

    connection.commit()
    connection.close()
    return anonymous_code


def get_user_by_code(code):
    connection = get_db()
    row = connection.execute(
        "SELECT * FROM users WHERE anonymous_code = ?",
        (code,)
    ).fetchone()
    connection.close()
    return row


def save_download(user_id, url, media_type, title):
    connection = get_db()
    connection.execute(
        """
        INSERT INTO downloads (user_id, url, media_type, title, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, url, media_type, title, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    connection.commit()
    connection.close()


async def get_bot_username():
    me = await bot.get_me()
    return me.username


# ============================================================
# KEYBOARDS
# ============================================================

def main_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📥 Media yuklash", callback_data="download")],
            [InlineKeyboardButton(text="✉️ Mening anonim linkim", callback_data="my_link")],
            [InlineKeyboardButton(text="ℹ️ Yordam", callback_data="help")]
        ]
    )


def back_button():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Bosh menyu", callback_data="home")]
        ]
    )


# ============================================================
# HANDLERS
# ============================================================

async def send_home(message):
    anonymous_code = save_user(message.from_user)
    username = await get_bot_username()
    anonymous_link = f"https://t.me/{username}?start=msg_{anonymous_code}"

    text = (
        f"👋 <b>{BOT_NAME}</b>ga xush kelibsiz!\n\n"
        "📥 <b>Media yuklash</b>\n"
        "Instagram, TikTok, YouTube va boshqa ochiq havolalarni yuboring.\n\n"
        "🎵 <b>Musiqa</b>\n"
        "Audio olinadigan havolalarni 'audio: link' ko'rinishida yuborishingiz mumkin.\n\n"
        "✉️ <b>Sizning anonim linkingiz:</b>\n"
        f"<code>{anonymous_link}</code>\n\n"
        "Linkni do'stlaringizga yuboring. Ular sizga anonim xabar yuborishi mumkin."
    )
    await message.answer(text, reply_markup=main_menu())


@dp.message(CommandStart())
async def start_handler(message: Message):
    save_user(message.from_user)
    parts = (message.text or "").split(maxsplit=1)
    payload = parts[1].strip() if len(parts) == 2 else ""

    if payload.startswith("msg_"):
        anonymous_code = payload[4:]
        receiver = get_user_by_code(anonymous_code)

        if not receiver:
            await message.answer("❌ Bu anonim link mavjud emas.", reply_markup=main_menu())
            return

        if receiver["user_id"] == message.from_user.id:
            await message.answer("ℹ️ Bu sizning o'zingizning anonim linkingiz.", reply_markup=main_menu())
            return

        anonymous_sessions[message.from_user.id] = receiver["user_id"]
        await message.answer(
            "✉️ <b>Anonim xabar</b>\n\n"
            "Siz anonim xabar yubormoqdasiz.\n"
            "Xabaringizni yozing.\n"
            "Qabul qiluvchi sizning Telegram ma'lumotlaringizni ko'rmaydi.\n\n"
            "❌ Bekor qilish: /cancel"
        )
        return

    await send_home(message)


@dp.message(Command("help"))
async def help_command(message: Message):
    save_user(message.from_user)
    await message.answer(
        "ℹ️ <b>Yordam</b>\n\n"
        "📥 <b>Media yuklash:</b> Havolani yuboring.\n"
        "🎵 <b>Audio olish:</b> Havola boshiga <code>audio:</code> qo'shib yuboring.\n"
        "✉️ <b>Anonim xabar:</b> Linkingizni oling va tarqating.\n"
        "❌ <b>Bekor qilish:</b> /cancel"
    )


@dp.message(Command("myid"))
async def myid_command(message: Message):
    await message.answer(f"🆔 <b>Sizning Telegram ID'ingiz:</b>\n<code>{message.from_user.id}</code>")


@dp.message(Command("mylink"))
async def mylink_command(message: Message):
    anonymous_code = save_user(message.from_user)
    username = await get_bot_username()
    link = f"https://t.me/{username}?start=msg_{anonymous_code}"
    await message.answer(f"✉️ <b>Sizning anonim linkingiz:</b>\n\n<code>{link}</code>")


@dp.message(Command("cancel"))
async def cancel_command(message: Message):
    anonymous_sessions.pop(message.from_user.id, None)
    await message.answer("❌ Jarayon bekor qilindi.", reply_markup=main_menu())


# ============================================================
# CALLBACK HANDLERS
# ============================================================

@dp.callback_query(F.data == "home")
async def home_callback(callback: CallbackQuery):
    await callback.message.edit_text(f"🏠 <b>{BOT_NAME}</b>\n\nKerakli bo'limni tanlang:", reply_markup=main_menu())
    await callback.answer()


@dp.callback_query(F.data == "download")
async def download_callback(callback: CallbackQuery):
    await callback.message.answer("📥 <b>Havolani yuboring</b>\n\nInstagram, TikTok, YouTube havolasini yuboring.")
    await callback.answer()


@dp.callback_query(F.data == "my_link")
async def my_link_callback(callback: CallbackQuery):
    anonymous_code = save_user(callback.from_user)
    username = await get_bot_username()
    link = f"https://t.me/{username}?start=msg_{anonymous_code}"
    await callback.message.edit_text(f"✉️ <b>Mening anonim linkim:</b>\n\n<code>{link}</code>", reply_markup=back_button())
    await callback.answer()


@dp.callback_query(F.data == "help")
async def help_callback(callback: CallbackQuery):
    await callback.message.edit_text("ℹ️ <b>Yordam bo'limi</b>", reply_markup=back_button())
    await callback.answer()


# ============================================================
# ADMIN COMMANDS
# ============================================================

def is_admin(user_id):
    return ADMIN_ID != 0 and user_id == ADMIN_ID


@dp.message(Command("stats"))
async def stats_command(message: Message):
    if not is_admin(message.from_user.id):
        return
    connection = get_db()
    users_count = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    downloads_count = connection.execute("SELECT COUNT(*) AS count FROM downloads").fetchone()["count"]
    connection.close()

    await message.answer(f"📊 <b>BOT STATISTIKASI</b>\n\n👥 Foydalanuvchilar: <b>{users_count}</b>\n📥 Yuklamalar: <b>{downloads_count}</b>")


@dp.message(Command("broadcast"))
async def broadcast_command(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("📢 Foydalanish: <code>/broadcast Salom!</code>")
        return

    broadcast_text = parts[1].strip()
    connection = get_db()
    rows = connection.execute("SELECT user_id FROM users").fetchall()
    connection.close()

    sent, failed = 0, 0
    status = await message.answer("📢 Yuborish boshlandi...")

    for row in rows:
        try:
            await bot.send_message(row["user_id"], broadcast_text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await status.edit_text(f"📢 <b>Broadcast tugadi</b>\n\n✅ Yuborildi: {sent}\n❌ Xatolik: {failed}")


# ============================================================
# DOWNLOAD HELPERS & TEXT HANDLER
# ============================================================

def extract_url(text):
    if not text:
        return None
    match = re.search(r"https?://[^\s]+", text)
    return match.group(0).rstrip(".,!?)]}>") if match else None


def valid_url(url):
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


async def download_media(url, folder, audio=False):
    output_template = str(Path(folder)) + "/%(title).80s-%(id)s.%(ext)s"
    options = {
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "socket_timeout": 30,
        "restrictfilenames": True,
    }

    if audio:
        options["format"] = "bestaudio/best"
        options["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192"
        }]
    else:
        options["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        options["merge_output_format"] = "mp4"

    def run_download():
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise RuntimeError("Media topilmadi.")
            prepared = Path(ydl.prepare_filename(info))
            if audio:
                mp3_file = prepared.with_suffix(".mp3")
                if mp3_file.exists():
                    return mp3_file, info
            if prepared.exists():
                return prepared, info
            files = [item for item in Path(folder).iterdir() if item.is_file()]
            if not files:
                raise RuntimeError("Yuklangan fayl topilmadi.")
            return files[0], info

    return await asyncio.to_thread(run_download)


async def send_media(message, file_path, title, audio):
    extension = file_path.suffix.lower()
    if audio or extension in {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}:
        await message.answer_audio(audio=FSInputFile(file_path), caption=f"🎵 <b>{title}</b>")
        return
    if extension in {".mp4", ".mov", ".webm", ".mkv"}:
        await message.answer_video(video=FSInputFile(file_path), caption=f"🎬 <b>{title}</b>", supports_streaming=True)
        return
    await message.answer_document(document=FSInputFile(file_path), caption=f"📎 <b>{title}</b>")


@dp.message(F.text)
async def text_handler(message: Message):
    user_id = message.from_user.id
    save_user(message.from_user)

    # Anonim xabar
    if user_id in anonymous_sessions:
        receiver_id = anonymous_sessions.pop(user_id)
        text = message.text.strip()
        if not text:
            await message.answer("❌ Xabar bo'sh bo'lmasin.")
            return
        try:
            await bot.send_message(receiver_id, f"💌 <b>Sizga anonim xabar keldi:</b>\n\n{text}")
            await message.answer("✅ Xabar yuborildi.", reply_markup=main_menu())
        except TelegramForbiddenError:
            await message.answer("❌ Qabul qiluvchi botni bloklagan.")
        except Exception:
            await message.answer("❌ Xabar yuborishda xatolik yuz berdi.")
        return

    # Media Yuklash
    original_text = message.text.strip()
    audio_mode = original_text.lower().startswith("audio:")
    url = extract_url(original_text[6:] if audio_mode else original_text)

    if not url or not valid_url(url):
        await message.answer("❓ Noma'lum buyruq yoki xatoli xabar.\nMedia yuklash uchun to'g'ri havola (URL) yuboring.")
        return

    status = await message.answer("⏳ <b>Yuklanmoqda...</b>")
    temporary_folder = tempfile.mkdtemp(prefix="anonbox_")

    try:
        file_path, info = await download_media(url, temporary_folder, audio=audio_mode)
        if file_path.stat().st_size > MAX_FILE_BYTES:
            await status.edit_text(f"❌ Fayl hajmi juda katta. Limit: {MAX_FILE_MB} MB.")
            return

        title = (info.get("title") or "Media")[:800]
        save_download(user_id, url, "audio" if audio_mode else "video", title)
        await send_media(message, file_path, title, audio_mode)
        await status.delete()

    except Exception as error:
        logger.error("Downloader error: %r", error)
        try:
            await status.edit_text("❌ <b>Yuklab bo'lmadi.</b> Havola xususiy (private) yoki havola xato bo'lishi mumkin.")
        except Exception:
            pass
    finally:
        shutil.rmtree(temporary_folder, ignore_errors=True)


# ============================================================
# MAIN ENTRYPOINT
# ============================================================

async def main():
    init_database()
    logger.info("Bot muvaffaqiyatli ishga tushdi!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
