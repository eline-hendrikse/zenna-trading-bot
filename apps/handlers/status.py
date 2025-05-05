# Handler for /status
import psutil
import sys
import os
from pathlib import Path
from apps.utils.telegram import send_reply

def is_script_running(target_script):
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline', [])
            if any(Path(arg).name == target_script for arg in cmdline):
                return True
        except Exception:
            continue
    return False

def handle(chat_id, *_):
    spot_paper_running       = is_script_running("spot_paper_trading.py")
    spot_live_running        = is_script_running("spot_trading.py")
    futures_paper_running    = is_script_running("futures_paper_trading.py")
    futures_live_running     = is_script_running("futures_trading.py")

    msg = (
        "Zenna Status\n\n"
        f"Spot Paper Trading: {'Running' if spot_paper_running else 'Paused'}\n"
        f"Spot Live Trading : {'Running' if spot_live_running else 'Paused'}\n"
        f"Futures Paper Trading: {'Running' if futures_paper_running else 'Paused'}\n"
        f"Futures Live Trading : {'Running' if futures_live_running else 'Paused'}"
    )
    send_reply(chat_id, msg)
