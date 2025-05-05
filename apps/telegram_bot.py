# Telegram command listener
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

import time
from apps import config_loader
from apps.utils.telegram import get_updates, send_reply
from apps.commands import dispatch_command

Telegram_chat_id      = int(config_loader.Telegram_chat_id)

last_update_id = 0

while True:   
    updates = get_updates(last_update_id)
    for update in updates:
        message = update.get("message")
        if not message:
            continue

        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]
        text = message.get("text", "")
        username = message["from"].get("username", "unknown")

        if user_id != Telegram_chat_id:
            print(f"Unauthorized access: {username} ({user_id})")
            send_reply(chat_id, "Access denied.")
            continue

        try:
            dispatch_command(chat_id, text)
            last_update_id = update["update_id"] + 1

        except Exception as e:
                import traceback
                print("🔔 Exception caught in main loop:")
                traceback.print_exc()
                send_reply(chat_id, "🔔 An internal error occurred.")
            # print(f"🔔 Error in main loop: {e}")

    time.sleep(5)

#jupyter nbconvert --to script telegram_bot.ipynb