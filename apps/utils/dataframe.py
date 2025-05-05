# Dataframe functions
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

import time
import pandas as pd
import vectorbt as vbt
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from requests.exceptions import RequestException
from apps import config_loader

def init_client():
    return Client(config_loader.api_key, config_loader.api_secret)

client = init_client()

# Binance call. Retries when API call fails.
def safe_binance_call(method_name, *args, retries=3, delay=5, **kwargs):
    global client

    for attempt in range(1, retries + 1):
        try:
            method = getattr(client, method_name)
            return method(*args, **kwargs)
        except (RequestException, BinanceAPIException, BinanceRequestException) as e:
            print(f"Zenna was not able to connect with Binance. Attempt {attempt} failed: {e}. Will try again in {delay} seconds.")
            time.sleep(delay)
            client = init_client()
        except AttributeError:
            raise ValueError(f"🔔 Method '{method_name}' not found on Binance client")
    
    raise ConnectionError(f"🔔 Failed to call {method_name}' after {retries} retries. A manual recovery is needed.")

# Binance functions
def get_klines(symbol, interval, limit, retries=3, delay=5):
    klines = safe_binance_call("get_klines", 
        symbol=symbol, interval=interval, limit=limit
    )
    
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'num_trades',
        'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['date'] = df['timestamp'].dt.date 
    df[['open', 'high', 'low', 'close']] = df[[
        'open', 'high', 'low', 'close']].astype(float)  
    df = df[['date', 'timestamp', 'open', 'high', 'low', 'close']].iloc[:-1]
    return df

# Function to fetch historical OHLCV data from Binance Futures (also used for Spot trading)
def get_historical_data(symbol, interval, start_ms, end_ms, retries=3, delay=5):

    klines = safe_binance_call("get_historical_klines", 
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
    df = df[['date', 'timestamp', 'open', 'high', 'low', 'close']]     # Keep only relevant columns
    return df