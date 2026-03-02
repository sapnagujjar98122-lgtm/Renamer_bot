import re
import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

# ================== ENV ==================

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client(
    "CaptionRenameBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ================== STORAGE ==================

user_templates = {}
user_queues = {}
user_processing = {}

# ================== DATA EXTRACT ==================

def extract_data(text: str):
    data = {
        "anime_name": "Unknown",
        "season": "Unknown",
        "episode": "Unknown",
        "audio": "Unknown",
        "quality": "Unknown"
    }

    patterns = {
        "anime_name": r"ANIME\s*[:•]\s*(.+)",
        "season": r"Season\s*[:•]\s*(\d+)",
        "episode": r"Episode\s*[:•]\s*(\d+)",
        "quality": r"Quality\s*[:•]\s*([0-9p •]+)",
        "audio": r"Audio\s*[:•]\s*(.+)"
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data[key] = match.group(1).strip()

    return data

# ================== FORMAT ==================

def format_caption(template: str, data: dict):
    for key, value in data.items():
        template = template.replace(f"{{{key}}}", value)
    return template

# ================== COMMANDS ==================

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "🔥 PyroFork HTML Caption Bot Ready!\n\n"
        "Use:\n"
        "/setcaption YourTemplate\n\n"
        "Supports HTML + <blockquote>\n\n"
        "Placeholders:\n"
        "{anime_name}\n"
        "{season}\n"
        "{episode}\n"
        "{audio}\n"
        "{quality}"
    )

@app.on_message(filters.command("setcaption"))
async def set_caption(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage:\n/setcaption Your Caption")

    template = message.text.split(" ", 1)[1]
    user_templates[message.from_user.id] = template
    await message.reply_text("✅ Custom caption saved!")

# ================== VIDEO HANDLER ==================

@app.on_message(filters.video)
async def video_handler(client, message: Message):
    user_id = message.from_user.id

    if user_id not in user_queues:
        user_queues[user_id] = asyncio.Queue()
        user_processing[user_id] = False

    await user_queues[user_id].put(message)

    if not user_processing[user_id]:
        asyncio.create_task(process_queue(user_id))

# ================== QUEUE SYSTEM ==================

async def process_queue(user_id):
    user_processing[user_id] = True

    while not user_queues[user_id].empty():
        message = await user_queues[user_id].get()

        original_caption = message.caption or ""
        data = extract_data(original_caption)

        template = user_templates.get(user_id)
        new_caption = format_caption(template, data) if template else original_caption

        try:
            await message.reply_video(
                video=message.video.file_id,
                caption=new_caption,
                parse_mode="html"   # ✅ PyroFork supports this directly
            )
        except Exception as e:
            print("Send Error:", e)
            await message.reply_video(
                video=message.video.file_id,
                caption=new_caption
            )

        await asyncio.sleep(0.2)

    user_processing[user_id] = False

print("🔥 Bot Running Successfully (PyroFork HTML Mode)")
app.run()
