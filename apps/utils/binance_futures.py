# Spot order functions
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from binance.um_futures import UMFutures
from apps import config_loader

# Initialize Binance client
client_futures        = UMFutures(config_loader.api_key, config_loader.api_secret)