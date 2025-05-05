# Handler for /indicators
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

import pandas as pd
import vectorbt as vbt
from utils.telegram import send_reply
from utils.dataframe import get_klines
from config_loader import get_project_path

def handle(chat_id, text=None):
    parts = text.split()
    if len(parts) < 3:
        send_reply(
            chat_id,
            " 💭 Usage:\n"
            "/indicators BTCUSDT 4h 20\n"
            "\n"
            "Symbol, timeframe, rsi window"
        )
        return

    args = parts[1:]
    
    try:
        symbol                = args[0]
        timeframe             = args[1]
        rsi_window            = args[2]
        
        df = get_klines(symbol, timeframe, int(rsi_window) + 2)
        
        # Calculate RSI based on rsi_window
        df['RSI']             = round(vbt.RSI.run(df['close'], window=int(rsi_window)).rsi, 2)
        df                    = df.tail(1)
        rsi                   = float(df['RSI'].iloc[0])

        send_reply(chat_id, rsi)

    except Exception as e:
        send_reply(chat_id, f"🔔 Could not retrieve indicators:\n{type(e).__name__}: {str(e)}")