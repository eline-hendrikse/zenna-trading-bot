# Paper trading bot
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

import pandas as pd
import vectorbt as vbt
import time
import datetime as dt
import requests
import json
from apps import config_loader
from apps.config_loader import get_project_path
from binance.client import Client
from binance.um_futures import UMFutures
from datetime import datetime, timedelta

# Initialize Binance client
client                = Client(config_loader.api_key, config_loader.api_secret)
client_futures        = UMFutures(config_loader.api_key, config_loader.api_secret)

# Initialize Telegram token
Telegram_bot_token    = config_loader.Telegram_bot_token
Telegram_chat_id      = int(config_loader.Telegram_chat_id)

def run_paper_trading_bot(
    symbol, timeframe, risk_per_trade, leverage, 
    rsi_window, rsi_entry, rsi_exit, rsi_exit_exec):

    try:
        while True:
            # Define global variables
            dataframe_path        = get_project_path("logs", "papertrading", "pt_dataframe.csv") 
            active_path           = get_project_path("logs", "papertrading", "pt_active_trade.csv")
            log_path              = get_project_path("logs", "papertrading", "pt_trade_log.csv")
            daily_pnl_path        = get_project_path("logs", "papertrading", "pt_daily_pnl.csv")
            daily_pnl_today_path  = get_project_path("logs", "papertrading", "pt_daily_pnl_today.csv")
        
            order_type            = 'LIMIT'       # e.g., 'LIMIT'

            maker_fee              = 0.0002                  # 0.0002 maker fee
            taker_fee              = 0.0005                  # 0.0005 taker fee

            if order_type == 'LIMIT':
                fee_pct = maker_fee
            else:
                fee_pct = taker_fee
            
            # Functions for logging
            def log_daily_pnl(date, current_price, pnl_pct, daily_pnl_path, daily_pnl_today_path):    
                # Create empty files if they don't exist
                for path in [daily_pnl_path, daily_pnl_today_path]:
                    if not Path(path).exists():
                        pd.DataFrame([{
                            "Date": date,
                            "First Price": current_price,         
                            "Daily PnL (%)": 0.0,
                            "Benchmark PnL (%)": 0.0
                        }]).to_csv(path, index=False)
                        
                # Load today's file
                df_today = pd.read_csv(daily_pnl_today_path, parse_dates=["Date"])
                first_date = pd.to_datetime(df_today["Date"].iloc[0])
                if first_date.date() == date:
            
                    start_price = df_today["First Price"].iloc[0]
                    benchmark_pct = (current_price - start_price) / start_price
                          
                    df_today["Benchmark PnL (%)"] = df_today["Benchmark PnL (%)"].astype(float)
                    df_today.loc[0, "Benchmark PnL (%)"] = round(benchmark_pct, 4)    
                    df_today.loc[0, "Daily PnL (%)"] += round(pnl_pct, 4)
                    df_today.to_csv(daily_pnl_today_path, index=False)
                else:
                    # New day: move temp row to main file
                    df_main = pd.read_csv(daily_pnl_path, parse_dates=["Date"])
                    df_main = pd.concat([df_main, df_today], ignore_index=True)
                    df_main.to_csv(daily_pnl_path, index=False)
            
                    # Start new temp row
                    new_row = {"Date": date, "First Price": current_price, "Daily PnL (%)": pnl_pct, "Benchmark PnL (%)": 0.0}
                    pd.DataFrame([new_row]).to_csv(daily_pnl_today_path, index=False)
            
            def trade_log_entry(entry_time, entry_price, order_type, current_capital, trading_amount):
                trade_data = pd.DataFrame([{
                    "entry_time": entry_time,
                    "entry_price": entry_price,
                    "trade_type": "LONG", 
                    "order_type": order_type,
                    "capital_before": current_capital,
                    "trading_amount": trading_amount,
                    "currently_trading": True,
                    "exit_time": str(timestamp),         
                    "exit_price": entry_price,
                    "realized_pnl": 0.0,
                    "realized_pnl_pct": 0.0,
                    "capital_after": current_capital
                }])

                trade_data.to_csv(active_path, index=False, mode='w', header=True)
            
            def trade_log_update(timestamp, current_price):
                if not Path(active_path).exists():
                    return
                    
                df = pd.read_csv(active_path)
            
                if df.empty or not df["currently_trading"].iloc[-1]:
                    return
            
                entry_price         = df["entry_price"].iloc[-1]
                trading_amount      = df["trading_amount"].iloc[-1]
                capital_before      = df["capital_before"].iloc[-1]
            
                price_change_pct    = (float(current_price) - float(entry_price)) / float(entry_price)
                temp_pnl            = price_change_pct * float(trading_amount) - fee
                temp_pnl_pct        = temp_pnl / capital_before
                temp_capital_after  = capital_before + temp_pnl
            
                df.loc[df.index[-1], "exit_time"] = str(timestamp)
                df.loc[df.index[-1], "exit_price"] = current_price
                df.loc[df.index[-1], "realized_pnl"] = round(temp_pnl, 2)
                df.loc[df.index[-1], "realized_pnl_pct"] = round(temp_pnl_pct, 4)
                df.loc[df.index[-1], "capital_after"] = round(temp_capital_after, 2)
            
                df.to_csv(active_path, index=False)
            
            def trade_log_exit(exit_time, exit_price, realized_pnl, realized_pnl_pct, current_capital):
                if not Path(active_path).exists():
                    print("No active trade found.")
                    return
            
                df = pd.read_csv(active_path)
            
                if df.empty or not df["currently_trading"].iloc[-1]:
                    print("No active trade to close.")
                    return
            
                # Retrieve key values
                entry_price = float(df["entry_price"].iloc[-1])
                trading_amount = float(df["trading_amount"].iloc[-1])
                capital_before = float(df["capital_before"].iloc[-1])
                
                # Update row
                df.loc[df.index[-1], "exit_time"] = str(exit_time)
                df.loc[df.index[-1], "exit_price"] = exit_price
                df.loc[df.index[-1], "realized_pnl"] = round(realized_pnl, 2)
                df.loc[df.index[-1], "realized_pnl_pct"] = round(realized_pnl_pct, 4)
                df.loc[df.index[-1], "capital_after"] = current_capital
                df.loc[df.index[-1], "currently_trading"] = False
            
                # Append to main trade log
                df.to_csv(log_path, mode='a', header=not Path(log_path).exists(), index=False)
            
                # Clear the active trade
                Path(active_path).unlink()  # Deletes the file
            
            # Fetch historical klines and start trading
            def wait_until_next_candle(timeframe, last_bucket):
                tf_map = {
                    '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
                    '1h': 60, '2h': 120, '4h': 240, '6h': 360, '8h': 480,
                    '12h': 720, '1d': 1440
                }
            
                interval_minutes = tf_map.get(timeframe)
                if interval_minutes is None:
                    raise ValueError(f"Unsupported timeframe: {timeframe}")
            
                while True:
                    now = dt.datetime.utcnow()
                    total_minutes = now.hour * 60 + now.minute
                    current_bucket = total_minutes // interval_minutes
            
                    if current_bucket != last_bucket and now.second >= 2:
                        return current_bucket  # Return updated tracker
            
                    time.sleep(0.5)
            
            def get_klines(symbol, interval, limit):
                    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
                    df = pd.DataFrame(klines, columns=[
                        'timestamp', 'open', 'high', 'low', 'close', 'volume',
                        'close_time', 'quote_asset_volume', 'num_trades',
                        'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
                    ])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df['date'] = df['timestamp'].dt.date 
                    df['close'] = df['close'].astype(float)
                    df = df[['date', 'timestamp', 'close']].iloc[:-1]
                    return df
            
            # Fetch available balance
            def get_available_balance(client_futures):
                try:
                    account_info = client_futures.balance()
                    usdt_balance = next((item for item in account_info if item['asset'] == 'USDT'), None)
                    
                    if usdt_balance:
                        return float(usdt_balance['availableBalance'])
                    else:
                        print("❌ Could not retrieve USDT balance.")
                        return None
            
                except Exception as e:
                    print(f"⚠️ Error fetching balance: {e}")
                    return None
            
            # Telegram message
            def send_telegram_trade_alert(message):
                url = f"https://api.telegram.org/bot{Telegram_bot_token}/sendMessage"
                payload = {"chat_id": Telegram_chat_id, "text": message}
                requests.post(url, data=payload)
            
            # Trading conditions
            last_bucket           = None              # Tracking of candles
            currently_trading     = False
            rsi_was_above_exit    = False
            current_capital       = get_available_balance(client_futures)
            
            send_telegram_trade_alert(
                f"Zenna is now active:\n"
                f"• Symbol: {symbol}\n"
                f"• Timeframe: {timeframe}\n"
                f"• Risk per trade: {risk_per_trade}\n"
                f"• Leverage: {leverage}\n"
                f"• RSI Window: {rsi_window}\n"
                f"• RSI Entry: {rsi_entry}\n"
                f"• RSI Exit: {rsi_exit}\n"
                f"• RSI Execution: {rsi_exit_exec}"
            )
        
            # Start trading
            while True:
                last_bucket = wait_until_next_candle(timeframe, last_bucket)
            
                # Download and prepare data
                df = get_klines(symbol, timeframe, int(rsi_window) + 2)
                
                # Calculate RSI based on rsi_window
                df['RSI']             = round(vbt.RSI.run(df['close'], window=int(rsi_window)).rsi, 2)
                
                # Only keep most recent record
                df                    = df.tail(1)
                    
                # Trading variables
                df['entry']           = False
                df['exit']            = False
                pnl_pct               = 0.0                         # Initialize PnL for each loop iteration
                rsi                   = float(df['RSI'].iloc[0])
                timestamp             = df['timestamp'].iloc[0]
                current_price         = df['close'].iloc[0]
                date                  = df['date'].iloc[0]

                # Open trade?
                if not currently_trading:
                    if rsi < rsi_entry:   
                        
                        currently_trading        = True 
                        df['entry']              = True                       
                        rsi_was_above_exit       = False  # Reset RSI tracking
                        entry_price              = current_price
                        entry_time               = timestamp
                        trading_amount           = (risk_per_trade * current_capital) * leverage
                        fee                      = fee_pct * trading_amount
                       
                        send_telegram_trade_alert(
                            f"	🌱 Zenna OPENED position:\n"
                            f"• Symbol: {symbol}\n"
                            f"• Date: {entry_time}\n"
                            f"• Price: ${entry_price}\n"
                            f"• Trade Capital: ${trading_amount:.2f}"
                        )
                        
                        trade_log_entry(entry_time, entry_price, order_type, current_capital, trading_amount)
            
                else:
                    # Update trade logging
                    trade_log_update(timestamp, current_price)

                    # Exit trade?
                    if rsi > rsi_exit:
                        rsi_was_above_exit      = True              # First exit condition
                        
                    if rsi_was_above_exit and rsi < rsi_exit_exec:  # Second exit condition
                        
                        currently_trading        = False
                        df['exit']               = True
                        exit_price               = current_price 
                        exit_time                = timestamp
                        price_change_pct         = (exit_price - entry_price) / entry_price # JUST FOR TESTING
                        realized_pnl             = price_change_pct * trading_amount - fee 
                        realized_pnl_pct         = realized_pnl / current_capital
                        current_capital          += realized_pnl
                        pnl_pct                  += realized_pnl_pct
            
                        send_telegram_trade_alert(
                            f"🍃 Zenna CLOSED position:\n"
                            f"• Symbol: {symbol}\n"
                            f"• Entry Date: {entry_time}\n"
                            f"• Exit Date: {exit_time}\n"
                            f"• Price: ${exit_price}\n"
                            f"• PnL: ${realized_pnl:.2f}\n"
                            f"• PnL: {realized_pnl_pct:.2f}%"
                        )
            
                        trade_log_exit(exit_time, exit_price, realized_pnl, realized_pnl_pct, current_capital)
                        
                # Create or update daily PnL file
                log_daily_pnl(date, current_price, pnl_pct, daily_pnl_path, daily_pnl_today_path)
                    
                # Append the most recent candle information to CSV
                df.to_csv(
                    dataframe_path,
                    mode="a",
                    header=not Path(dataframe_path).exists(),
                    index=False,
                    encoding="utf-8"
                )
            
                # Validate data integrity
                if df.empty:
                    print("⚠️ Warning: Data fetched successfully but contains no rows.")
            
                time.sleep(10)

    except KeyboardInterrupt:
        send_telegram_trade_alert("Zenna has gracefully stopped.")
        sys.exit(0)

    except Exception as e:
        send_telegram_trade_alert(
            f"🔔 Error while Zenna was running:\n{type(e).__name__}: {str(e)}"
        )
        print(json.dumps({"error": f"{type(e).__name__}: {str(e)}"}))
        sys.exit(1)

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[-1] not in ("start", "check"):
        print(json.dumps({"error": "Missing mode: 'start' or 'check'."}))
        sys.exit(1)

    mode = args[-1]
    args = args[:-1]

    if mode == "check":
        print(json.dumps({"status": "ready"}))
    elif mode == "start":          
        try:
            run_paper_trading_bot(
                symbol=args[0],
                timeframe=args[1],
                risk_per_trade=float(args[2]),
                leverage=int(args[3]),
                rsi_window=int(args[4]),
                rsi_entry=float(args[5]),
                rsi_exit=float(args[6]),
                rsi_exit_exec=float(args[7])
            )
    
        except Exception as e:
            # Catch any exception and return it as valid JSON to Telegram
            error_output = {"error": f"{type(e).__name__}: {str(e)}"}
            print(json.dumps(error_output))

#jupyter nbconvert --to script 5_Paper_Trading_Bot_TG-250413.ipynb