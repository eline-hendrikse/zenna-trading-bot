# Handler for /balance
import requests
import sys
import os
from binance.client import Client
from pathlib import Path
from apps.utils.binance_spot import safe_binance_call, get_spot_balance
from apps.utils.telegram import send_reply
from apps.config_loader import api_key, api_secret

def handle(chat_id, *_):
    try:
        spot_available, spot_balances   = get_spot_balance()
        spot_total_value                = spot_available
        
        # Check open spot positions (assets ≠ USDT)
        spot_positions = [
            b for b in spot_balances
            if b["asset"] != "USDT" and (float(b["free"]) + float(b["locked"])) > 0
        ]
        
        spot_is_trading               = len(spot_positions) > 0
        
        # Prepare message
        msg      = f"Spot:\n"
        
        if not spot_is_trading:
            msg += f"• Available USDT            : ${spot_available:.2f}\n"
            msg += f"• No other asset holdings.\n"
        else:
            msg += f"• Available USDT            : ${spot_available:.2f}\n"
            msg += f"• Open Holdings             : {len(spot_positions)}\n"

            # Fetch USDT prices for open positions
            prices                      = requests.get("https://api.binance.com/api/v3/ticker/price").json()
            price_lookup                = {p["symbol"]: float(p["price"]) for p in prices}
        
            for b in spot_positions:
                asset                       = b["asset"]
                amount                      = round(float(b["free"]) + float(b["locked"]), 6)
                symbol                      = f"{asset.upper()}USDT"
                reverse                     = f"USDT{asset.upper()}"
                symbol_price                = price_lookup.get(symbol)
                reverse_price               = price_lookup.get(reverse)
                
                if symbol_price:
                    value = amount * symbol_price
                elif reverse_price and reverse_price != 0:
                    value = amount / reverse_price
                else:
                    msg += f"   • No price found for {asset}\n"
                    continue
        
                msg += f"   • {asset}: ${value:.2f} ({amount})\n"
                spot_total_value            += value

            msg += f"• Total Value                    : ~${spot_total_value:.2f}\n"
            
        # Get futures balances
        futures_balances              = safe_binance_call("futures_account_balance")
        futures_usdt                  = next((b for b in futures_balances if b["asset"] == "USDT"), None)
        if not futures_usdt:
            send_reply(chat_id, "🔔 Could not find USDT Futures balance.")
            return

        futures_balance               = float(futures_usdt["balance"])
        futures_available             = float(futures_usdt["availableBalance"])

        # Check futures open positions
        futures_positions             = safe_binance_call("futures_position_information")
        futures_open_positions        = [p for p in futures_positions if float(p["positionAmt"]) != 0]
        futures_is_trading            = len(futures_open_positions) > 0

        # Get futures margin info
        futures_account_info          = safe_binance_call("futures_account")
        futures_total_margin          = float(futures_account_info["totalMaintMargin"])
        futures_wallet_balance        = float(futures_account_info["totalWalletBalance"])
        futures_margin_usage          = 100 * (futures_total_margin / futures_wallet_balance) if futures_wallet_balance else 0

        msg += f"\nFutures:\n"
        
        if not futures_is_trading:
            msg += f"• Available USDT            : ${futures_available:.2f}\n"
            msg += f"• No open trades on Binance Futures.\n"
        else:
            msg += f"• Total Balance             : ${futures_balance:.2f}\n"
            msg += f"• Open Positions            : {len(futures_open_positions)}\n"
            msg += f"• Available USDT            : ${futures_available:.2f}\n"
            msg += f"• Margin Usage              : {futures_margin_usage:.2f}%"

        send_reply(chat_id, msg)

    except Exception as e:
        send_reply(chat_id, f"🔔 Failed to fetch live balance:\n{type(e).__name__}: {str(e)}")

