# KENSHIN Caption Changer 2.02 — Full Extended (Pyrogram)
# Requirements: pyrogram, tgcrypto, python-dotenv (optional)
# Environment variables required:
# API_ID, API_HASH, BOT_TOKEN, LOG_GROUP_ID, ADMIN_IDS  (ADMIN_IDS comma-separated numeric IDs)
#
# Notes:
# - This file is self-contained and uses in-memory storage (restart will clear registrations).
# - Make sure the bot is admin in channels you register and in target channels.
# - Use Python 3.11 / Pyrogram 2.x for best results.

import os
import re
import asyncio
from typing import Dict, Any, List, Tuple, Optional

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
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

if not (API_ID and API_HASH and BOT_TOKEN and LOG_GROUP_ID):
    raise SystemExit("Missing required environment variables: API_ID, API_HASH, BOT_TOKEN, LOG_GROUP_ID")

app = Client("kenshin_v2", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=100)

# ------------------ In-memory storage ------------------
users_db: set[int] = set()                                   # all users who used /start
user_templates: Dict[int, str] = {}                          # per-user caption template
user_media_buffer: Dict[int, List[Message]] = {}             # per-user video buffer
user_delay_task: Dict[int, asyncio.Task] = {}                # per-user scheduled tasks
user_edit_all_mode: Dict[int, str] = {}                      # "yes" or "no"
registered_channels: Dict[int, Dict[int, str]] = {}          # user_id -> {channel_id: title}
huge_sessions: Dict[int, Dict[str, Any]] = {}                # user_id -> huge_upload state
episode_stickers: Dict[int, Dict[int, str]] = {}             # user_id -> {episode: sticker_file_id}
user_sessions: Dict[int, Dict[str, Any]] = {}                # user_id -> {"mode": "normal"/"huge_upload"/"add_channel"}

# ------------------ Defaults & templates ------------------
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

# ------------------ Safe copy util (handles FloodWait) ------------------

async def safe_copy(to_chat: int, from_chat: int, message_id: int, **kwargs):
    while True:
        try:
            copied = await app.copy_message(chat_id=to_chat, from_chat_id=from_chat, message_id=message_id, **kwargs)
            return copied
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except RPCError:
            # Bubble up non-retryable RPC errors for caller to handle/log
            raise

# ------------------ Session helpers ------------------

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
    user_templates.setdefault(uid, DEFAULT_CAPTION)
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
        "Notes:\n- Bot must be admin in channels you register and in target channels.\n- Registrations are in-memory (restart clears). Use DB for persistence."
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

@app.on_message(filters.command("list_stickers") & filters.private)
async def cmd_list_stickers(_, message: Message):
    uid = message.from_user.id
    stickers = episode_stickers.get(uid, {})
    if not stickers:
        return await message.reply_text("You have no stickers set. Use /set_sticker (reply to sticker).")
    text_lines = ["Your episode stickers:"]
    for ep, fid in sorted(stickers.items()):
        text_lines.append(f"Episode {ep} -> {fid}")
    await message.reply_text("\n".join(text_lines))

# ------------------ Channel registration ------------------

@app.on_message(filters.command("add_channels") & filters.private)
async def cmd_add_channels(client: Client, message: Message):
    uid = message.from_user.id
    set_user_mode(uid, "add_channel")
    await message.reply_text("🔁 Forward one message from each channel you want to register (forward exactly that message). When done, send /done_channels")

@app.on_message(filters.command("done_channels") & filters.private)
async def cmd_done_channels(_, message: Message):
    uid = message.from_user.id
    reset_user_mode(uid)
    await message.reply_text("✅ Channel registration finished. Use /list_channels to see registered channels.")

def _get_forward_source_chat_id(msg: Message) -> Optional[int]:
    # new property forward_origin may be present; support both
    if getattr(msg, "forward_from_chat", None):
        try:
            return msg.forward_from_chat.id
        except:
            pass
    # fallback to forward_origin.chat.sender_chat path used in newer Pyrogram/Telegram
    fo = getattr(msg, "forward_origin", None)
    if fo and getattr(fo, "chat", None):
        # forward_origin.chat may be a Chat or SenderChat; both have id attribute
        try:
            return fo.chat.id
        except:
            pass
    # also handle forward_sender_name forwarded from users without channel info
    return None

@app.on_message(filters.forwarded & filters.private)
async def handle_forward_registration(client: Client, message: Message):
    uid = message.from_user.id
    if get_user_mode(uid) != "add_channel":
        return  # only accept when in add_channel mode
    source_chat_id = _get_forward_source_chat_id(message)
    if not source_chat_id:
        return await message.reply_text("Could not detect source chat from forwarded message. Forward a direct message from the channel.")
    # verify bot admin in that channel
    try:
        bot_member = await client.get_chat_member(source_chat_id, "me")
    except Exception as e:
        return await message.reply_text("Failed to query channel. Make sure bot is a member/admin of the channel.")
    if bot_member.status not in ("administrator", "creator"):
        return await message.reply_text("❌ I must be admin in that channel to register it. Make me admin and forward again.")
    # record channel
    registered_channels.setdefault(uid, {})
    try:
        chat = await client.get_chat(source_chat_id)
        title = chat.title or str(source_chat_id)
    except:
        title = str(source_chat_id)
    registered_channels[uid][source_chat_id] = title
    await message.reply_text(f"✅ Registered channel: {title}")

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

async def _enqueue_video_for_user(message: Message):
    if not message.from_user:
        return
    uid = message.from_user.id
    users_db.add(uid)
    if uid not in user_media_buffer:
        user_media_buffer[uid] = []
    user_media_buffer[uid].append(message)
    # schedule processing (cancel previous pending task)
    if uid in user_delay_task and not user_delay_task[uid].done():
        user_delay_task[uid].cancel()
    user_delay_task[uid] = asyncio.create_task(_process_after_delay(uid))

@app.on_message(filters.video & (filters.private | filters.group | filters.channel))
async def on_video_message(client: Client, message: Message):
    uid = message.from_user.id if message.from_user else None
    if uid:
        mode = get_user_mode(uid)
        if mode in ("huge_upload", "add_channel"):
            # ignore normal enqueue while user is in a flow
            return
    await _enqueue_video_for_user(message)

async def _process_after_delay(user_id: int):
    await asyncio.sleep(0.2)
    messages = list(user_media_buffer.get(user_id, []))
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
    for _, _, msg in media_list:
        try:
            data = extract_data(msg.caption or "")
            tpl = user_templates.get(user_id, DEFAULT_CAPTION)
            caption = format_caption(tpl, data)
            # copy message back to same chat with new caption
            try:
                sent = await safe_copy(
                    to_chat=msg.chat.id,
                    from_chat=msg.chat.id,
                    message_id=msg.id,
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                print("Error copying message:", e)
                continue
            # copy to log group (best-effort)
            try:
                await sent.copy(LOG_GROUP_ID)
            except:
                pass
            # send sticker if user has one for this episode (best-effort)
            ep_num = data.get("episode")
            sticker_file_id = episode_stickers.get(user_id, {}).get(ep_num)
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

# ------------------ Huge upload flow ------------------

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
        return
    src_chat_id = _get_forward_source_chat_id(message)
    if not src_chat_id:
        return await message.reply_text("Could not detect source chat from forwarded message. Forward a direct message from the channel.")
    fmid = message.forward_from_message_id
    # record first
    if session["step"] == 1:
        session["first_chat"] = src_chat_id
        session["first_id"] = fmid
        session["step"] = 2
        await message.reply_text("✅ First message recorded.\n\nNow forward the LAST message from the same source channel/group.")
        return
    # record last
    if session["step"] == 2:
        if src_chat_id != session.get("first_chat"):
            return await message.reply_text("The LAST message must be forwarded from the SAME source channel/group as the FIRST. Forward it again.")
        session["last_chat"] = src_chat_id
        session["last_id"] = fmid
        session["step"] = 3
        # present user's registered channels for selection
        chans = registered_channels.get(uid, {})
        if not chans:
            reset_user_mode(uid)
            huge_sessions.pop(uid, None)
            return await message.reply_text("You have no registered target channels. Use /add_channels and forward a message from your target channel(s) first.")
        buttons = []
        for cid, title in chans.items():
            buttons.append([InlineKeyboardButton(text=title[:40], callback_data=f"huge_target:{cid}")])
        await message.reply_text("Choose a target channel to upload into:", reply_markup=InlineKeyboardMarkup(buttons))
        return

@app.on_callback_query(filters.regex(r"^huge_target:(-?\d+)$"))
async def cb_huge_target(client: Client, cq: CallbackQuery):
    uid = cq.from_user.id
    m = huge_sessions.get(uid)
    if not m or get_user_mode(uid) != "huge_upload":
        return await cq.answer("Session expired", show_alert=True)
    target_cid = int(re.match(r"^huge_target:(-?\d+)$", cq.data).group(1))
    # verify bot admin in target
    try:
        bot_member = await app.get_chat_member(target_cid, "me")
        if bot_member.status not in ("administrator", "creator"):
            return await cq.answer("I am not admin in the selected target channel.", show_alert=True)
    except Exception:
        return await cq.answer("Failed to verify target channel.", show_alert=True)
    await cq.message.edit_text("✅ Target selected. Starting upload...")
    # fire background task
    asyncio.create_task(_process_huge_upload(uid, m["first_chat"], m["first_id"], m["last_id"], target_cid, cq.message.chat.id))
    await cq.answer("Upload started (in background).")

async def _iter_messages_between(chat_id: int, first_id: int, last_id: int) -> List[Message]:
    # returns messages in ascending order (first->last) inclusive
    # handle first > last by swapping
    if first_id <= last_id:
        start, end = first_id, last_id
    else:
        start, end = last_id, first_id
    collected: List[Message] = []
    # Pyrogram's iter_history/get_chat_history may be used; we iterate from end backwards and reverse
    try:
        async for m in app.get_chat_history(chat_id, offset_id=end + 1):
            if m.id < start:
                break
            if start <= m.id <= end:
                collected.append(m)
    except TypeError:
        # fallback older signature
        async for m in app.iter_history(chat_id, offset_id=end + 1):
            if m.id < start:
                break
            if start <= m.id <= end:
                collected.append(m)
    except TypeError:
        # fallback older signature
        async for m in app.iter_history(chat_id, offset_id=end + 1):
            if m.id < start:
                break
            if start <= m.id <= end:
                collected.append(m)
    collected.reverse()
    return collected

async def _process_huge_upload(user_id: int, source_chat: int, first_id: int, last_id: int, target_channel: int, reply_chat: int):
    try:
        await app.send_message(reply_chat, "🔁 Collecting messages from source...")
        msgs = await _iter_messages_between(source_chat, first_id, last_id)
        if not msgs:
            await app.send_message(reply_chat, "No messages found in that range.")
            reset_user_mode(user_id)
            huge_sessions.pop(user_id, None)
            return
        # filter videos
        media_items: List[Tuple[int, int, Message]] = []
        for m in msgs:
            if m.video:
                data = extract_data(m.caption or "")
                media_items.append((data.get("episode", 0), quality_order(data.get("quality", 0)), m))
        media_items.sort(key=lambda x: (x[0], x[1]))
        await app.send_message(reply_chat, f"Found {len(media_items)} video items. Starting upload...")
        count = 0
        for ep_num, _, m in media_items:
            tpl = user_templates.get(user_id, DEFAULT_CAPTION)
            data = extract_data(m.caption or "")
            caption = format_caption(tpl, data)
            try:
                copied = await safe_copy(
                    to_chat=target_channel,
                    from_chat=source_chat,
                    message_id=m.id,
                    caption=caption,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                print("Copy error (huge upload):", e)
                await asyncio.sleep(0.2)
                continue
            try:
                await copied.copy(LOG_GROUP_ID)
            except:
                pass
            sticker_file_id = episode_stickers.get(user_id, {}).get(data.get("episode"))
            if sticker_file_id:
                try:
                    await app.send_sticker(target_channel, sticker_file_id)
                except:
                    pass
            count += 1
            await asyncio.sleep(0.2)
        await app.send_message(reply_chat, f"✅ Huge upload completed: {count} items uploaded.")
    except Exception as exc:
        print("HUGE UPLOAD ERROR:", exc)
        try:
            await app.send_message(reply_chat, f"❌ Upload failed: {exc}")
        except:
            pass
    finally:
        reset_user_mode(user_id)
        huge_sessions.pop(user_id, None)

# ------------------ Cancel flow ------------------

@app.on_message(filters.command("cancel") & filters.private)
async def cmd_cancel(client: Client, message: Message):
    uid = message.from_user.id
    reset_user_mode(uid)
    huge_sessions.pop(uid, None)
    await message.reply_text("✅ Session cancelled and normal processing resumed.")

# ------------------ Startup log ------------------

if __name__ == "__main__":
    print("🔥 KENSHIN Caption Changer 2.02 (Pyrogram) starting...")
    app.run()
