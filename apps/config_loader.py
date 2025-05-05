# Config and env loader
import os
from dotenv import load_dotenv
from pathlib import Path

try:
    env_path = Path(__file__).resolve().parent / ".env"
except NameError:
    env_path = Path(os.getcwd()) / "apps" / ".env"

load_dotenv(dotenv_path=env_path)

def get_project_path(*subpaths):
    try:
        # In .py files
        root_dir = Path(__file__).resolve().parent.parent
    except NameError:
        # In Jupyter Notebooks
        root_dir = Path.cwd().parent

    full_path = root_dir.joinpath(*subpaths)

    # Auto-create folder if it doesn't exist
    if full_path.suffix:
        # It's a file → ensure its parent folder exists
        full_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        # It's a directory → ensure it exists
        full_path.mkdir(parents=True, exist_ok=True)

    return full_path

def register_project_root():
    try:
        # In .py files
        project_root = Path(__file__).resolve().parent.parent
    except NameError:
        # In Jupyter Notebooks
        project_root = Path.cwd().parent

    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)
        
# Expose config variables
Telegram_bot_token        = os.getenv("TELEGRAM_BOT_TOKEN")
Telegram_chat_id          = os.getenv("TELEGRAM_CHAT_ID")
api_key                   = os.getenv("BINANCE_API_KEY")
api_secret                = os.getenv("BINANCE_API_SECRET")
client_id                 = os.getenv("CLIENT_ID")
tenant_id                 = os.getenv("TENANT_ID")    
client_secret             = os.getenv("CLIENT_SECRET") 

# Check if keys are loaded
if not Telegram_bot_token or not Telegram_chat_id or not api_key or not api_secret or not client_id or not tenant_id or not client_secret:
    raise ValueError("Missing API credentials. Check .env file location.")

