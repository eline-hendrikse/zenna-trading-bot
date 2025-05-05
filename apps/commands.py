# Command router
from apps.utils.telegram import send_reply
from apps.handlers import backtest, balance, indicators, start_paper_trading, start_trading, status, stop_paper_trading, stop_trading

COMMANDS = {
    "/backtest": backtest.handle,
    "/balance": balance.handle,
    "/indicators": indicators.handle,
    "/start_paper_trading": start_paper_trading.handle,
    "/start_trading": start_trading.handle,
    "/status": status.handle,   
    "/stop_paper_trading": stop_paper_trading.handle,
    "/stop_trading": stop_trading.handle,
    "/commands": lambda chat_id, *_: send_reply(chat_id, format_commands(COMMANDS)),
}

def dispatch_command(chat_id, text):
    command = text.split()[0]
    handler = COMMANDS.get(command)
    if handler:
        handler(chat_id, text)
    else:
        send_reply(chat_id, "💭 Unknown command. Type /commands to see options.")

def format_commands(cmds):
    return "Available Commands:\n" + "\n".join(f"• {cmd}" for cmd in sorted(cmds))
