# Handler for /stop_paper_trading.py
import psutil
import signal
import sys
import os
from pathlib import Path
from apps.utils.telegram import send_reply

# TO DO: add arg wallet and stop the right process

def handle(chat_id, text=None):
    try:
        found = False

        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get("cmdline", [])
                if cmdline and "spot_paper_trading.py" in " ".join(cmdline):
                    send_reply(chat_id, "Stopping Zenna...")
                    proc.send_signal(signal.SIGINT)
                    found = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not found:
            send_reply(chat_id, "Zenna is already stopped.")

    except Exception as e:
        send_reply(chat_id, f"🔔 Error while stopping:\n{type(e).__name__}: {str(e)}")
