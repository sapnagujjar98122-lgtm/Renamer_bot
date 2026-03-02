from pyrogram.enums import ParseMode

# Default parse mode
user_parse_modes = {}

def set_parse_mode(user_id: int, mode: str):
    mode = mode.lower()

    if mode == "html":
        user_parse_modes[user_id] = ParseMode.HTML
        return "✅ Parse mode set to HTML"

    elif mode == "markdown":
        user_parse_modes[user_id] = ParseMode.MARKDOWN
        return "✅ Parse mode set to Markdown"

    elif mode == "none":
        user_parse_modes[user_id] = None
        return "✅ Parse mode disabled"

    else:
        return "❌ Invalid mode. Use: html / markdown / none"

def get_parse_mode(user_id: int):
    return user_parse_modes.get(user_id, ParseMode.HTML)
