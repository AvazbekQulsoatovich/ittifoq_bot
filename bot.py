import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite

# 🔐 Sozlamalar
BOT_TOKEN = "8337937134:AAGiG2N__ZfAB0WHish3mJV9AE8DqMAw9fs"
CHANNEL_USERNAME = "@TerDU_Yoshlari"  # Kanal username
ADMIN_IDS = [61040584]  # Admin Telegram ID-lari

# 📦 Bot va Dispatcher
bot = Bot(BOT_TOKEN)
dp = Dispatcher()


# 🔌 Ma'lumotlar bazasi yaratish
async def init_db():
    async with aiosqlite.connect("data.db") as db:
        # Tanlovlar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS contests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                is_active INTEGER DEFAULT 0
            )
        """)

        # Videolar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                caption TEXT,
                message_id INTEGER
            )
        """)

        # Ovozlar jadvali
        await db.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                user_id INTEGER,
                video_id INTEGER NOT NULL,
                contest_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, contest_id)
            )
        """)

        # Agar aktiv tanlov bo‘lmasa, bittasini yaratamiz
        cursor = await db.execute("SELECT id FROM contests WHERE is_active = 1")
        row = await cursor.fetchone()
        if not row:
            await db.execute("INSERT INTO contests (is_active) VALUES (1)")
        await db.commit()


# 📌 Joriy aktiv tanlovni olish
async def get_active_contest_id():
    async with aiosqlite.connect("data.db") as db:
        cursor = await db.execute("SELECT id FROM contests WHERE is_active = 1")
        row = await cursor.fetchone()
        return row[0] if row else None


# ✅ Obuna tekshirish
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"Subscription check failed: {e}")
        return False


# 🎬 Videoni kanalga yuborish
async def send_video_to_channel(video_id: int, file_id: str, caption: str, contest_id: int):
    async with aiosqlite.connect("data.db") as db:
        async with db.execute("SELECT COUNT(*) FROM votes WHERE video_id = ? AND contest_id = ?", (video_id, contest_id)) as cursor:
            vote_count = (await cursor.fetchone())[0]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=f"❤️ Ovoz berish ({vote_count})",
                callback_data=f"vote_{video_id}"
            )
        ]]
    )

    msg = await bot.send_video(
        chat_id=CHANNEL_USERNAME,
        video=file_id,
        caption=caption,
        reply_markup=keyboard
    )

    async with aiosqlite.connect("data.db") as db:
        await db.execute("UPDATE videos SET message_id=? WHERE id=?", (msg.message_id, video_id))
        await db.commit()


# 🏁 /start komandasi
@dp.message(F.text == "/start")
async def start_cmd(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🆕 Yangi tanlovni boshlash", callback_data="new_contest")
            ]]
        )
        await message.answer("👋 Salom admin!\n\n📤 Kanal uchun video yuboring.", reply_markup=keyboard)
    else:
        await message.answer("❌ Siz admin emassiz.\nBu botdan faqat admin foydalana oladi.")


# 🎥 Admin video yuklashi
@dp.message(F.video)
async def upload_video(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Siz admin emassiz, video qo'sha olmaysiz.")
        return

    contest_id = await get_active_contest_id()
    file_id = message.video.file_id
    caption = message.caption or "Video"

    async with aiosqlite.connect("data.db") as db:
        cursor = await db.execute(
            "INSERT INTO videos (contest_id, file_id, caption) VALUES (?, ?, ?)",
            (contest_id, file_id, caption)
        )
        video_id = cursor.lastrowid
        await db.commit()

    await send_video_to_channel(video_id, file_id, caption, contest_id)
    await message.answer("✅ Video kanalga joylandi!")


# 🆕 Yangi tanlovni boshlash
@dp.callback_query(F.data == "new_contest")
async def new_contest(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("❌ Faqat admin yangi tanlov boshlashi mumkin.", show_alert=True)
        return

    async with aiosqlite.connect("data.db") as db:
        # Hamma eski tanlovlarni o‘chirib qo‘yamiz
        await db.execute("UPDATE contests SET is_active = 0")
        # Yangi tanlov yaratamiz
        await db.execute("INSERT INTO contests (is_active) VALUES (1)")
        await db.commit()

    await call.answer("🆕 Yangi tanlov boshlandi!", show_alert=True)
    await call.message.edit_text("✅ Yangi tanlov boshlandi!\nEndi yangi videolarni yuklashingiz mumkin.")


# 🗳 Ovoz berish handleri
@dp.callback_query(F.data.startswith("vote_"))
async def vote_handler(call: types.CallbackQuery):
    video_id = int(call.data.split("_")[1])
    user_id = call.from_user.id
    contest_id = await get_active_contest_id()

    # Avval obuna tekshiramiz
    if not await check_subscription(user_id):
        await call.answer("🛑 Avval kanalga obuna bo‘ling!", show_alert=True)
        return

    async with aiosqlite.connect("data.db") as db:
        # Shu foydalanuvchi shu tanlovda ovoz berganmi?
        async with db.execute("SELECT video_id FROM votes WHERE user_id = ? AND contest_id = ?", (user_id, contest_id)) as cursor:
            row = await cursor.fetchone()
            if row:
                await call.answer("❗ Siz allaqachon ovoz bergansiz!", show_alert=True)
                return

        # Yangi ovoz yozamiz
        await db.execute("INSERT INTO votes (user_id, video_id, contest_id) VALUES (?, ?, ?)", (user_id, video_id, contest_id))
        await db.commit()

        # Yangilangan ovozlar soni
        async with db.execute("SELECT COUNT(*) FROM votes WHERE video_id = ? AND contest_id = ?", (video_id, contest_id)) as cursor:
            vote_count = (await cursor.fetchone())[0]

    # Tugmani yangilash
    new_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=f"❤️ Ovoz berish ({vote_count})",
                callback_data=f"vote_{video_id}"
            )
        ]]
    )
    try:
        await call.message.edit_reply_markup(reply_markup=new_keyboard)
    except Exception as e:
        print(f"Tugma yangilash xatolik: {e}")

    await call.answer("✅ Ovoz berildi!")


# 🚀 Botni ishga tushirish
async def main():
    await init_db()
    print("Bot ishga tushmoqda...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
