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
import gc
from apps import config_loader
from apps.config_loader import get_project_path
from apps.utils.binance_spot import get_spot_balance, get_safe_quantity, get_lot_size_info
from apps.utils.telegram import send_message
from apps.utils.dataframe import get_klines
from apps.utils.sharepoint import async_sharepoint_file
from apps.utils.monitoring import monitor_and_log_memory
from datetime import datetime, timedelta

def run_paper_trading_bot(symbol, timeframe, risk_per_trade, rsi_window, rsi_entry, rsi_exit, rsi_exit_exec):
    try:
        while True:
            # Define global variables
            step_size, min_qty     = get_lot_size_info(symbol)
            start_capital          = 100.0            
            order_type             = 'MARKET'               # e.g., 'MARKET'
            maker_commission       = 0.001                  # 0.001 maker commission
            taker_commission       = 0.001                  # 0.001 taker commission

            if order_type == 'MARKET':
                commission_pct = maker_commission
            else:
                commission_pct = taker_commission                   

            log_dir                = Path("logs/papertrades/spot")
            active_trade_file      = os.path.join(log_dir, "active_trade.csv")
            pnl_today_file         = os.path.join(log_dir, "pnl_today.csv")

            # Monitor memory usage
            last_memory_check      = time.time()
            memory_log_file        = os.path.join(log_dir, "system", "memory_log.csv")
            
            # Functions for logging
            def log_path(filename, ext):        
                now                    = datetime.utcnow()
                year                   = str(now.year)
                month                  = str(now.strftime("%m"))
                log_path               = os.path.join(log_dir, year, month + '_' + filename + ext)
                return log_path

            def log_daily_pnl(date, current_price, pnl_pct):
                Path(pnl_today_file).parent.mkdir(parents=True, exist_ok=True)
                if not Path(pnl_today_file).exists():
                    # Create today's file only
                    df_today = pd.DataFrame([{
                        "Date": date,
                        "First Price": current_price,
                        "Last Price": current_price,
                        "Daily PnL (%)": 0.0,
                        "Benchmark PnL (%)": 0.0
                    }])
                    df_today.to_csv(pnl_today_file, index=False)
                    async_sharepoint_file("upload", pnl_today_file)
                    del df_today
                    gc.collect()
                    return 
            
                # Load today's file
                df_today = pd.read_csv(pnl_today_file, parse_dates=["Date"])
                first_date = pd.to_datetime(df_today["Date"].iloc[0])
            
                if first_date.date() == date:
                    # Update PnL and benchmark
                    start_price = df_today["First Price"].iloc[0]
                    benchmark_pct = (current_price - start_price) / start_price
            
                    df_today.loc[0, "Last Price"] = round(current_price, 2)
                    df_today.loc[0, "Benchmark PnL (%)"] = round(benchmark_pct, 4)
                    df_today.loc[0, "Daily PnL (%)"] += round(pnl_pct, 4)
            
                    df_today.to_csv(pnl_today_file, index=False)
                    async_sharepoint_file("upload", pnl_today_file)
                    del df_today
                    gc.collect()
                else:
                    # It's a new day → move yesterday’s data to main file
                    Path(daily_pnl_file).parent.mkdir(parents=True, exist_ok=True)
                    if not Path(daily_pnl_file).exists():
                        df_main = pd.DataFrame(columns=df_today.columns)
                    else:
                        df_main = pd.read_csv(daily_pnl_file, parse_dates=["Date"])
            
                    df_main = pd.concat([df_main, df_today], ignore_index=True)
                    df_main.to_csv(daily_pnl_file, index=False)
                    async_sharepoint_file("upload", daily_pnl_file)
                    del df_main
                    gc.collect()
            
                    # Start today's temp row
                    new_row = {
                        "Date": date,
                        "First Price": current_price,
                        "Last Price": current_price,
                        "Daily PnL (%)": pnl_pct,
                        "Benchmark PnL (%)": 0.0
                    }
                    Path(pnl_today_file).parent.mkdir(parents=True, exist_ok=True)
                    pd.DataFrame([new_row]).to_csv(pnl_today_file, index=False)
                    async_sharepoint_file("upload", pnl_today_file)
                    
            def trade_log_entry(symbol, entry_time, entry_price, order_type, current_capital, trading_amount, entry_commission):
                capital_after             = float(current_capital) - float(entry_commission)
                
                trade_data = pd.DataFrame([{
                    "Symbol": symbol,
                    "Entry Time": entry_time,
                    "Entry Price": round(entry_price, 2),
                    "Trade Type": "BUY", 
                    "Order Type": order_type,
                    "Capital Before": round(current_capital, 2),
                    "Trading Amount": round(trading_amount, 2),
                    "Entry Commission": round(entry_commission, 2),
                    "First Exit Condition": False,
                    "Currently Trading": True,
                    "Exit Time": str(timestamp),         
                    "Exit Price": round(entry_price, 2),
                    "Realized PnL": 0.0,
                    "Realized PnL (%)": 0.0,
                    "Capital After": round(capital_after, 2),
                    "Exit Commission": 0.0
                }])
                
                Path(active_trade_file).parent.mkdir(parents=True, exist_ok=True)
                trade_data.to_csv(active_trade_file, index=False, mode='w', header=True)
                async_sharepoint_file("upload", active_trade_file)
                del trade_data
                gc.collect()
                
            def trade_log_update(timestamp, current_price, rsi_was_above_exit):
                
                df = pd.read_csv(active_trade_file)
            
                entry_price         = df["Entry Price"].iloc[-1]
                trading_amount      = df["Trading Amount"].iloc[-1]
                capital_before      = df["Capital Before"].iloc[-1]
                entry_commission    = df["Entry Commission"].iloc[-1] if "Entry Commission" in df.columns else 0
                first_exit_condition = df["First Exit Condition"].iloc[-1]
            
                price_change_pct    = (float(current_price) - float(entry_price)) / float(entry_price)
                temp_pnl            = price_change_pct * float(trading_amount) - float(entry_commission)
                temp_pnl_pct        = temp_pnl / capital_before
                temp_capital_after  = capital_before + temp_pnl

                if not first_exit_condition:
                    df.loc[df.index[-1], "First Exit Condition"] = rsi_was_above_exit
                df.loc[df.index[-1], "Exit Time"] = str(timestamp)
                df.loc[df.index[-1], "Exit Price"] = round(current_price, 2)
                df.loc[df.index[-1], "Realized PnL"] = round(temp_pnl, 2)
                df.loc[df.index[-1], "Realized PnL (%)"] = round(temp_pnl_pct, 4)
                df.loc[df.index[-1], "Capital After"] = round(temp_capital_after, 2)
            
                df.to_csv(active_trade_file, index=False)
                async_sharepoint_file("upload", active_trade_file)
                del df
                gc.collect()
                
            def trade_log_exit(exit_time, exit_price, realized_pnl, realized_pnl_pct, current_capital, exit_commission):
            
                df = pd.read_csv(active_trade_file)
            
                # Retrieve key values
                entry_price           = float(df["Entry Price"].iloc[-1])
                trading_amount        = float(df["Trading Amount"].iloc[-1])
                capital_before        = float(df["Capital Before"].iloc[-1])
                
                # Update row
                df.loc[df.index[-1], "Exit Time"] = str(exit_time)
                df.loc[df.index[-1], "Exit Price"] = round(exit_price, 2)
                df.loc[df.index[-1], "Realized PnL"] = round(realized_pnl, 2)
                df.loc[df.index[-1], "Realized PnL (%)"] = round(realized_pnl_pct, 4)
                df.loc[df.index[-1], "Capital After"] = round(current_capital, 2)
                df.loc[df.index[-1], "Exit Commission"] = round(exit_commission, 2)
                df.loc[df.index[-1], "First Exit Condition"] = False
                df.loc[df.index[-1], "Currently Trading"] = False
            
                # Append to main trade log
                Path(trade_file).parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(trade_file, mode='a', header=not Path(trade_file).exists(), index=False)
                async_sharepoint_file("upload", trade_file)
                del df
                gc.collect()
                
                # Clear the active trade
                Path(active_trade_file).unlink()  # Deletes the file
                async_sharepoint_file("delete", active_trade_file)
                
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
                    now                   = dt.datetime.utcnow()
                    total_minutes         = now.hour * 60 + now.minute
                    current_bucket        = total_minutes // interval_minutes
            
                    if current_bucket != last_bucket and now.second >= 2:
                        last_bucket           = current_bucket
                        return current_bucket  # Return updated tracker
                        
                    time.sleep(0.5)
            
            # Trading conditions
            last_bucket           = None
            current_bucket        = None              # Tracking of candles
            currently_trading     = Path(active_trade_file).exists()
            rsi_was_above_exit    = False
            current_capital       = start_capital
            
            send_message(
                f"Zenna is now active:\n"
                f"• Symbol: {symbol}\n"
                f"• Timeframe: {timeframe}\n"
                f"• Risk per trade: {risk_per_trade}\n"
                f"• RSI Window: {rsi_window}\n"
                f"• RSI Entry: {rsi_entry}\n"
                f"• RSI Exit: {rsi_exit}\n"
                f"• RSI Execution: {rsi_exit_exec}\n"
                f"• Open positions: {currently_trading}"
            )
        
            # Start trading
            while True:
                last_bucket = wait_until_next_candle(timeframe, last_bucket)
                current_time = time.time()
                if current_time - last_memory_check >= 60: # Log memory usage every 1 minute
                    monitor_and_log_memory(memory_log_file)
                    async_sharepoint_file("upload", memory_log_file)
                    last_memory_check = current_time
                
                # Define log file names
                dataframe_file         = log_path('dataframe', '.csv')
                daily_pnl_file         = log_path('daily_pnl', '.csv')
                trade_file             = log_path('trades', '.csv')
                
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

                        df['entry']              = True      
                        currently_trading        = True
                        rsi_was_above_exit       = False  # Reset RSI tracking
                        entry_price              = current_price
                        entry_time               = timestamp

                        raw_qty                  = (current_capital * risk_per_trade) / entry_price
                        safe_qty                 = get_safe_quantity(raw_qty, step_size)
                        trading_amount           = safe_qty * entry_price

                        entry_commission         = commission_pct * trading_amount
                       
                        send_message(
                            f"	🌱 Zenna OPENED position:\n"
                            f"• Symbol: {symbol}\n"
                            f"• Date: {entry_time}\n"
                            f"• Price: ${entry_price}\n"
                            f"• Trade Capital: ${trading_amount:.2f}\n"
                            f"• Commission: ${entry_commission:.2f}"
                        )
                        
                        trade_log_entry(symbol, entry_time, entry_price, order_type, current_capital, trading_amount, entry_commission)
            
                else:
                    # First exit condition
                    if rsi > rsi_exit:
                        rsi_was_above_exit       = True             
                        
                    # Update trade logging
                    trade_log_update(timestamp, current_price, rsi_was_above_exit)
                    
                    # Second exit condition
                    if rsi_was_above_exit and rsi < rsi_exit_exec: 

                        df['exit']               = True
                        currently_trading        = False
                        exit_price               = current_price 
                        exit_time                = timestamp

                        
                        # Load entry details
                        df_trade = pd.read_csv(active_trade_file)
                        entry_time               = df_trade["Entry Time"].iloc[-1]
                        entry_price              = float(df_trade["Entry Price"].iloc[-1])
                        trading_amount_entry     = float(df_trade["Trading Amount"].iloc[-1])
                        capital_before           = float(df_trade["Capital Before"].iloc[-1])
                        entry_commission         = float(df_trade["Entry Commission"].iloc[-1])
                        del df_trade
                        gc.collect()

                        price_change_pct         = (exit_price - entry_price) / entry_price 
                        print(f"Price Change {price_change_pct}")
                        raw_qty                  = price_change_pct * trading_amount_entry + trading_amount_entry
                        print(f"Raw_qty {raw_qty}")
                        trading_amount           = get_safe_quantity(raw_qty, step_size)
                        print(f"Trading amount {trading_amount}")
                        exit_commission          = commission_pct * trading_amount 

                        print(f"Exit Commission {exit_commission}")
                        realized_pnl             = price_change_pct * current_capital - entry_commission - exit_commission
                        print(f"realized_pnl {realized_pnl}")
                        realized_pnl_pct         = realized_pnl / current_capital
                        
                        current_capital          += realized_pnl
                        pnl_pct                  += realized_pnl_pct
            
                        send_message(
                            f"🍃 Zenna CLOSED position:\n"
                            f"• Symbol: {symbol}\n"
                            f"• Entry Date: {entry_time}\n"
                            f"• Exit Date: {exit_time}\n"
                            f"• Price: ${exit_price}\n"
                            f"• PnL: ${realized_pnl:.2f}\n"
                            f"• PnL: {realized_pnl_pct:.2f}%\n"
                            f"• Commission: ${exit_commission:.2f}"
                        )
                        trade_log_exit(exit_time, exit_price, realized_pnl, realized_pnl_pct, current_capital, exit_commission)
                        
                # Create or update daily PnL file
                log_daily_pnl(date, current_price, pnl_pct)

                # Append the most recent candle information to CSV
                Path(dataframe_file).parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(
                    dataframe_file,
                    mode="a",
                    header=not Path(dataframe_file).exists(),
                    index=False,
                    encoding="utf-8"
                )
                async_sharepoint_file("upload", dataframe_file)
                del df
                gc.collect()
            
                time.sleep(30)

    except KeyboardInterrupt:
        send_message("Zenna has gracefully stopped.")
        sys.exit(0)

    except Exception as e:
        send_message(
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
                rsi_window=int(args[3]),
                rsi_entry=float(args[4]),
                rsi_exit=float(args[5]),
                rsi_exit_exec=float(args[6])
            )
    
        except Exception as e:
            # Catch any exception and return it as valid JSON to Telegram
            error_output = {"Error in 'spot_paper_trading.py'. Error": f"{type(e).__name__}: {str(e)}"}
        print(json.dumps(error_output))

#jupyter nbconvert --to script 5_Paper_Trading_Bot_TG-250413.ipynb