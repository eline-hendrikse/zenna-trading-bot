# Handler for /backtest
import subprocess
import json
import sys
import os
from pathlib import Path
from apps.utils.telegram import send_reply
from apps.config_loader import get_project_path

def handle(chat_id, text=None):
    parts = text.split()
    if len(parts) < 12:
        send_reply(
            chat_id,
            " 💭 Usage:\n"
            "/backtest spot BTCUSDT 4h 1 2024-04-01 00:00:00 2025-04-01 00:00:00 20 30 75 58\n\n"
            "Spot/Futures, symbol, timeframe, risk per trade, start date, start time, end date, end time, rsi window, rsi entry, rsi exit, rsi exit execution"
        )
        return

    args = parts[1:]
    script_path = get_project_path("apps", "trading", args[0] + "_backtest.py")
    cmd = ["python", script_path] + args[1:]

    try:
        result = subprocess.check_output(cmd, timeout=240, text=True).strip()
        
        try:
            data = json.loads(result)    
        except json.JSONDecodeError:
            send_reply(chat_id, f"🔔 Zenna returned an invalid response:\n```{result.strip()}```")
            return

        if "error" in data:
            send_reply(chat_id, f"🔔 Zenna could not complete the task:\n{data['error']}")
        else:
            report = (
                f"Backtest Report\n\n"
                f"• Start Date: {data['Start Date']}\n"
                f"• End Date: {data['End Date']}\n"
                f"• Start Value: {data['Start Value']}\n"
                f"• End Value: {data['End Value']}\n"
                f"• Profit: {data['Profit']}\n"
                f"• Benchmark: {data['Benchmark']}\n"
                f"• Total Trades: {data['Total Trades']}\n"
                f"• Closed Trades: {data['Total Closed Trades']}\n"
                f"• Open Trades: {data['Total Open Trades']}\n"
                f"• Open Trade PnL: {data['Open Trade PnL']}\n"
                f"• Win Rate: {data['Win Rate']}\n"
                f"• Winning Trades: {data['Total Winning Trades']}\n"
                f"• Losing Trades: {data['Total Losing Trades']}\n"
                f"• Lowest PnL: {data['Lowest PnL']}\n"
                f"• Max Drawdown: {data['Max Drawdown']}\n"
                f"• Commission: {data['Commission']}\n\n"
                f"{data['Performance vs Benchmark']}"
            )    
            send_reply(chat_id, report)

    except subprocess.TimeoutExpired:
        send_reply(chat_id, "🔔 Timeout: Zenna took too long to backtest.")
    except subprocess.CalledProcessError as e:
        send_reply(chat_id, f"🔔 Backtest error (code {e.returncode})\nPossibly a syntax error.\n{e.output.strip()}")
    except Exception as e:
        send_reply(chat_id, f"🔔 Backtest failed:\n{type(e).__name__}: {str(e)}")


