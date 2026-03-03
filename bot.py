import os
import re
import asyncio
import aiohttp
from pyrofork import Client, filters, idle
from pyrofork.errors import FloodWait
from pyrofork.types import Message

# ================= CONFIG =================

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))
STORE_GROUP_ID = int(os.getenv("STORE_GROUP_ID"))
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID"))

ANILIST_CLIENT_ID = os.getenv("ANILIST_CLIENT_ID")
ANILIST_CLIENT_SECRET = os.getenv("ANILIST_CLIENT_SECRET")

bot = Client("empire_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

users_db = set()
caption_template = None
anime_details_template = None
edit_all_mode = True

# ================= UTILS =================

def extract_episode(text):
    if not text: return 0
    match = re.search(r'ep(?:isode)?\s?(\d+)', text, re.I)
    return int(match.group(1)) if match else 0

def extract_quality(text):
    if not text: return "0"
    match = re.search(r'(480p|720p|1080p|2160p|4k)', text, re.I)
    return match.group(1) if match else "0"

def sort_key(msg):
    ep = extract_episode(msg.caption or "")
    quality = extract_quality(msg.caption or "")
    quality_order = {"480p":1,"720p":2,"1080p":3,"2160p":4,"4k":4}
    return (ep, quality_order.get(quality, 0))

# ================= ANILIST FETCH =================

async def fetch_anime_data(title):
    query = """
    query ($search: String) {
      Media (search: $search, type: ANIME) {
        title { romaji english }
        genres
        description(asHtml: false)
        coverImage { large }
        episodes
        status
      }
    }
    """

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": {"search": title}},
        ) as resp:
            data = await resp.json()

    media = data["data"]["Media"]

    return {
        "title": media["title"]["english"] or media["title"]["romaji"],
        "genres": ", ".join(media["genres"]),
        "synopsis": re.sub('<.*?>', '', media["description"] or ""),
        "poster": media["coverImage"]["large"],
        "episodes": str(media["episodes"] or "Ongoing"),
        "status": media["status"]
    }

# ================= COMMANDS =================

@bot.on_message(filters.private & filters.incoming)
async def user_tracker(_, msg: Message):
    if msg.from_user:
        users_db.add(msg.from_user.id)

@bot.on_message(filters.command("setcaption") & filters.user(ADMIN_IDS))
async def set_caption(_, msg):
    global caption_template
    caption_template = msg.text.split(None,1)[1]
    await msg.reply("✅ Video Caption Template Saved")

@bot.on_message(filters.command("anime_dl_caption") & filters.user(ADMIN_IDS))
async def set_anime_template(_, msg):
    global anime_details_template
    anime_details_template = msg.text.split(None,1)[1]
    await msg.reply("✅ Anime Details Template Saved")

@bot.on_message(filters.command("edit_all") & filters.user(ADMIN_IDS))
async def edit_mode(_, msg):
    global edit_all_mode
    mode = msg.text.split()[-1].lower()
    edit_all_mode = True if mode == "yes" else False
    await msg.reply(f"Mode Updated: {mode}")

@bot.on_message(filters.command("users") & filters.user(ADMIN_IDS))
async def total_users(_, msg):
    await msg.reply(f"👥 Total Users: {len(users_db)}")

@bot.on_message(filters.command("broadcast") & filters.user(ADMIN_IDS))
async def broadcast(_, msg):
    text = msg.text.split(None,1)[1]
    for user in users_db:
        try:
            await bot.send_message(user, text)
            await asyncio.sleep(0.3)
        except:
            continue
    await msg.reply("Broadcast Completed")

# ================= HUGE UPLOAD =================

@bot.on_message(filters.command("huge_upload") & filters.user(ADMIN_IDS))
async def huge_upload(_, msg: Message):

    await msg.reply("Send Source Chat Username or ID")
    source = (await bot.listen(msg.chat.id)).text.strip()

    await msg.reply("Send First Message ID")
    first_id = int((await bot.listen(msg.chat.id)).text)

    await msg.reply("Send Last Message ID")
    last_id = int((await bot.listen(msg.chat.id)).text)

    await msg.reply("Send Target Channel Username or ID")
    target = (await bot.listen(msg.chat.id)).text.strip()

    await msg.reply("Send Anime Name For Metadata")
    anime_name = (await bot.listen(msg.chat.id)).text.strip()

    await msg.reply("🚀 Starting Empire Upload...")

    anime_data = await fetch_anime_data(anime_name)

    # Upload poster + details
    if anime_details_template:
        details_caption = anime_details_template.format(
            anime=anime_data["title"],
            season="1",
            episodes=anime_data["episodes"],
            audio="Hindi",
            quality="480p • 720p • 1080p",
            genre=anime_data["genres"],
            synopsis=anime_data["synopsis"]
        )

        await bot.send_photo(
            target,
            anime_data["poster"],
            caption=details_caption
        )

    # Stickers
    sticker_pack = await bot.get_sticker_set("AnimeNetworkIndia")
    start_sticker = sticker_pack.stickers[0].file_id
    black_sticker = sticker_pack.stickers[1].file_id
    end_sticker = sticker_pack.stickers[2].file_id

    await bot.send_sticker(target, start_sticker)

    copied = []

    for i in range(first_id, last_id+1):
        try:
            m = await bot.copy_message(STORE_GROUP_ID, source, i)
            if m.video:
                copied.append(m)
            await asyncio.sleep(1)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except:
            continue

    copied.sort(key=sort_key)

    current_ep = None

    for m in copied:
        ep = extract_episode(m.caption or "")
        if current_ep and ep != current_ep:
            await bot.send_sticker(target, black_sticker)
        current_ep = ep

        if edit_all_mode:
            await bot.copy_message(target, STORE_GROUP_ID, m.id)
        else:
            await bot.copy_message(target, STORE_GROUP_ID, m.id, caption=m.caption)

        await bot.delete_messages(STORE_GROUP_ID, m.id)
        await asyncio.sleep(1)

    await bot.send_sticker(target, end_sticker)

    await msg.reply("✅ Empire Upload Completed")

# ================= START & HELP =================

@bot.on_message(filters.command("start"))
async def start(_, msg):
    await msg.reply(f"""🔥 Advance Caption Empire Bot

Hi {msg.from_user.mention}

100+ Channel Automation Ready 🚀
Use /help to see all commands.""")

@bot.on_message(filters.command("help"))
async def help_cmd(_, msg):
    await msg.reply("""
📌 ADMIN COMMANDS

/setcaption - Set video caption template
/anime_dl_caption - Set anime details template
/edit_all yes/no - Send full message or only video
/huge_upload - Massive range upload
/broadcast - Broadcast to all users
/users - Total user count
""")

# ================= RUN =================

async def main():
    await bot.start()
    print("🔥 TELEGRAM EMPIRE SYSTEM RUNNING")
    await idle()

if __name__ == "__main__":
    asyncio.run(main())
