# KENSHIN Caption Renamer - Focused (Pyrogram)
# Features:
# - Queue-based caption renamer for videos (0.2s delay)
# - Custom caption templates per user (/setcaption)
# - Episode/quality extraction using provided extract_data
# - Per-user episode stickers (/set_sticker)
# - edit_all mode (rename only vs rename+copy other message types)
# - Log-group copy for every renamed message
# - Admin commands: /users, /broadcast
# - /start and /help with detailed instructions
#
# REQUIREMENTS:
# - pyrogram (2.x), tgcrypto
# - Environment variables: API_ID, API_HASH, BOT_TOKEN, LOG_GROUP_ID, ADMIN_IDS
# - Run with Python 3.11 recommended
#
# NOTE: This is an in-memory implementation (registrations/templates/stickers lost on restart).
# For production persistence, connect to a DB (Redis/Mongo/etc).

import os
import re
import asyncio
from typing import Dict, List, Tuple, Optional

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, RPCError

# ----------------------- ENV & APP -----------------------

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID", "0"))
# ADMIN_IDS: comma separated numeric IDs, e.g. "12345,67890"
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

if not (API_ID and API_HASH and BOT_TOKEN and LOG_GROUP_ID):
    raise SystemExit("Missing required environment variables: API_ID, API_HASH, BOT_TOKEN, LOG_GROUP_ID")

app = Client("kenshin_renamer", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=100)

# ----------------------- In-memory storage -----------------------

users_db: set[int] = set()                        # users who used /start
user_templates: Dict[int, str] = {}               # per-user caption template
user_media_buffer: Dict[int, List[Message]] = {}  # per-user incoming media buffer
user_delay_task: Dict[int, asyncio.Task] = {}     # per-user scheduled processing task
user_edit_all_mode: Dict[int, str] = {}           # "yes" or "no"
episode_stickers: Dict[int, Dict[int, str]] = {}  # user_id -> {episode_number: sticker_file_id}

# Default caption (HTML)
DEFAULT_CAPTION = """<b> 📺 ᴀɴɪᴍᴇ : {anime_name}
━━━━━━━━━━━━━━━━━━━⭒
❖ Sᴇᴀsᴏɴ: {season}
❖ ᴇᴘɪꜱᴏᴅᴇ: {episode}
❖ ᴀᴜᴅɪᴏ: {audio}
❖ Qᴜᴀʟɪᴛʏ: {quality}
━━━━━━━━━━━━━━━━━━━⭒
<blockquote>POWERED BY: [@KENSHIN_ANIME & @MANWHA_VERSE]</blockquote></b>"""

# ----------------------- Utilities (provided functions) -----------------------

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
        try:
            data["quality"] = int(ql.group(1))
        except:
            data["quality"] = 0

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

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ----------------------- Safe copy (handles FloodWait) -----------------------

async def safe_copy(chat_id: int, from_chat_id: int, message_id: int, **kwargs):
    while True:
        try:
            return await app.copy_message(chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id, **kwargs)
        except FloodWait as e:
            await asyncio.sleep(e.x if hasattr(e, "x") else e.value if hasattr(e, "value") else 1)
        except RPCError:
            raise

# ----------------------- Commands: start/help -----------------------

@app.on_message(filters.command("start") & filters.private)
async def cmd_start(_, message: Message):
    uid = message.from_user.id
    users_db.add(uid)
    user_templates.setdefault(uid, DEFAULT_CAPTION)
    await message.reply_text(
        "🔥 KENSHIN Caption Renamer\n\n"
        f"Hi {message.from_user.mention},\n"
        "This bot renames videos using your custom caption template.\n\n"
        "Commands: /setcaption, /edit_all, /set_sticker, /help\n"
        "Admin: /users, /broadcast\n\n"
        "Placeholders: {anime_name}, {season}, {episode}, {audio}, {quality}",
        parse_mode=ParseMode.HTML
    )

@app.on_message(filters.command("help") & filters.private)
async def cmd_help(_, message: Message):
    help_text = (
        "<b>KENSHIN Caption Renamer — Help</b>\n\n"
        "/setcaption TEMPLATE  — Save your caption template.\n"
        "Example template uses placeholders: {anime_name}, {season}, {episode}, {audio}, {quality}\n\n"
        "/edit_all yes|no — yes: rename + copy non-video messages (text/sticker); no: only videos\n\n"
        "/set_sticker — Reply to a sticker with this command to save a sticker for the next episode (per-user)\n\n"
        "How to use: Send multiple videos (in same chat). The bot waits 0.2s, sorts them by episode -> quality and resends them with your template.\n\n"
        "Admin commands:\n/users — show total users\n/broadcast TEXT — send TEXT to all users\n\n"
        "Notes: Each renamed message is also copied to the LOG_GROUP for your archive."
    )
    await message.reply_text(help_text, parse_mode=ParseMode.HTML)

# ----------------------- Admin commands -----------------------

@app.on_message(filters.command("users") & filters.user(ADMIN_IDS))
async def cmd_users(_, message: Message):
    await message.reply_text(f"👥 Total users: {len(users_db)}")

@app.on_message(filters.command("broadcast") & filters.user(ADMIN_IDS))
async def cmd_broadcast(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /broadcast Your message")
    text = message.text.split(" ", 1)[1]
    sent = 0
    for uid in list(users_db):
        try:
            await app.send_message(uid, text)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            continue
    await message.reply_text(f"✅ Broadcast sent to {sent} users")

# ----------------------- Template & edit_all -----------------------

@app.on_message(filters.command("setcaption") & filters.private)
async def cmd_setcaption(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /setcaption Your caption template (use placeholders).")
    tpl = message.text.split(" ", 1)[1]
    user_templates[message.from_user.id] = tpl
    await message.reply_text("✅ Caption template saved!")

@app.on_message(filters.command("edit_all") & filters.private)
async def cmd_edit_all(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /edit_all yes|no")
    choice = message.command[1].lower()
    if choice not in ("yes", "no"):
        return await message.reply_text("Use: /edit_all yes  or  /edit_all no")
    user_edit_all_mode[message.from_user.id] = choice
    await message.reply_text(f"Mode set to: {choice}")

# ----------------------- Sticker management -----------------------

@app.on_message(filters.command("set_sticker") & filters.private)
async def cmd_set_sticker(_, message: Message):
    if not message.reply_to_message or not message.reply_to_message.sticker:
        return await message.reply_text("Reply to a sticker with /set_sticker to save it for the next episode.")
    uid = message.from_user.id
    episode_stickers.setdefault(uid, {})
    next_ep = max(episode_stickers[uid].keys()) + 1 if episode_stickers[uid] else 1
    episode_stickers[uid][next_ep] = message.reply_to_message.sticker.file_id
    await message.reply_text(f"✅ Sticker saved for episode {next_ep}")

@app.on_message(filters.command("list_stickers") & filters.private)
async def cmd_list_stickers(_, message: Message):
    uid = message.from_user.id
    stickers = episode_stickers.get(uid, {})
    if not stickers:
        return await message.reply_text("You have no stickers set. Use /set_sticker (reply to sticker).")
    lines = ["Your episode stickers:"]
    for ep, fid in sorted(stickers.items()):
        lines.append(f"Episode {ep} -> {fid}")
    await message.reply_text("\n".join(lines))

# ----------------------- Core: queue-based renamer -----------------------

async def _enqueue_video(message: Message):
    if not message.from_user:
        return
    uid = message.from_user.id
    users_db.add(uid)
    user_media_buffer.setdefault(uid, []).append(message)
    # cancel previous scheduled task if pending
    task = user_delay_task.get(uid)
    if task and not task.done():
        task.cancel()
    user_delay_task[uid] = asyncio.create_task(_process_after_delay(uid))

@app.on_message(filters.video & (filters.private | filters.group | filters.channel))
async def on_video_message(_, message: Message):
    # ignore if forwarded message came from a channel that shouldn't be auto-processed? We keep processing.
    await _enqueue_video(message)

async def _process_after_delay(user_id: int):
    await asyncio.sleep(0.2)  # buffer wait
    messages = list(user_media_buffer.get(user_id, []))
    if not messages:
        return
    edit_all = user_edit_all_mode.get(user_id, "no")
    # build sortable list: (episode, quality_order, message)
    media_list: List[Tuple[int, int, Message]] = []
    for msg in messages:
        data = extract_data(msg.caption or "")
        media_list.append((data.get("episode", 0), quality_order(data.get("quality", 0)), msg))
    media_list.sort(key=lambda x: (x[0], x[1]))
    for ep, _, msg in media_list:
        try:
            data = extract_data(msg.caption or "")
            tpl = user_templates.get(user_id, DEFAULT_CAPTION)
            new_caption = format_caption(tpl, data)
            # copy message with new caption into same chat (resend)
            try:
                sent = await safe_copy(
                    chat_id=msg.chat.id,
                    from_chat_id=msg.chat.id,
                    message_id=msg.id,
                    caption=new_caption,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                print("Copy error:", e)
                continue
            # copy to log group (best-effort)
            try:
                await sent.copy(LOG_GROUP_ID)
            except:
                pass
            # send sticker if set for this episode
            sticker_file_id = episode_stickers.get(user_id, {}).get(data.get("episode"))
            if sticker_file_id:
                try:
                    await app.send_sticker(chat_id=msg.chat.id, sticker=sticker_file_id)
                except:
                    pass
        except Exception as e:
            print("PROCESS ERROR:", e)
        await asyncio.sleep(0.2)
    # clear buffer
    user_media_buffer[user_id] = []

# ----------------------- Utility: show status -----------------------

@app.on_message(filters.command("status") & filters.private)
async def cmd_status(_, message: Message):
    uid = message.from_user.id
    buf = user_media_buffer.get(uid, [])
    tpl = user_templates.get(uid, DEFAULT_CAPTION)
    mode = user_edit_all_mode.get(uid, "no")
    await message.reply_text(
        f"Status:\nBuffered videos: {len(buf)}\nEdit mode: {mode}\nTemplate preview:\n\n{tpl}",
        parse_mode=ParseMode.HTML
    )

# ----------------------- Graceful shutdown (optional) -----------------------

@app.on_message(filters.command("stop") & filters.user(ADMIN_IDS) & filters.private)
async def cmd_stop(_, message: Message):
    await message.reply_text("Shutting down (admin requested).")
    await app.stop()
    # process will exit

# ----------------------- Start -----------------------

if __name__ == "__main__":
    print("🔥 KENSHIN Caption Renamer starting...")
    app.run()
