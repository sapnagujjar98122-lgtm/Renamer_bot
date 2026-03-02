import re
import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode

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

# ================== MEMORY ==================

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

    if not text:
        return data

    patterns = {
        "anime_name": r"[Aaᴀ][Nnɴ][Iiɪ][Mmᴍ][Eeᴇ]\s*:\s*(.+)",
        "season": r"[Ss]eason\s*:\s*(\d+)",
        "episode": r"[Ee]pisode\s*:\s*(\d+)",
        "quality": r"[Qq]uality\s*:\s*([\dPp]+)",
        "audio": r"[Aa]udio\s*:\s*(.+)"
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text)
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
    await message.reply_text("🔥 Pyrofork Caption Bot Ready!")

@app.on_message(filters.command("setcaption"))
async def set_caption(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage:\n/setcaption Your Template")

    template = message.text.split(" ", 1)[1]
    user_templates[message.from_user.id] = template
    await message.reply_text("✅ Caption Template Saved!")

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

# ================== QUEUE PROCESS ==================

async def process_queue(user_id):
    user_processing[user_id] = True

    while not user_queues[user_id].empty():
        message = await user_queues[user_id].get()

        original_caption = message.caption or ""
        data = extract_data(original_caption)

        template = user_templates.get(user_id)
        new_caption = format_caption(template, data) if template else original_caption

        try:
            await app.copy_message(
                chat_id=message.chat.id,
                from_chat_id=message.chat.id,
                message_id=message.id,
                caption=new_caption,
                parse_mode=ParseMode.HTML  # ✅ Correct way in Pyrofork
            )
        except Exception as e:
            print("Copy Error:", e)

        await asyncio.sleep(0.4)

    user_processing[user_id] = False

print("🔥 Pyrofork Bot Running Successfully")
app.run()
