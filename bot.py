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

ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID"))

# ================== APP ==================

app = Client(
    "UltimateAnimeBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ================== STORAGE ==================

users_db = set()
user_templates = {}
user_media_buffer = {}
user_delay_task = {}
user_edit_all_mode = {}

# ================== DEFAULT CAPTION ==================

DEFAULT_CAPTION = """<b> 📺 ᴀɴɪᴍᴇ : {anime_name}
━━━━━━━━━━━━━━━━━━━⭒
❖ Sᴇᴀsᴏɴ: {season}
❖ ᴇᴘɪꜱᴏᴅᴇ: {episode}
❖ ᴀᴜᴅɪᴏ: {audio}
❖ Qᴜᴀʟɪᴛʏ: {quality}
━━━━━━━━━━━━━━━━━━━⭒
<blockquote>POWERED BY: [@KENSHIN_ANIME & @MANWHA_VERSE]</blockquote></b>"""

# ================== UTIL FUNCTIONS ==================

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

    name = re.search(r"[Aaᴀ][Nnɴ][Iiɪ][Mmᴍ][Eeᴇ]\s*:\s*(.+)", text)
    if name:
        data["anime_name"] = name.group(1).strip()

    season = re.search(r"[Ss]eason\s*:?\.?\s*(\d+)", text)
    if season:
        data["season"] = season.group(1)

    ep = re.search(r"[Ee]pisode\s*:?\.?\s*(\d+)", text)
    if ep:
        data["episode"] = int(ep.group(1))

    ql = re.search(r"(\d{3,4})p", text)
    if ql:
        data["quality"] = int(ql.group(1))

    audio = re.search(r"[Aa]udio\s*:\s*(.+)", text)
    if audio:
        data["audio"] = audio.group(1).strip()

    return data

def format_caption(template: str, data: dict):
    for key, value in data.items():
        template = template.replace(f"{{{key}}}", str(value))
    return template

def quality_order(q):
    order = [480, 720, 1080, 2160]
    return order.index(q) if q in order else 999

def is_admin(user_id):
    return user_id in ADMIN_IDS

# ================== START ==================

@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    users_db.add(user_id)

    if user_id not in user_templates:
        user_templates[user_id] = DEFAULT_CAPTION

    text = f"""🔥 Advance Caption Bot.

Hi {message.from_user.mention},
Welcome to our bot. This bot is specially maked for anime uploaders and here you can rename any videos with your own caption in seconds.

My Owner : @Kenshin_anime_owner
For any help : @KENSHIN_ANIME_CHAT"""

    await message.reply_text(text, parse_mode=ParseMode.HTML)

# ================== HELP ==================

@app.on_message(filters.command("help"))
async def help_cmd(client, message):
    help_text = """
<b>🔥 COMPLETE BOT GUIDE</b>

📌 How It Works:
• Send multiple videos.
• Bot waits 2 seconds.
• Automatically sorts:
Episode → 480p → 720p → 1080p → 2160p

📌 Commands:
/setcaption - Set your custom caption
/edit_all yes - Rename + resend all messages
/edit_all no - Rename only videos
/users - Total users (Admin)
/broadcast - Send message to all users (Admin)

📌 Placeholders:
{anime_name}
{season}
{episode}
{audio}
{quality}

📌 Extra Features:
• Original messages auto deleted
• Renamed videos auto stored in log group
• Smart quality sorting
• HTML formatting supported
"""

    await message.reply_text(help_text, parse_mode=ParseMode.HTML)

# ================== ADMIN COMMANDS ==================

@app.on_message(filters.command("users"))
async def users_cmd(client, message):
    if not is_admin(message.from_user.id):
        return
    await message.reply_text(f"👥 Total Users: {len(users_db)}")

@app.on_message(filters.command("broadcast"))
async def broadcast(client, message):
    if not is_admin(message.from_user.id):
        return

    if len(message.command) < 2:
        return await message.reply_text("Usage: /broadcast your message")

    text = message.text.split(" ", 1)[1]
    count = 0

    for user in users_db:
        try:
            await app.send_message(user, text)
            count += 1
        except:
            pass

    await message.reply_text(f"✅ Broadcast Sent to {count} users")

# ================== SET CAPTION ==================

@app.on_message(filters.command("setcaption"))
async def set_caption(client, message):
    if len(message.command) < 2:
        return

    template = message.text.split(" ", 1)[1]
    user_templates[message.from_user.id] = template
    await message.reply_text("✅ Caption Updated!")

# ================== EDIT ALL ==================

@app.on_message(filters.command("edit_all"))
async def edit_all_cmd(client, message):
    if len(message.command) < 2:
        return

    choice = message.command[1].lower()
    if choice not in ["yes", "no"]:
        return

    user_edit_all_mode[message.from_user.id] = choice
    await message.reply_text(f"Mode set to: {choice}")

# ================== COLLECT ==================

@app.on_message(filters.all & ~filters.command(["start","help","setcaption","edit_all","users","broadcast"]))
async def collect(client, message: Message):
    user_id = message.from_user.id

    if user_id not in user_media_buffer:
        user_media_buffer[user_id] = []

    user_media_buffer[user_id].append(message)

    if user_id in user_delay_task:
        user_delay_task[user_id].cancel()

    user_delay_task[user_id] = asyncio.create_task(process_after_delay(user_id))

# ================== PROCESS ==================

async def process_after_delay(user_id):
    await asyncio.sleep(2)

    messages = user_media_buffer.get(user_id, [])
    if not messages:
        return

    edit_all = user_edit_all_mode.get(user_id, "no")
    media_list = []

    for msg in messages:
        if msg.video:
            data = extract_data(msg.caption or "")
            media_list.append((data["episode"], quality_order(data["quality"]), msg))
        elif edit_all == "yes":
            media_list.append((9999, 9999, msg))

    media_list.sort(key=lambda x: (x[0], x[1]))

    for _, _, msg in media_list:
        try:
            if msg.video:
                data = extract_data(msg.caption or "")
                template = user_templates.get(user_id, DEFAULT_CAPTION)
                new_caption = format_caption(template, data)

                sent = await app.copy_message(
                    chat_id=msg.chat.id,
                    from_chat_id=msg.chat.id,
                    message_id=msg.id,
                    caption=new_caption,
                    parse_mode=ParseMode.HTML
                )

                await sent.copy(LOG_GROUP_ID)

            elif edit_all == "yes":
                await app.copy_message(
                    chat_id=msg.chat.id,
                    from_chat_id=msg.chat.id,
                    message_id=msg.id
                )

            await msg.delete()
            await asyncio.sleep(0.3)

        except Exception as e:
            print("Error:", e)

    user_media_buffer[user_id] = []

print("🔥 Production Secure Bot Running")
app.run()
