# =========================================================
# KENSHIN Caption Changer 2.01 - Full Extended
# =========================================================

import os, re, asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode

# ================== ENV ==================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID"))
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS","").split(",")))

# ================== APP ==================
app = Client(
    "KENSHINCaptionChanger2.01",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=100
)

# ================== STORAGE ==================
users_db = set()
user_templates = {}
user_media_buffer = {}
user_delay_task = {}
user_edit_all_mode = {}
registered_channels = {}  # user_id -> [channel_ids]
huge_sessions = {}  # user_id -> {"step":1, "first_msg":None, "last_msg":None}
episode_stickers = {}  # user_id -> {episode_number: sticker_file_id}

DEFAULT_CAPTION = """<b>📺 ᴀɴɪᴍᴇ : {anime_name}
━━━━━━━━━━━━━━━━━━━⭒
❖ Season: {season}
❖ Episode: {episode}
❖ Audio: {audio}
❖ Quality: {quality}p
━━━━━━━━━━━━━━━━━━━⭒
<blockquote>POWERED BY: [@KENSHIN_ANIME & @MANWHA_VERSE]</blockquote></b>"""

# ================== UTIL FUNCTIONS ==================
def is_admin(user_id):
    return user_id in ADMIN_IDS

def extract_data(text):
    data = {
        "anime_name": "Unknown",
        "season": "1",
        "episode": 0,
        "audio": "Unknown",
        "quality": 480,
        "synopsis": "N/A"
    }
    if not text: return data
    name = re.search(r"Anime\s*:\s*(.+)", text, re.I)
    if name: data["anime_name"]=name.group(1)
    season = re.search(r"Season\s*(\d+)", text, re.I)
    if season: data["season"]=season.group(1)
    ep = re.search(r"Episode\s*(\d+)", text, re.I)
    if ep: data["episode"]=int(ep.group(1))
    ql = re.search(r"(\d{3,4})p", text)
    if ql: data["quality"]=int(ql.group(1))
    audio = re.search(r"Audio\s*:\s*(.+)", text, re.I)
    if audio: data["audio"]=audio.group(1)
    synopsis = re.search(r"Synopsis\s*:\s*(.+)", text, re.I)
    if synopsis: data["synopsis"]=synopsis.group(1)
    return data

def format_caption(template, data):
    for k,v in data.items():
        template = template.replace(f"{{{k}}}", str(v))
    return template

def quality_order(q):
    order = [480,720,1080,2160]
    return order.index(q) if q in order else 999

# ================== START ==================
@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    users_db.add(user_id)
    if user_id not in user_templates:
        user_templates[user_id] = DEFAULT_CAPTION
    text=f"""🔥 KENSHIN Caption Changer 2.01

Hi {message.from_user.mention},
Welcome! Rename videos fast with your template.

Owner: @Kenshin_anime_owner
Help: @KENSHIN_ANIME_CHAT
"""
    await message.reply_text(text, parse_mode=ParseMode.HTML)

# ================== HELP ==================
@app.on_message(filters.command("help"))
async def help_cmd(client,message):
    help_text=f"""
<b>🔥 KENSHIN Caption Changer 2.01 - Guide</b>

📌 Commands:
/start - Welcome message
/help - This guide
/setcaption - Set your custom template
/edit_all yes/no - Rename only or rename+copy
/add_channels - Register your channels
/huge_upload - Huge upload from channel
/set_sticker - Set custom sticker for episodes
/users - Total users (Admin)
/broadcast - Broadcast message (Admin)

📌 Placeholders:
{{anime_name}}, {{season}}, {{episode}}, {{audio}}, {{quality}}, {{synopsis}}

📌 Features:
• Queue system with 0.2s delay
• Rename videos + log group copy
• Sticker per episode
• Multi-user safe
• HTML + blockquote supported
• Huge upload system: first→last messages from any channel
"""
    await message.reply_text(help_text, parse_mode=ParseMode.HTML)

# ================== ADMIN COMMANDS ==================
@app.on_message(filters.command("users"))
async def users_cmd(client,message):
    if not is_admin(message.from_user.id): return
    await message.reply_text(f"👥 Total Users: {len(users_db)}")

@app.on_message(filters.command("broadcast"))
async def broadcast(client,message):
    if not is_admin(message.from_user.id): return
    if len(message.command)<2: return await message.reply_text("Usage: /broadcast Your Message")
    text=message.text.split(" ",1)[1]
    count=0
    for user in users_db:
        try: await app.send_message(user,text); count+=1
        except: pass
    await message.reply_text(f"✅ Broadcast sent to {count} users")

# ================== TEMPLATE ==================
@app.on_message(filters.command("setcaption"))
async def set_caption(client,message):
    if len(message.command)<2: return await message.reply_text("Usage: /setcaption Your template")
    template=message.text.split(" ",1)[1]
    user_templates[message.from_user.id]=template
    await message.reply_text("✅ Caption Updated!")

@app.on_message(filters.command("edit_all"))
async def edit_all(client,message):
    if len(message.command)<2: return
        choice = message.command[1].lower()
        if choice not in ["yes","no"]: return
        user_edit_all_mode[message.from_user.id]=choice
        await message.reply_text(f"Mode set: {choice}")

# ================== STICKER ==================
@app.on_message(filters.command("set_sticker"))
async def set_sticker(client,message):
    if not message.reply_to_message: return await message.reply_text("Reply to a sticker to set")
    if message.from_user.id not in episode_stickers:
        episode_stickers[message.from_user.id]={}
    last_ep=len(episode_stickers[message.from_user.id])+1
    episode_stickers[message.from_user.id][last_ep]=message.reply_to_message.sticker.file_id
    await message.reply_text(f"✅ Sticker set for episode {last_ep}")

# ================== VIDEO QUEUE ==================
@app.on_message(filters.video)
async def video_handler(client,message):
    user_id=message.from_user.id
    if user_id not in user_media_buffer: user_media_buffer[user_id]=[]
    user_media_buffer[user_id].append(message)
    if user_id in user_delay_task: user_delay_task[user_id].cancel()
    user_delay_task[user_id]=asyncio.create_task(process_after_delay(user_id))

async def process_after_delay(user_id):
    await asyncio.sleep(0.2)
    messages=user_media_buffer.get(user_id,[])
    if not messages: return
    edit_all=user_edit_all_mode.get(user_id,"no")
    media_list=[]
    for msg in messages:
        data=extract_data(msg.caption or "")
        media_list.append((data["episode"],quality_order(data["quality"]),msg))
    media_list.sort(key=lambda x:(x[0],x[1]))
    for _,_,msg in media_list:
        data=extract_data(msg.caption or "")
        template=user_templates.get(user_id,DEFAULT_CAPTION)
        caption=format_caption(template,data)
        try:
            sent = await app.copy_message(
                chat_id=msg.chat.id,
                from_chat_id=msg.chat.id,
                message_id=msg.id,
                caption=caption,
                parse_mode=ParseMode.HTML
            )
            await sent.copy(LOG_GROUP_ID)
            ep_num=data["episode"]
            sticker_file_id = episode_stickers.get(user_id, {}).get(ep_num)
            if sticker_file_id:
                await app.send_sticker(msg.chat.id, sticker_file_id)
        except Exception as e: print("Error:",e)
        await asyncio.sleep(0.2)
    user_media_buffer[user_id]=[]

# ================== CHANNEL REGISTRATION & HUGE UPLOAD ==================
@app.on_message(filters.command("add_channels"))
async def add_channels(_,msg):
    await msg.reply("📩 Forward a message from your channel to register it.")

@app.on_message(filters.forwarded)
async def register_forward(client,msg):
    user_id=msg.from_user.id
    chat=msg.forward_from_chat
    if not chat: return
    member_bot = await client.get_chat_member(chat.id,"me")
    if member_bot.status not in ["administrator","creator"]:
        return await msg.reply("❌ Bot must be admin in channel")
    if user_id not in registered_channels: registered_channels[user_id]=[]
    if chat.id not in registered_channels[user_id]:
        registered_channels[user_id].append(chat.id)
    await msg.reply(f"✅ Channel Added: {chat.title}")

@app.on_message(filters.command("huge_upload"))
async def huge_upload_start(_,msg):
    huge_sessions[msg.from_user.id]={"step":1}
    await msg.reply("📩 Forward FIRST message from source channel to start huge upload")

# ================== RUN BOT ==================
print("🔥 KENSHIN Caption Changer 2.01 Running")
app.run()
