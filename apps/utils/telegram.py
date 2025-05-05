# Telegram functions
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

import requests
from apps import config_loader

telegram_bot_token    = config_loader.Telegram_bot_token
telegram_chat_id      = int(config_loader.Telegram_chat_id)

import requests
import time

def safe_telegram_call(method, payload=None, retries=5, delay=5):
    url = f"https://api.telegram.org/bot{telegram_bot_token}/{method}"
    attempt = 0

    while attempt < retries:
        try:
            if payload:
                response = requests.post(url, data=payload, timeout=10)
            else:
                response = requests.get(url, timeout=10)

            response.raise_for_status()
            result = response.json()
            if "getUpdates" in method:
                return result.get("result", []) if result else []
            else:
                return result
        except Exception as e:
            attempt += 1
            print(f"🔔 Telegram API {method} unreachable (Attempt {attempt}/{retries}): {e}")
            if attempt >= retries:
                print(f"🔔 Failed to connect with Telegram after {attempt} retries. A manual recovery is needed.")
                if "getUpdates" in method:
                    return []
                else:
                    return None

            time.sleep(min(delay * (2 ** (retries - 1)), 30))

# Telegram functions
def get_updates(offset=None):
    method = "getUpdates"
    if offset:
        method += f"?offset={offset}"
    return safe_telegram_call(method)
    
def send_reply(chat_id, text):
    payload = {"chat_id": chat_id, "text": text}
    safe_telegram_call("sendMessage", payload)

def send_message(text):
    payload = {"chat_id": telegram_chat_id, "text": text}
    safe_telegram_call("sendMessage", payload)


        
