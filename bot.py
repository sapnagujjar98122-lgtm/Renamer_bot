import os
import re
import asyncio
from pyrofork import Client, filters
from pyrofork.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrofork.enums import ParseMode

# ================= ENV =================

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID"))
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))

# ================= APP =================

app = Client(
    "EmpireUltimateBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=100
)

# ================= STORAGE =================

registered_channels = {}      # user_id: [channel_ids]
huge_sessions = {}            # user_id: session data
user_templates = {}           # rename template

DEFAULT_CAPTION = """<b>📺 {anime_name}
━━━━━━━━━━━━━━━━━━━
❖ Season: {season}
❖ Episode: {episode}
❖ Quality: {quality}p
━━━━━━━━━━━━━━━━━━━</b>"""

# ================= UTIL =================

def extract_data(text):
    data = {
        "anime_name": "Unknown",
        "season": "1",
        "episode": 0,
        "quality": 480
    }

    if not text:
        return data

    name = re.search(r"Anime\s*:\s*(.+)", text, re.I)
    if name:
        data["anime_name"] = name.group(1)

    ep = re.search(r"Episode\s*(\d+)", text, re.I)
    if ep:
        data["episode"] = int(ep.group(1))

    q = re.search(r"(\d{3,4})p", text)
    if q:
        data["quality"] = int(q.group(1))

    season = re.search(r"Season\s*(\d+)", text, re.I)
    if season:
        data["season"] = season.group(1)

    return data

def quality_order(q):
    order = [480, 720, 1080, 2160]
    return order.index(q) if q in order else 999

def format_caption(template, data):
    for k, v in data.items():
        template = template.replace(f"{{{k}}}", str(v))
    return template

# ================= START =================

@app.on_message(filters.command("start"))
async def start(_, msg):
    await msg.reply("🔥 Empire Ultimate Bot Active!")

# ================= ADD CHANNELS =================

@app.on_message(filters.command("add_channels"))
async def add_channels(_, msg):
    await msg.reply("📩 Resend any message from your channel with sender name")

@app.on_message(filters.forwarded)
async def save_channel(client, msg):

    user_id = msg.from_user.id
    chat = msg.forward_from_chat

    if not chat:
        return

    member_bot = await client.get_chat_member(chat.id, "me")
    member_user = await client.get_chat_member(chat.id, user_id)

    if member_bot.status not in ["administrator", "creator"]:
        return await msg.reply("❌ Bot must be admin in channel")

    if member_user.status not in ["administrator", "creator"]:
        return await msg.reply("❌ You must be admin of channel")

    if user_id not in registered_channels:
        registered_channels[user_id] = []

    if chat.id not in registered_channels[user_id]:
        registered_channels[user_id].append(chat.id)

    await msg.reply(f"✅ Channel Added: {chat.title}")

# ================= HUGE UPLOAD START =================

@app.on_message(filters.command("huge_upload"))
async def huge_upload_start(_, msg):
    huge_sessions[msg.from_user.id] = {"step": 1}
    await msg.reply("📩 Resend FIRST message from source channel")

# ================= HUGE STEPS =================

@app.on_message(filters.forwarded)
async def huge_steps(client, msg):

    user_id = msg.from_user.id

    if user_id not in huge_sessions:
        return

    session = huge_sessions[user_id]
    source_chat = msg.forward_from_chat

    if not source_chat:
        return

    if session["step"] == 1:
        session["first_id"] = msg.forward_from_message_id
        session["source_chat"] = source_chat.id
        session["step"] = 2
        return await msg.reply("📩 Resend LAST message from source channel")

    if session["step"] == 2:
        session["last_id"] = msg.forward_from_message_id
        session["step"] = 3

        channels = registered_channels.get(user_id, [])
        if not channels:
            return await msg.reply("❌ No registered channels. Use /add_channels")

        buttons = []
        for ch in channels:
            chat = await client.get_chat(ch)
            buttons.append([InlineKeyboardButton(chat.title, callback_data=f"upload_{ch}")])

        await msg.reply(
            "📢 Choose target channel",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

# ================= CALLBACK =================

@app.on_callback_query(filters.regex("upload_"))
async def process_upload(client, callback):

    user_id = callback.from_user.id
    target_channel = int(callback.data.split("_")[1])

    session = huge_sessions.get(user_id)
    if not session:
        return await callback.answer("Session expired", show_alert=True)

    await callback.message.edit_text("🚀 Processing Huge Upload...")

    source_chat = session["source_chat"]
    first_id = session["first_id"]
    last_id = session["last_id"]

    messages = []

    async for m in client.get_chat_history(source_chat, offset_id=last_id+1):
        if m.id < first_id:
            break
        messages.append(m)

    messages.reverse()

    media_list = []

    for m in messages:
        if m.video:
            data = extract_data(m.caption or "")
            media_list.append((data["episode"], quality_order(data["quality"]), m))

    media_list.sort(key=lambda x: (x[0], x[1]))

    for _, _, m in media_list:

        data = extract_data(m.caption or "")
        caption = format_caption(DEFAULT_CAPTION, data)

        sent = await client.copy_message(
            chat_id=target_channel,
            from_chat_id=source_chat,
            message_id=m.id,
            caption=caption,
            parse_mode=ParseMode.HTML
        )

        await sent.copy(LOG_GROUP_ID)

        await asyncio.sleep(0.4)

    await callback.message.edit_text("✅ Huge Upload Completed!")

    del huge_sessions[user_id]

print("🔥 Empire Ultimate Huge System Running...")
app.run()
