# SharePoint functions
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

import psutil
import pandas as pd
from apps.utils.sharepoint import upload_file_to_sharepoint
from datetime import datetime
from pathlib import Path

def monitor_and_log_memory(memory_log_file, upload_to_sharepoint_fn=None):
    process = psutil.Process()
    mem_in_mb = process.memory_info().rss / 1024 ** 2

    log_entry = {
        "Timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "Memory_MB": round(mem_in_mb, 2)
    }

    df_entry = pd.DataFrame([log_entry])

    # Ensure folder exists
    Path(memory_log_file).parent.mkdir(parents=True, exist_ok=True)

    # Append to CSV
    Path(memory_log_file).parent.mkdir(parents=True, exist_ok=True)
    df_entry.to_csv(memory_log_file, mode='a', header=not Path(memory_log_file).exists(), index=False)

    # Upload to SharePoint if a function is passed
    if upload_to_sharepoint_fn:
        upload_file_to_sharepoint(memory_log_file)
