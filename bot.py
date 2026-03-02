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
    "UltimateCaptionBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ================== STORAGE ==================

user_templates = {}
user_media_buffer = {}
user_delay_task = {}

# ================== DATA EXTRACT ==================

def extract_data(text: str):
    data = {
        "anime_name": "Unknown",
        "season": "Unknown",
        "episode": 0,
        "audio": "Unknown",
        "quality": 0
    }

    if not text:
        return data

    # Anime Name
    name = re.search(r"[Aaᴀ][Nnɴ][Iiɪ][Mmᴍ][Eeᴇ]\s*:\s*(.+)", text)
    if name:
        data["anime_name"] = name.group(1).strip()

    # Season
    season = re.search(r"[Ss]eason\s*:?\.?\s*(\d+)", text)
    if season:
        data["season"] = season.group(1)

    # Episode
    ep = re.search(r"[Ee]pisode\s*:?\.?\s*(\d+)", text)
    if ep:
        data["episode"] = int(ep.group(1))

    # Quality
    ql = re.search(r"(\d{3,4})p", text)
    if ql:
        data["quality"] = int(ql.group(1))

    # Audio
    audio = re.search(r"[Aa]udio\s*:\s*(.+)", text)
    if audio:
        data["audio"] = audio.group(1).strip()

    return data

# ================== FORMAT CAPTION ==================

def format_caption(template: str, data: dict):
    for key, value in data.items():
        template = template.replace(f"{{{key}}}", str(value))
    return template

# ================== QUALITY ORDER ==================

def quality_order(q):
    order = [480, 720, 1080, 2160]
    return order.index(q) if q in order else 999

# ================== COMMANDS ==================

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "🔥 Ultimate Caption Rename Bot Ready!\n\n"
        "Send multiple videos.\n"
        "Bot will wait 2 seconds and resend in correct episode & quality order.\n\n"
        "Use /setcaption to set custom caption\n"
        "Use /help for placeholders"
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
        "/setcaption <blockquote>{anime_name}</blockquote>\n"
        "Ep {episode} - {quality}p"
    )

@app.on_message(filters.command("setcaption"))
async def set_caption(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage:\n/setcaption Your Caption Template")

    template = message.text.split(" ", 1)[1]
    user_templates[message.from_user.id] = template
    await message.reply_text("✅ Caption Template Saved Successfully!")

# ================== VIDEO HANDLER ==================

@app.on_message(filters.video)
async def video_handler(client, message: Message):
    user_id = message.from_user.id

    if user_id not in user_media_buffer:
        user_media_buffer[user_id] = []

    user_media_buffer[user_id].append(message)

    # Cancel previous delay if running
    if user_id in user_delay_task:
        user_delay_task[user_id].cancel()

    user_delay_task[user_id] = asyncio.create_task(process_after_delay(user_id))

# ================== PROCESS AFTER DELAY ==================

async def process_after_delay(user_id):
    await asyncio.sleep(2)

    messages = user_media_buffer.get(user_id, [])
    if not messages:
        return

    media_list = []

    for msg in messages:
        data = extract_data(msg.caption or "")
        media_list.append((data["episode"], quality_order(data["quality"]), msg))

    # Sort by episode then quality order
    media_list.sort(key=lambda x: (x[0], x[1]))

    for _, _, msg in media_list:
        original_caption = msg.caption or ""
        template = user_templates.get(user_id)

        data = extract_data(original_caption)
        new_caption = format_caption(template, data) if template else original_caption

        try:
            await app.copy_message(
                chat_id=msg.chat.id,
                from_chat_id=msg.chat.id,
                message_id=msg.id,
                caption=new_caption,
                parse_mode=ParseMode.HTML
            )
            await asyncio.sleep(0.4)
        except Exception as e:
            print("Copy Error:", e)

    user_media_buffer[user_id] = []

print("🔥 Ultimate Advanced Bot Running Successfully")
app.run()
