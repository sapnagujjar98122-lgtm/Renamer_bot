import os
import re
import asyncio
import aiohttp
from pyrogram import Client, filters, idle
from pyrogram.errors import FloodWait
from pyrogram.types import Message

# ================= CONFIG =================

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))
STORE_GROUP_ID = int(os.getenv("STORE_GROUP_ID"))
LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID"))

bot = Client(
    "EmpireBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

users_db = set()
video_caption_template = None
anime_details_template = None
edit_all_mode = True

# ================= UTILS =================

def extract_episode(text):
    if not text: return 0
    m = re.search(r'ep(?:isode)?\s?(\d+)', text, re.I)
    return int(m.group(1)) if m else 0

def extract_quality(text):
    if not text: return "0"
    m = re.search(r'(480p|720p|1080p|2160p|4k)', text, re.I)
    return m.group(1) if m else "0"

def sort_key(msg):
    order = {"480p":1,"720p":2,"1080p":3,"2160p":4,"4k":4}
    return (extract_episode(msg.caption or ""),
            order.get(extract_quality(msg.caption or ""), 0))

# ================= ANILIST =================

async def fetch_anime(title):
    query = """
    query ($search: String) {
      Media (search: $search, type: ANIME) {
        title { english romaji }
        genres
        description
        coverImage { large }
        episodes
      }
    }
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": {"search": title}}
        ) as resp:
            data = await resp.json()

    media = data["data"]["Media"]

    return {
        "title": media["title"]["english"] or media["title"]["romaji"],
        "genres": ", ".join(media["genres"]),
        "synopsis": re.sub('<.*?>', '', media["description"] or ""),
        "poster": media["coverImage"]["large"],
        "episodes": str(media["episodes"] or "Ongoing")
    }

# ================= COMMANDS =================

@bot.on_message(filters.private)
async def track_users(_, msg):
    if msg.from_user:
        users_db.add(msg.from_user.id)

@bot.on_message(filters.command("setcaption") & filters.user(ADMIN_IDS))
async def set_caption(_, msg):
    global video_caption_template
    video_caption_template = msg.text.split(None,1)[1]
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
async def users(_, msg):
    await msg.reply(f"👥 Users: {len(users_db)}")

@bot.on_message(filters.command("broadcast") & filters.user(ADMIN_IDS))
async def broadcast(_, msg):
    text = msg.text.split(None,1)[1]
    for u in users_db:
        try:
            await bot.send_message(u, text)
            await asyncio.sleep(0.2)
        except:
            pass
    await msg.reply("Broadcast Done")

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

    await msg.reply("Send Anime Name")
    anime_name = (await bot.listen(msg.chat.id)).text.strip()

    await msg.reply("🚀 Processing...")

    anime = await fetch_anime(anime_name)

    # Upload Poster + Details
    if anime_details_template:
        caption = anime_details_template.format(
            anime=anime["title"],
            season="1",
            episodes=anime["episodes"],
            audio="Hindi",
            quality="480p • 720p • 1080p",
            genre=anime["genres"],
            synopsis=anime["synopsis"]
        )
        await bot.send_photo(target, anime["poster"], caption=caption)

    stickers = await bot.get_sticker_set("AnimeNetworkIndia")
    await bot.send_sticker(target, stickers.stickers[0].file_id)

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
            await bot.send_sticker(target, stickers.stickers[1].file_id)
        current_ep = ep

        if edit_all_mode:
            await bot.copy_message(target, STORE_GROUP_ID, m.id)
        else:
            await bot.copy_message(target, STORE_GROUP_ID, m.id, caption=m.caption)

        await bot.delete_messages(STORE_GROUP_ID, m.id)
        await asyncio.sleep(1)

    await bot.send_sticker(target, stickers.stickers[2].file_id)
    await msg.reply("✅ Upload Completed")

# ================= START =================

@bot.on_message(filters.command("start"))
async def start(_, msg):
    await msg.reply("🔥 Anime Empire Bot Running")

@bot.on_message(filters.command("help"))
async def help_cmd(_, msg):
    await msg.reply("""
/setcaption
/anime_dl_caption
/edit_all yes/no
/huge_upload
/broadcast
/users
""")

# ================= RUN =================

async def main():
    await bot.start()
    print("🔥 Empire Bot Running")
    await idle()

if __name__ == "__main__":
    asyncio.run(main())
