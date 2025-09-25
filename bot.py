import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import aiosqlite

# 🔐 Sozlamalar
BOT_TOKEN = "8337937134:AAGiG2N__ZfAB0WHish3mJV9AE8DqMAw9fs"
CHANNEL_USERNAME = "@sizkimsiza"  # Kanal username
ADMIN_IDS = [8133521082]  # Admin Telegram ID-lari

# 📦 Bot va Dispatcher
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# 🔌 Ma'lumotlar bazasi yaratish
async def init_db():
    async with aiosqlite.connect("data.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT,
                caption TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                user_id INTEGER UNIQUE,
                video_id INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY
            )
        """)
        await db.commit()

# ✅ Obuna tekshirish
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Subscription check failed: {e}")
        return False

# 🎥 Admin video yuklashi
@dp.message(F.video)
async def upload_video(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Siz admin emassiz, video qo'sha olmaysiz.")
        return

    file_id = message.video.file_id
    caption = message.caption or "Video"

    async with aiosqlite.connect("data.db") as db:
        await db.execute("INSERT INTO videos (file_id, caption) VALUES (?, ?)", (file_id, caption))
        await db.commit()

    await message.answer("✅ Video qo‘shildi va barcha obunachilarga yuborilmoqda...")

    # 📢 Barcha foydalanuvchilarga yuborish
    async with aiosqlite.connect("data.db") as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()

    for (uid,) in users:
        try:
            await send_video_with_vote(uid, uid, message.message_id, file_id, caption)
        except Exception as e:
            print(f"Foydalanuvchiga yuborishda xatolik: {e}")

# 🎬 Video ko‘rsatish (ovoz berish va o‘chirish tugmalari bilan)
async def send_video_with_vote(chat_id: int, user_id: int, video_id: int, file_id: str, caption: str):
    async with aiosqlite.connect("data.db") as db:
        # Ovozlar sonini olish
        async with db.execute("SELECT COUNT(*) FROM votes WHERE video_id = ?", (video_id,)) as cursor:
            vote_count = (await cursor.fetchone())[0]

        # Foydalanuvchi ovoz berganmi?
        async with db.execute("SELECT * FROM votes WHERE user_id = ?", (user_id,)) as cursor:
            has_voted = await cursor.fetchone()

    # 🔑 Tugmalar
    buttons = []
    if not has_voted:
        buttons.append([InlineKeyboardButton(text=f"❤️ Ovoz berish ({vote_count})", callback_data=f"vote_{video_id}")])
    if user_id in ADMIN_IDS:
        buttons.append([InlineKeyboardButton(text="🗑 Videoni o‘chirish", callback_data=f"delete_{video_id}")])

    if buttons:
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await bot.send_video(chat_id, file_id, caption=caption, reply_markup=keyboard)
    else:
        await bot.send_video(chat_id, file_id, caption=f"{caption}\n\n📊 Ovozlar: {vote_count}")

# 🎬 /start komandasi
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    subscribed = await check_subscription(message.from_user.id)
    if not subscribed:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Kanalga obuna bo‘lish", url=f"https://t.me/{CHANNEL_USERNAME.strip('@')}")],
            [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")]
        ])
        await message.answer("🛑 Ovoz berishdan avval kanalga obuna bo‘ling:", reply_markup=keyboard)
        return

    # 🔖 Foydalanuvchini bazaga yozamiz
    async with aiosqlite.connect("data.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()

    async with aiosqlite.connect("data.db") as db:
        async with db.execute("SELECT * FROM videos") as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.answer("Hozircha video mavjud emas.")
        return

    for video in rows:
        video_id, file_id, caption = video
        await send_video_with_vote(message.chat.id, message.from_user.id, video_id, file_id, caption)

# 🔁 Obunani qayta tekshirish tugmasi
@dp.callback_query(F.data == "check_sub")
async def recheck_sub(call: types.CallbackQuery):
    subscribed = await check_subscription(call.from_user.id)
    if not subscribed:
        await call.answer("❌ Hali obuna bo‘lmagansiz.", show_alert=True)
    else:
        # 🔖 Foydalanuvchini bazaga qo‘shamiz
        async with aiosqlite.connect("data.db") as db:
            await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (call.from_user.id,))
            await db.commit()

        await call.message.delete()
        await call.message.answer("✅ Obuna tasdiqlandi.")

        # Obuna bo‘lgach videolarni yuborish
        async with aiosqlite.connect("data.db") as db:
            async with db.execute("SELECT * FROM videos") as cursor:
                rows = await cursor.fetchall()

        for video in rows:
            video_id, file_id, caption = video
            await send_video_with_vote(call.message.chat.id, call.from_user.id, video_id, file_id, caption)

# 🗳 Ovoz berish handleri
@dp.callback_query(F.data.startswith("vote_"))
async def vote_handler(call: types.CallbackQuery):
    video_id = int(call.data.split("_")[1])
    user_id = call.from_user.id

    async with aiosqlite.connect("data.db") as db:
        # Tekshirish
        async with db.execute("SELECT * FROM votes WHERE user_id = ?", (user_id,)) as cursor:
            if await cursor.fetchone():
                await call.answer("❗️ Siz allaqachon ovoz bergansiz.", show_alert=True)
                return

        # Ovoz qo'shish
        await db.execute("INSERT INTO votes (user_id, video_id) VALUES (?, ?)", (user_id, video_id))
        await db.commit()

        # Yangi ovozlar soni
        async with db.execute("SELECT COUNT(*) FROM votes WHERE video_id = ?", (video_id,)) as count_cursor:
            vote_count = (await count_cursor.fetchone())[0]

        async with db.execute("SELECT file_id, caption FROM videos WHERE id = ?", (video_id,)) as video_cursor:
            video_data = await video_cursor.fetchone()

    # Inline tugmani olib tashlash
    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("✅ Ovoz berildi!")

    # Captionni yangilash
    new_caption = f"{video_data[1]}\n\n✅ Siz ovoz berdingiz!\n📊 Ovozlar: {vote_count}"
    try:
        await bot.edit_message_caption(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            caption=new_caption,
        )
    except Exception as e:
        print(f"Captionni yangilashda xatolik: {e}")

    await call.message.answer("🗳 Ovoz uchun rahmat!")

# 🗑 Videoni o‘chirish handleri
@dp.callback_query(F.data.startswith("delete_"))
async def delete_video(call: types.CallbackQuery):
    user_id = call.from_user.id
    if user_id not in ADMIN_IDS:
        await call.answer("❌ Siz admin emassiz!", show_alert=True)
        return

    video_id = int(call.data.split("_")[1])

    async with aiosqlite.connect("data.db") as db:
        await db.execute("DELETE FROM videos WHERE id = ?", (video_id,))
        await db.execute("DELETE FROM votes WHERE video_id = ?", (video_id,))
        await db.commit()

    try:
        await call.message.delete()
    except Exception as e:
        print(f"Xabarni o‘chirishda xatolik: {e}")

    await call.answer("🗑 Video o‘chirildi!", show_alert=True)

# 🏁 Botni ishga tushirish
async def main():
    await init_db()
    print("Bot ishga tushmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
