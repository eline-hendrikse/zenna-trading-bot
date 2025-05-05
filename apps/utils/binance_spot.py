# Spot order functions
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

import time
import requests
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from requests.exceptions import RequestException
from decimal import Decimal, ROUND_DOWN
from apps.utils.telegram import send_message
from apps import config_loader

def init_client():
    return Client(config_loader.api_key, config_loader.api_secret)

client = init_client()

# Binance call that retries when API call fails
def safe_binance_call(method_name, *args, retries=5, delay=5, **kwargs):
    global client

    for attempt in range(1, retries + 1):
        try:
            method = getattr(client, method_name)
            return method(*args, **kwargs)
        except (RequestException, BinanceAPIException, BinanceRequestException) as e:
            print(f"Zenna was not able to connect with Binance. Attempt {attempt} failed: {e}. Will try again in {delay} seconds.")
            time.sleep(min(delay * (2 ** (retries - 1)), 30))
            client = init_client()
        except AttributeError:
            raise ValueError(f"🔔 Method '{method_name}' not found on Binance client")
    
    raise ConnectionError(f"🔔 Failed to call {method_name}' after {retries} retries. A manual recovery is needed.")
    
# Binance functions
def get_spot_balance():
    spot_account_info     = safe_binance_call("get_account")
    spot_balances         = spot_account_info["balances"]
    spot_usdt             = next((b for b in spot_balances if b["asset"] == "USDT"), None)
    if not spot_usdt:
        send_reply(chat_id, "Could not find USDT Spot balance.")
        return
    
    spot_balance          = float(spot_usdt["free"])
    spot_available        = spot_balance  # No locked margin in spot trading
    return spot_available, spot_balances

def get_current_capital():
    spot_available, spot_balances = get_spot_balance()
    spot_total_value       = spot_available
    
    # Check open spot positions (assets ≠ USDT)
    spot_positions = [
        b for b in spot_balances
        if b["asset"] != "USDT" and (float(b["free"]) + float(b["locked"])) > 0
    ]
    
    spot_is_trading        = len(spot_positions) > 0

    # Fetch USDT prices for open positions
    prices                     = requests.get("https://api.binance.com/api/v3/ticker/price").json()
    price_lookup               = {p["symbol"]: float(p["price"]) for p in prices}

    for b in spot_positions:
        asset                      = b["asset"]
        amount                     = round(float(b["free"]) + float(b["locked"]), 6)
        symbol                     = f"{asset.upper()}USDT"
        reverse                    = f"USDT{asset.upper()}"
        symbol_price               = price_lookup.get(symbol)
        reverse_price              = price_lookup.get(reverse)
        
        if symbol_price:
            value = amount * symbol_price
        elif reverse_price and reverse_price != 0:
            value = amount / reverse_price
        else:
            continue

        spot_total_value           += value

    current_capital            = round(spot_total_value, 2)
    return current_capital

def get_lot_size_info(symbol):
    info                  = safe_binance_call("get_symbol_info", symbol)
    
    for f in info["filters"]:
        if f["filterType"] == "LOT_SIZE":
            step_size             = f["stepSize"]
            min_qty               = float(f["minQty"])
            return step_size, min_qty
    raise ValueError(f"Minimale step size and quantity for {symbol} not found.")

def get_safe_quantity(quantity, step_size):
    decimals               = len(step_size.rstrip('0').split('.')[-1])
    factor                 = 10 ** decimals
    floored                = int(quantity * factor) / factor
    return floored

def buy_spot_position(symbol, risk_per_trade, step_size, min_qty):
    try:
        base_asset             = "USDT"
        asset                  = symbol.replace("USDT", "")
        
        # Get latest price
        current_price          = float(safe_binance_call("get_symbol_ticker", symbol=symbol)["price"])

        # Calculate quantity to buy
        spot_available, _      = get_spot_balance()
        raw_qty                = (spot_available * risk_per_trade) / current_price
        safe_qty               = get_safe_quantity(raw_qty, step_size)
        total_value            = safe_qty * current_price
        
        if safe_qty < min_qty:
            msg = (
                f"🔔 Unable to buy {asset}: quantity {safe_qty} "
                f"is below minimal order quantity {min_qty:.5f}."
            )
            send_message(msg)
            return

        min_order_size         = 5   # https://www.binance.com/en/trade-rule
        if total_value < min_order_size:
            msg = (
                f"🔔 Unable to buy {asset}: trading amount ${total_value:.2f} "
                f"is below the minimum order size of ${min_order_size}."
            )
            send_message(msg)
            return

        # Place market buy order
        safe_qty               = str(Decimal(str(safe_qty)).normalize())
        
        order = safe_binance_call(
            "order_market_buy",
            symbol=symbol,
            quantity=safe_qty
        )

        msg = f"Zenna bought {safe_qty} {asset}: total value ~${total_value:.2f}"
        send_message(msg)
        return order

    except Exception as e:
        print(f"🔔 Unexpected error in binance_spot.py: {type(e).__name__}: {e}")
        send_message(f"🔔 Unexpected error in binance_spot.py: {type(e).__name__}: {e}")

def sell_spot_position(symbol, step_size, min_qty, percentage=1):
    try:
        asset                  = symbol.replace("USDT", "")
        account                = safe_binance_call("get_account")
        balance                = next((b for b in account["balances"] if b["asset"] == asset), None)

        if not balance:
            msg                    = f"🔔 No balance information for {asset}"
            send_message(msg)
            return

        free_qty               = float(balance["free"])
        
        if free_qty == 0:
            msg                    = f"🔔 Unable to sell {asset}: the balance is zero."
            send_message(msg)
            return
        
        # Fetch Binance limits
        step_size, min_qty     = get_lot_size_info(symbol)
        
        # Calculate and round quantity
        raw_qty                = free_qty * percentage
        safe_qty               = get_safe_quantity(raw_qty, step_size)

        if safe_qty < min_qty:
            msg = (
                f"🔔 Unable to sell {asset}: quantity {safe_qty} "
                f"is below the minimum order size of {min_qty:.5f}."
            )
            send_message(msg)
            return
            
        min_order_size        = 5 # https://www.binance.com/en/trade-rule
        current_price         = float(safe_binance_call("get_symbol_ticker", symbol=symbol)["price"])
        total_value           = safe_qty * current_price
        
        if total_value < min_order_size:
            msg = (
                f"🔔 Unable to sell {asset}: trading amount ${total_value:.2f} "
                f"is below the minimum order size of ${min_order_size}."
            )
            send_message(msg)
            return
        
        # Place market order
        safe_qty               = str(Decimal(str(safe_qty)).normalize())
        
        order = safe_binance_call("order_market_sell", 
            symbol=symbol,
            quantity=safe_qty
        )

        msg                    = f"Zenna sold {safe_qty} {asset}: total value ~${total_value:.2f}"
        send_message(msg)
        return order

    except Exception as e:
        print(f"🔔 Unexpected error in binance_spot.py: {type(e).__name__}: {e}")
        send_message(f"🔔 Unexpected error in binance_spot.py: {type(e).__name__}: {e}")

