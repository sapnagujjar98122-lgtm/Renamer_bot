import re
import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message

# ================== ENV VARIABLES ==================

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Client(
    "CaptionRenameBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ================== MEMORY STORAGE ==================

user_templates = {}
user_queues = {}
user_processing = {}

# ================== DATA EXTRACTOR ==================

def extract_data(text: str):
    data = {
        "anime_name": "Unknown",
        "season": "Unknown",
        "episode": "Unknown",
        "audio": "Unknown",
        "quality": "Unknown"
    }

    patterns = {
        "anime_name": r"ᴀɴɪᴍᴇ:\s*(.*)",
        "season": r"Season:\s*(\d+)",
        "episode": r"Episode:\s*(\d+)",
        "quality": r"Quality:\s*(\d+p)",
        "audio": r"Audio:\s*(.*)"
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            data[key] = match.group(1).strip()

    return data

# ================== CAPTION FORMATTER ==================

def format_caption(template: str, data: dict):
    for key, value in data.items():
        template = template.replace(f"{{{key}}}", value)
    return template

# ================== COMMANDS ==================

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "💀 Caption Rename Bot Ready!\n\n"
        "Send multiple videos and I will resend in same order.\n\n"
        "Use:\n"
        "/setcaption YourTemplate\n"
        "/help for placeholders"
    )

@app.on_message(filters.command("help"))
async def help_cmd(client, message):
    await message.reply_text(
        "🛠 Available Placeholders:\n\n"
        "{anime_name}\n"
        "{season}\n"
        "{episode}\n"
        "{audio}\n"
        "{quality}\n\n"
        "Example:\n"
        "/setcaption Anime: {anime_name} | Ep: {episode}"
    )

@app.on_message(filters.command("setcaption"))
async def set_caption(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage:\n/setcaption Your Caption Template")

    template = message.text.split(" ", 1)[1]
    user_templates[message.from_user.id] = template
    await message.reply_text("✅ Custom caption saved successfully!")

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

# ================== QUEUE PROCESSOR ==================

async def process_queue(user_id):
    user_processing[user_id] = True

    while not user_queues[user_id].empty():
        message = await user_queues[user_id].get()

        original_caption = message.caption or ""
        data = extract_data(original_caption)

        template = user_templates.get(user_id)

        if template:
            new_caption = format_caption(template, data)
        else:
            new_caption = original_caption

        try:
            await message.reply_video(
                video=message.video.file_id,
                caption=new_caption
            )
        except Exception as e:
            print(f"Error: {e}")

        await asyncio.sleep(0.2)  # Speed control (anti flood)

    user_processing[user_id] = False

# ================== RUN BOT ==================

app.run()
