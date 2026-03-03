# KENSHIN Caption Changer 2.02 (Pyrogram) — full extended working code
# Features:
# - /start, /help, /setcaption, /edit_all, /set_sticker, /add_channels, /list_channels
# - /huge_upload (forward FIRST & LAST messages; choose target channel via inline buttons)
# - Queue-based video rename with 0.2s delay, episode/quality sorting
# - Per-user episode stickers, log-group copy, admin commands /users & /broadcast
# - Uses the exact extract_data/format_caption/quality_order/is_admin helpers you provided
# Notes:
# - Set environment variables: API_ID, API_HASH, BOT_TOKEN, LOG_GROUP_ID, ADMIN_IDS (comma separated)
# - Bot must be admin in channels you register and in target channels
# - This script keeps registrations in memory (restart clears them). Persist if needed.

import os
import re
import asyncio
from typing import Dict, Any, List, Tuple

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, RPCError

# ------------------ ENV / APP ------------------

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID", "0"))
# ADMIN_IDS should be a comma-separated list of numeric IDs, e.g. "12345,67890"
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

if not (API_ID and API_HASH and BOT_TOKEN and LOG_GROUP_ID):
    print("Missing required environment variables (API_ID/API_HASH/BOT_TOKEN/LOG_GROUP_ID). Exiting.")
    raise SystemExit(1)

app = Client("kenshin_v2", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=100)

# ------------------ STORAGE (in-memory) ------------------
# NOTE: For production across restarts, replace with persistent DB (Redis/Mongo/etc.)

users_db: set[int] = set()                       # all users who /start
user_templates: Dict[int, str] = {}              # per-user caption template
user_media_buffer: Dict[int, List[Message]] = {} # per-user incoming video buffer
user_delay_task: Dict[int, asyncio.Task] = {}    # per-user delayed processing task
user_edit_all_mode: Dict[int, str] = {}          # "yes" or "no"
registered_channels: Dict[int, Dict[int, str]] = {}  # user_id -> {channel_id: channel_title}
huge_sessions: Dict[int, Dict[str, Any]] = {}    # per-user huge_upload session state
episode_stickers: Dict[int, Dict[int, str]] = {} # user_id -> {episode_number: sticker_file_id}
user_sessions: Dict[int, Dict[str, Any]] = {}    # user_id -> {"mode": "normal"/"huge_upload"/"add_channel"}

# ------------------ Defaults ------------------

DEFAULT_CAPTION = """<b>📺 ᴀɴɪᴍᴇ : {anime_name}
━━━━━━━━━━━━━━━━━━━⭒
❖ Season: {season}
❖ Episode: {episode}
❖ Audio: {audio}
❖ Quality: {quality}
━━━━━━━━━━━━━━━━━━━⭒
<blockquote>POWERED BY: [@KENSHIN_ANIME & @MANWHA_VERSE]</blockquote></b>"""

# ------------------ Helper functions (as requested) ------------------

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

def is_admin(user_id: int):
    return user_id in ADMIN_IDS

# ------------------ Utilities ------------------

async def safe_copy(to_chat: int, from_chat: int, message_id: int, **kwargs):
    """Copy a message and handle FloodWait / RPC errors gracefully."""
    while True:
        try:
            copied = await app.copy_message(chat_id=to_chat, from_chat_id=from_chat, message_id=message_id, **kwargs)
            return copied
        except FloodWait as e:
            await asyncio.sleep(e.x)
        except RPCError as e:
            # non-retryable or unknown RPC error: raise so caller may continue
            raise

def get_user_mode(uid: int) -> str:
    return user_sessions.get(uid, {}).get("mode", "normal")

def set_user_mode(uid: int, mode: str):
    user_sessions[uid] = {"mode": mode}

def reset_user_mode(uid: int):
    user_sessions[uid] = {"mode": "normal"}

# ------------------ Commands: start/help ------------------

@app.on_message(filters.command("start") & filters.private)
async def cmd_start(client: Client, message: Message):
    uid = message.from_user.id
    users_db.add(uid)
    if uid not in user_templates:
        user_templates[uid] = DEFAULT_CAPTION
    reset_user_mode(uid)
    text = (
        "🔥 KENSHIN Caption Changer 2.02\n\n"
        f"Hi {message.from_user.mention},\n"
        "Welcome — this bot renames videos, does massive uploads, and manages channels.\n\n"
        "Owner: @Kenshin_anime_owner\n"
        "Help: /help\n\n"
        "Quick: Use /setcaption to set your caption template."
    )
    await message.reply_text(text, parse_mode=ParseMode.HTML)

@app.on_message(filters.command("help") & filters.private)
async def cmd_help(client: Client, message: Message):
    help_text = (
        "<b>KENSHIN Caption Changer 2.02 — Help</b>\n\n"
        "Commands (private chat):\n"
        "/start — Welcome\n"
        "/help — This help\n"
        "/setcaption Your template — Set caption template (placeholders below)\n"
        "/edit_all yes|no — yes: copy text/stickers too, no: only videos\n"
        "/set_sticker — Reply to a sticker to set next episode sticker\n"
        "/add_channels — Forward one message from each channel you own to register it\n"
        "/list_channels — Show your registered channels\n"
        "/huge_upload — Start huge upload flow (forward FIRST & LAST messages)\n\n"
        "Placeholders (use in caption templates):\n"
        "{anime_name}, {season}, {episode}, {audio}, {quality}\n\n"
        "Admin commands:\n"
        "/users — total users\n"
        "/broadcast TEXT — send TEXT to all users\n\n"
        "Notes:\n- Bot must be admin in channels you register and in target channels.\n- Registrations are in-memory (restart clears). Use persistent DB for production."
    )
    await message.reply_text(help_text, parse_mode=ParseMode.HTML)

# ------------------ Admin commands ------------------

@app.on_message(filters.command("users") & filters.user(ADMIN_IDS))
async def cmd_users(client: Client, message: Message):
    await message.reply_text(f"👥 Total users: {len(users_db)}")

@app.on_message(filters.command("broadcast") & filters.user(ADMIN_IDS))
async def cmd_broadcast(client: Client, message: Message):
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

# ------------------ Template & edit_all ------------------

@app.on_message(filters.command("setcaption") & filters.private)
async def cmd_setcaption(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /setcaption Your caption template")
    tpl = message.text.split(" ", 1)[1]
    user_templates[message.from_user.id] = tpl
    await message.reply_text("✅ Template saved")

@app.on_message(filters.command("edit_all") & filters.private)
async def cmd_edit_all(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /edit_all yes|no")
    choice = message.command[1].lower()
    if choice not in ["yes", "no"]:
        return await message.reply_text("Use: /edit_all yes  or  /edit_all no")
    user_edit_all_mode[message.from_user.id] = choice
    await message.reply_text(f"Mode set to: {choice}")

# ------------------ Sticker management ------------------

@app.on_message(filters.command("set_sticker") & filters.private)
async def cmd_set_sticker(client: Client, message: Message):
    # set sticker by replying to a sticker message; associates next episode number
    if not message.reply_to_message or not message.reply_to_message.sticker:
        return await message.reply_text("Reply to a sticker message with /set_sticker to save it.")
    uid = message.from_user.id
    episode_stickers.setdefault(uid, {})
    next_ep = max(episode_stickers[uid].keys()) + 1 if episode_stickers[uid] else 1
    episode_stickers[uid][next_ep] = message.reply_to_message.sticker.file_id
    await message.reply_text(f"✅ Sticker saved for episode {next_ep}")

# ------------------ Channel registration ------------------

@app.on_message(filters.command("add_channels") & filters.private)
async def cmd_add_channels(client: Client, message: Message):
    uid = message.from_user.id
    set_user_mode(uid, "add_channel")
    await message.reply_text("🔁 Forward one message from each channel you want to register (forward exactly one message from the channel). When done, send /done_channels")

@app.on_message(filters.command("done_channels") & filters.private)
async def cmd_done_channels(_, message: Message):
    uid = message.from_user.id
    reset_user_mode(uid)
    await message.reply_text("✅ Channel registration finished. Use /list_channels to see registered channels.")

@app.on_message(filters.forwarded & filters.private)
async def handle_forward_registration(client: Client, message: Message):
    uid = message.from_user.id
    mode = get_user_mode(uid := message.from_user.id)
    # Only accept forwarded messages while in add_channel mode
    if user_sessions.get(uid, {}).get("mode") != "add_channel":
        return
    chat = message.forward_from_chat
    if not chat:
        return await message.reply_text("Forward a message directly from the channel (not a forward-of-forward).")
    # verify bot is admin in that channel
    try:
        bot_member = await client.get_chat_member(chat.id, "me")
    except Exception as e:
        return await message.reply_text("Failed to query channel. Make sure bot is added to that channel.")
    if bot_member.status not in ("administrator", "creator"):
        return await message.reply_text("❌ I must be admin in that channel to register it. Make me admin and forward again.")
    # verify the forwarder is admin too (best-effort)
    try:
        user_member = await client.get_chat_member(chat.id, message.from_user.id)
        if user_member.status not in ("administrator", "creator"):
            # not strictly required, but earlier user wanted to be admin
            await message.reply_text("You are not an admin in that channel (bot still registered it).")
    except:
        # ignore if API can't fetch (private)
        pass
    registered_channels.setdefault(message.from_user.id, {})
    registered_channels[message.from_user.id][chat.id] = chat.title or str(chat.id)
    await message.reply_text(f"✅ Registered channel: {chat.title or chat.id}")

@app.on_message(filters.command("list_channels") & filters.private)
async def cmd_list_channels(client: Client, message: Message):
    uid = message.from_user.id
    chans = registered_channels.get(uid, {})
    if not chans:
        return await message.reply_text("You have no registered channels. Use /add_channels and forward a message from your channel.")
    text_lines = ["<b>Your registered channels:</b>"]
    for cid, title in chans.items():
        text_lines.append(f"• {title} — <code>{cid}</code>")
    await message.reply_text("\n".join(text_lines), parse_mode=ParseMode.HTML)

# ------------------ Video processing queue ------------------

@app.on_message(filters.video & filters.private)
async def handle_incoming_video_private(client: Client, message: Message):
    # For private chats — normal behaviour
    await _enqueue_video_for_user(message)

@app.on_message(filters.video & ~filters.private)
async def handle_incoming_video_other(client: Client, message: Message):
    # For groups/channels where bot receives videos directly (not forwarded)
    # Enqueue only if user is not in a special session (huge_upload/add_channel)
    uid = message.from_user.id if message.from_user else None
    if uid:
        mode = get_user_mode(uid)
        if mode in ("huge_upload", "add_channel"):
            return  # ignore normal processing while in session
    await _enqueue_video_for_user(message)

async def _enqueue_video_for_user(message: Message):
    # Accept videos sent by users (or in groups)
    # Identify owner by message.from_user (works for private and groups)
    if not message.from_user:
        return
    uid = message.from_user.id
    users_db.add(uid)
    if uid not in user_media_buffer:
        user_media_buffer[uid] = []
    user_media_buffer[uid].append(message)
    # schedule processing (cancel previous pending task)
    if uid in user_delay_task:
        user_delay_task[uid].cancel()
    user_delay_task[uid] = asyncio.create_task(_process_after_delay(uid))

async def _process_after_delay(user_id: int):
    # buffer wait
    await asyncio.sleep(0.2)
    messages = user_media_buffer.get(user_id, [])[:]
    if not messages:
        return
    edit_all = user_edit_all_mode.get(user_id, "no")
    # build sortable list
    media_list: List[Tuple[int, int, Message]] = []
    for msg in messages:
        data = extract_data(msg.caption or "")
        media_list.append((data.get("episode", 0), quality_order(data.get("quality", 0)), msg))
    media_list.sort(key=lambda x: (x[0], x[1]))
    # process in order
    for ep, _, msg in media_list:
        try:
            data = extract_data(msg.caption or "")
            template = user_templates.get(user_id, DEFAULT_CAPTION)
            new_caption = format_caption(template, data)
            # copy message with new caption back to same chat
            sent = await safe_copy(
                to_chat=msg.chat.id,
                from_chat=msg.chat.id,
                message_id=msg.id,
                caption=new_caption,
                parse_mode=ParseMode.HTML
            )
            # copy to log group
            try:
                await sent.copy(LOG_GROUP_ID)
            except:
                pass
            # send episode sticker if available for this user
            sticker_file_id = episode_stickers.get(user_id, {}).get(data.get("episode"))
            if sticker_file_id:
                try:
                    await app.send_sticker(chat_id=msg.chat.id, sticker=sticker_file_id)
                except:
                    pass
        except Exception as e:
            # print error to logs (avoid crashing)
            print("PROCESS ERROR:", e)
        # small delay to avoid floods
        await asyncio.sleep(0.2)
    # clear buffer
    user_media_buffer[user_id] = []

# ------------------ Huge upload flow (forward FIRST & LAST messages) ------------------

@app.on_message(filters.command("huge_upload") & filters.private)
async def cmd_huge_upload_start(client: Client, message: Message):
    uid = message.from_user.id
    set_user_mode(uid, "huge_upload")
    huge_sessions[uid] = {"step": 1, "first_chat": None, "first_id": None, "last_chat": None, "last_id": None}
    await message.reply_text("🚀 Huge upload started.\n\nForward the FIRST message from the source channel/group (forward exactly that message).")

@app.on_message(filters.forwarded & filters.private)
async def handle_huge_forward_steps(client: Client, message: Message):
    uid = message.from_user.id
    session = huge_sessions.get(uid)
    if not session or get_user_mode(uid) != "huge_upload":
        return  # not in huge_upload flow

    step = session.get("step", 1)
    fchat = message.forward_from_chat
    fmid = message.forward_from_message_id

    if not fchat or not fmid:
        return await message.reply_text("Forward a direct message from the source (not a forward-of-forward).")

    # STEP 1: record first
    if step == 1:
        session["first_chat"] = fchat.id
        session["first_id"] = fmid
        session["step"] = 2
        await message.reply_text("✅ First message recorded.\n\nNow forward the LAST message from the same source channel/group.")
        return

    # STEP 2: record last (must be same source)
    if step == 2:
        if fchat.id != session.get("first_chat"):
            return await message.reply_text("The LAST message must be forwarded from the SAME source channel/group as the FIRST message. Forward it again.")
        session["last_chat"] = fchat.id
        session["last_id"] = fmid
        session["step"] = 3
        # show registered channels as inline buttons for target selection
        chans = registered_channels.get(uid, {})
        if not chans:
            # reset session and instruct
            reset_user_mode(uid)
            huge_sessions.pop(uid, None)
            return await message.reply_text("You have no registered target channels. Use /add_channels and forward a message from your target channel(s) first.")
        # build keyboard
        buttons = []
        for cid, title in chans.items():
            buttons.append([InlineKeyboardButton(text=title[:40], callback_data=f"huge_target:{cid}")])
        await message.reply_text("Choose a target channel to upload into:", reply_markup=InlineKeyboardMarkup(buttons))
        return

# callback to receive target channel selection
@app.on_callback_query(filters.regex(r"^huge_target:(-?\d+)$"))
async def cb_huge_target(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    match = re.match(r"^huge_target:(-?\d+)$", cq.data)
    if not match:
        return await cq.answer("Invalid selection.", show_alert=True)
    target_cid = int(match.group(1))
    session = huge_sessions.get(uid)
    if not session or get_user_mode(uid) != "huge_upload":
        return await cq.answer("Session expired.", show_alert=True)
    source_chat = session.get("first_chat")
    first_id = session.get("first_id")
    last_id = session.get("last_id")
    if not (source_chat and first_id and last_id):
        return await cq.answer("Session data missing.", show_alert=True)
    # check bot is admin in target channel
    try:
        bot_member = await app.get_chat_member(target_cid, "me")
        if bot_member.status not in ("administrator", "creator"):
            return await cq.answer("I am not admin in the selected target channel.", show_alert=True)
    except Exception as e:
        return await cq.answer("Failed to verify target channel admin status.", show_alert=True)

    await cq.message.edit_text("✅ Target selected. Starting upload...")

    # process upload in background task (don't block callback)
    asyncio.create_task(_process_huge_upload(uid, source_chat, first_id, last_id, target_cid, cq.message.chat.id))
    # respond to callback
    await cq.answer("Upload queued. See progress messages here.")

async def _iter_messages_between(chat_id: int, first_id: int, last_id: int):
    """
    Yield messages from chat_id between first_id and last_id inclusive
    in ascending message id (first -> last).
    """
    # ensure first_id <= last_id
    if first_id <= last_i
