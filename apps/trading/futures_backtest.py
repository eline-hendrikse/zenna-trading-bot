# Backtest
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

import pandas as pd
import vectorbt as vbt
import plotly.graph_objects as go
import plotly.express as px
import datetime as dt
import json
from apps import config_loader
from apps.config_loader import get_project_path
from apps.utils.telegram import send_message
from binance.client import Client
from datetime import datetime, timedelta

# Initialize Binance client
client = Client(config_loader.api_key, config_loader.api_secret)

def run_backtest(
    symbol, timeframe, risk_per_trade, leverage, start_date, start_time, end_date, end_time, 
    rsi_window, rsi_entry, rsi_exit, rsi_exit_exec):
    
    # Define global variables
    dataframe_path         = get_project_path("logs", "backtest", "bt_dataframe.csv") 
    log_path               = get_project_path("logs", "backtest", "bt_trade_log.csv")
    daily_pnl_path         = get_project_path("logs", "backtest", "bt_daily_pnl.csv")

    start_capital          = 100.00                  # e.g., 100.00 starting USDT balance.
    slippage_pct           = 0.0001                  # 0.0001 slippage on price
    
    order_type             = 'LIMIT'                 # e.g., 'LIMIT'
    funding_rate           = 0.003
    maker_fee              = 0.0002                  # 0.0002 maker fee
    taker_fee              = 0.0005                  # 0.0005 taker fee

    # Rolling period or manual dates
    start_time             = start_date + ' ' + start_time  # real-time + 2h - 20m (timeframe + m/h/d)
    end_time               = end_date + ' ' + end_time                # real-time + 2h

    # Determine fee based on order type
    if order_type == 'LIMIT':
        fee_pct = maker_fee
    else:
        fee_pct = taker_fee

    from datetime import datetime, time

    # Fundings fees 
    # https://www.binance.com/en/futures/funding-history/perpetual/real-time-funding-rate
    
    funding_times = [time(0, 0), time(8, 0), time(16, 0)]
    last_funding_time = None  # set when funding is applied
    
    def should_apply_funding(now: datetime, last_applied: datetime):
        if not last_applied:
            return True  # first-time funding
    
        for ft in funding_times:
            funding_datetime = now.replace(hour=ft.hour, minute=ft.minute, second=0, microsecond=0)
            if last_applied < funding_datetime <= now:
                return True
    
        return False

    def apply_funding_fee(position_size, funding_rate=0.003):
        funding_fee = position_size * funding_rate
    return funding_fee
    
    # Set KLINES based on timeframe
    tf_map = {
        '1m': Client.KLINE_INTERVAL_1MINUTE, 
        '3m': Client.KLINE_INTERVAL_3MINUTE, 
        '5m': Client.KLINE_INTERVAL_5MINUTE, 
        '15m': Client.KLINE_INTERVAL_15MINUTE, 
        '30m': Client.KLINE_INTERVAL_30MINUTE,
        '1h': Client.KLINE_INTERVAL_1HOUR,
        '2h': Client.KLINE_INTERVAL_2HOUR,
        '4h': Client.KLINE_INTERVAL_4HOUR,
        '6h': Client.KLINE_INTERVAL_6HOUR,
        '8h': Client.KLINE_INTERVAL_8HOUR,
        '12h': Client.KLINE_INTERVAL_12HOUR, 
        '1d': Client.KLINE_INTERVAL_1DAY
    }
    
    interval = tf_map.get(timeframe)
    if interval is None:
        print(f"❌ Error: Unsupported timeframe {timeframe}")
    
    # Convert to milliseconds
    start_ms               = int(dt.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
    end_ms                 = int(dt.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)

    # Delete existing historical data   
    if dataframe_path.exists():
        dataframe_path.unlink()
    if log_path.exists():
        log_path.unlink()
        
    # Function to fetch historical OHLCV data from Binance Futures
    def get_historical_data(symbol, interval):
        
        klines = client.get_historical_klines(
            symbol, interval, start_str=start_ms, end_str=end_ms
        )
        df = pd.DataFrame(klines, columns=[
            "timestamp", "open", "high", "low", "close", "volume", 
            "close_time", "quote_asset_volume", "num_trades", 
            "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
        ])          
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")       # Convert timestamp to datetime 
        df['date'] = df['timestamp'].dt.date
        df[["open", "high", "low", "close"]] = df[[
            "open", "high", "low", "close"]].astype(float)                 # Convert prices to float
        df = df[['date', 'timestamp', 'open', 'high', 'low', 'close']]             # Keep only relevant columns
        return df

    # Fetch historical OHLCV data
    df = get_historical_data(symbol, interval)
    
    # Compute RSI
    df['RSI']    = vbt.RSI.run(df["close"], window=int(rsi_window)).rsi
    
    # Save the updated DataFrame to CSV
    df.to_csv(dataframe_path, index=False)
    
    # Validate data integrity
    if df.empty:
        print("⚠️ Warning: Data fetched successfully but contains no rows. Check your date range and asset symbol.")

    def calc_pnl(price, entry_price, trading_amount):
        exit_price               = price * (1 - slippage_pct)       
        price_change_pct         = (exit_price - entry_price) / entry_price
        pnl                      = price_change_pct * trading_amount - fee
        return pnl

    def calc_drawdown(price, entry_price, trading_amount, max_drawdown):
        pnl                      = calc_pnl(price, entry_price, trading_amount)
        pnl_pct                  = pnl / current_capital
        temp_capital             = current_capital + pnl                

        if temp_capital <= 0:
            pnl_pct                  = pnl_pct * 100
            send_message(
                f"This strategy would cause a negative balance.\n"
                f"• Symbol: {symbol}\n"
                f"• Date: {timestamp}\n"
                f"• Current PnL: {pnl_pct:.2f}%\n"
            )
                            
        if pnl_pct < max_drawdown:
            max_drawdown             = pnl_pct

        return max_drawdown
        
    # Execute backtesting
    current_capital       = float(start_capital)
    total_trades          = 0 
    total_wins            = 0
    total_losses          = 0
    open_trades           = 0
    entry_price           = 0           # To store the entry price of an open trade
    price_change_pct      = 0
    lowest_pnl_pct        = 0           # Store biggest loss in pct
    max_drawdown          = 0
    currently_trading     = False
    rsi_was_above_exit    = False       # Track if RSI was ever above 70
    trade                 = ""
    
    # Create a trade log (to store executed trades)
    trade_log             = []
    active_trades         = {}
    daily_pnl             = {}
    
    # Load historical dataset
    df                    = pd.read_csv(dataframe_path)
    
    # Loop through each record (using itertuples for efficiency) after RSI is calculated
    for row in df.itertuples(index=False):       
        date                  = row.date
        if date not in daily_pnl:
            daily_pnl[date] = 0  # Initialize daily PnL
            
        # Start trading after RSI window has passed
        if not pd.isna(row.RSI):  
            timestamp             = row.timestamp
            current_price         = row.close
            lowest_price          = row.low
            rsi                   = float(row.RSI)  
            pnl                   = 0           # Initialize PnL for each loop iteration

            if total_trades == 0:
                current_capital = float(start_capital)
            # else:
            #     current_capital += pnl  # Add profit/loss to capital

            # Entry conditions
            if not currently_trading:
                if rsi < rsi_entry:
                    currently_trading        = True
                    rsi_was_above_exit       = False  # Reset RSI tracking
                    entry_price              = current_price
                    trading_amount           = (risk_per_trade * current_capital) * leverage
                    fee                      = fee_pct * trading_amount
                    total_trades             += 1
    
                    # Store active trades in a dictionary until they exit
                    entry_timestamp          = timestamp  # Ensure this is the same as the key used in active_trades
    
                    active_trades[entry_timestamp] = {
                        "entry_time": timestamp,  # Entry timestamp
                        "entry_price": entry_price,
                        "trade_type": "LONG",
                        "order_type": order_type,
                        "capital_before": current_capital,
                        "trading_amount": trading_amount,
                        "currently_trading": True  # Trade is still open
                    }
                          
            else:
                # Calculate max drawdown and funding fees
                max_drawdown             = calc_drawdown(lowest_price, entry_price, trading_amount, max_drawdown)

                # TO DO
                if should_apply_funding(current_time, last_funding_time):
                    funding_fee = apply_funding_fee(position_size)
                    current_capital -= funding_fee
                    last_funding_time = current_time
    
                # Exit conditions
                if rsi > rsi_exit:
                    rsi_was_above_exit       = True   # First condition: RSI above rsi_exit
    
                if rsi_was_above_exit and rsi < rsi_exit_exec:       # Second condition: RSI drops below rsi_exit_exec
                    currently_trading        = False
                    pnl                      = calc_pnl(current_price, entry_price, trading_amount)                
                    pnl_pct                  = pnl / current_capital
                    daily_pnl[date]          += pnl_pct
                    current_capital          += pnl
    
                    if pnl > 0:
                        total_wins += 1
                    else:
                        total_losses += 1
                        if pnl_pct < lowest_pnl_pct:
                            lowest_pnl_pct = pnl_pct
    
                    if entry_timestamp in active_trades:
                        trade = active_trades.pop(entry_timestamp)  # Retrieve trade entry details
                        trade.update({
                            "exit_time": timestamp,  # Exit timestamp
                            "exit_price": current_price,
                            "pnl": pnl,
                            "pnl_pct": pnl_pct,
                            "capital_after": current_capital,
                            "currently_trading": False  # Trade is now closed
                        })
                        trade_log.append(trade)  # Append completed trade
        
        if max_drawdown <= -1:
            print(json.dumps("aborted")) 
            sys.exit(0)
            
    if currently_trading == True:
        # Calculate drawdown and unrealized PnL
        max_drawdown             = calc_drawdown(lowest_price, entry_price, trading_amount, max_drawdown)
        
        open_trades              += 1
        pnl                      = calc_pnl(current_price, entry_price, trading_amount)  
        pnl_pct                  = pnl / current_capital
        daily_pnl[date]          += pnl_pct
        current_capital          += pnl
        
        if pnl > 0:
            total_wins += 1
        else:
            total_losses += 1
            if pnl_pct < lowest_pnl_pct:
                lowest_pnl_pct = pnl_pct
    
        if entry_timestamp in active_trades:
            trade = active_trades.pop(entry_timestamp)  # Retrieve trade entry details
            trade.update({
                "exit_time": timestamp,  # Exit timestamp
                "exit_price": current_price,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "capital_after": current_capital,
                "currently_trading": True 
            })
            trade_log.append(trade)  # Append completed trade
        
    closed_trades         = total_trades - open_trades
    win_rate              = (total_wins / total_trades) * 100   
    total_return          = (current_capital - start_capital) / start_capital * 100
    benchmark_return      = (df.iloc[-1].close - df.iloc[0].open) / df.iloc[0].close * 100
    lowest_pnl_pct        = lowest_pnl_pct * 100
    max_drawdown          = max_drawdown * 100
    comparison_result     = "✅ Outperformed Benchmark" if total_return > benchmark_return else "❌ Underperformed Benchmark"
    
    # Convert trade log to DataFrame and save to CSV
    trade_log_df = pd.DataFrame(trade_log)
    trade_log_df.to_csv(log_path, index=False)
    
    # Convert daily PnL to DataFrame
    daily_pnl_df = pd.DataFrame(list(daily_pnl.items()), columns=["Date", "Daily PnL (%)"])
    
    # Save to CSV
    daily_pnl_df.to_csv(daily_pnl_path, index=False)

    result = {
        "Start Date": f"{start_time}",
        "End Date": f"{end_time}",
        "Start Value": f"{start_capital:.2f}",
        "End Value": f"{current_capital:.2f}",
        "Total Return": f"{total_return:.2f}%",
        "Benchmark Return": f"{benchmark_return:.2f}%",
        "Total Trades": total_trades,
        "Total Closed Trades": closed_trades,
        "Total Open Trades": open_trades,
        "Open Trade PnL": f"{pnl_pct:.2f}%",
        "Win Rate": f"{win_rate:.0f}%",   
        "Total Winning Trades": f"{total_wins:.0f}",   
        "Total Losing Trades": f"{total_losses:.0f}",  
        "Lowest PnL": f"{lowest_pnl_pct:.2f}%",
        "Max Drawdown": f"{max_drawdown:.2f}%",
        "Performance vs Benchmark": comparison_result

    }
    print(json.dumps(result)) 

    # Add cumulative PnL
    # Load daily PnL CSV
    df_pnl            = pd.read_csv(daily_pnl_path)
    
    # Calculate Cumulative PnL: (1 + Daily PnL / 100).cumprod() - 1
    df_pnl["Cumulative PnL (%)"] = (1 + df_pnl["Daily PnL (%)"]).cumprod() - 1
    
    # Add Benchmark Pnl (buy & hold strategy)
    first_open = df.groupby("date")["open"].first().reset_index()
    last_close = df.groupby("date")["close"].last().reset_index()
    
    daily_benchmark = first_open.merge(last_close, on="date")
    daily_benchmark["Benchmark PnL (%)"] = ((daily_benchmark["close"] - daily_benchmark["open"]) / daily_benchmark["open"])
    
    daily_benchmark = daily_benchmark.sort_values("date")
    df_pnl["Cumulative Benchmark PnL (%)"] = (1 + daily_benchmark["Benchmark PnL (%)"]).cumprod() - 1
    
    # Save updated CSV
    df_pnl.to_csv(daily_pnl_path, index=False)    

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]

    try:
        run_backtest(
            symbol=args[0],
            timeframe=args[1],
            risk_per_trade=float(args[2]),
            leverage=int(args[3]),
            start_date=args[4],
            start_time=args[5],
            end_date=args[6],
            end_time=args[7],
            rsi_window=int(args[8]),
            rsi_entry=float(args[9]),
            rsi_exit=float(args[10]),
            rsi_exit_exec=float(args[11])
        )
    except Exception as e:
        # Catch any exception and return it as valid JSON to Telegram
        error_output = {"error": f"{type(e).__name__}: {str(e)}"}
        print(json.dumps(error_output))

#jupyter nbconvert --to script 2_Backtesting-TG-250413.ipynb





