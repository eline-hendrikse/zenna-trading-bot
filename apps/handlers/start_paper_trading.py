# Handler for /start_paper_trading
import subprocess
import json
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from config_loader import get_project_path
from utils.telegram import send_reply

def handle(chat_id, text=None):    
    parts = text.split()

    if len(parts) < 8:
        send_reply(
            chat_id,
            " 💭 Usage:\n"
            "/start_paper_trading spot BTCUSDT 4h 1 20 30 70 55\n"
            "\n"
            "Spot/Futures, symbol, timeframe, risk per trade, leverage, rsi window, rsi entry, rsi exit, rsi exit execution"
        )
        return

    args = parts[1:]
    script_path = get_project_path("apps", "trading", args[0] + "_paper_trading.py")
    cmd = ["python", script_path] + args[1:]

    try:
        # Pre-flight check only
        result = subprocess.check_output(cmd + ["check"], timeout=30, text=True)
        
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            send_reply(chat_id, "🔔 Zenna returned an invalid response\n(possibly a syntax error).")
            return

        if "error" in data:
            send_reply(chat_id, f"🔔 Zenna could not start:\n{data['error']}")
        else:
            zenna_process = subprocess.Popen(cmd + ["start"])
            send_reply(chat_id, f"Starting Zenna...")

    except subprocess.TimeoutExpired:
        send_reply(chat_id, f"🔔 Timeout: Zenna took too long to respond.")
    except Exception as e:
        send_reply(chat_id, f"🔔 Unexpected error:\n{type(e).__name__}: {str(e)}")   
        
