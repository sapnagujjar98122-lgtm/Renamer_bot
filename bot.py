from pyrogram import Client, filters

app = Client("test", bot_token="YOUR_TOKEN")

@app.on_message(filters.command("start"))
async def start(_, msg):
    await msg.reply("Working")

app.run()
