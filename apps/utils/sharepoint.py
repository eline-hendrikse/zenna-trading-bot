# SharePoint functions
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

import gc
import time
import requests
import threading
from apps import config_loader

# SharePoint details
site_url                 = "zenghetti.sharepoint.com:/sites/Zenna"
Graph_API_site_url       = f"https://graph.microsoft.com/v1.0/sites/{site_url}"
CLIENT_ID                = config_loader.client_id
TENANT_ID                = config_loader.tenant_id
CLIENT_SECRET            = config_loader.client_secret
SCOPES                   = ["https://graph.microsoft.com/.default"]

# SharePoint call that retries when API call fails
def safe_sharepoint_call(method, url, headers=None, data=None, retries=5, delay=5):
    attempt = 0
    while attempt < retries:
        try:
            if method == "POST":
                response = requests.post(url, headers=headers, data=data, timeout=10)
            elif method == "PUT":
                response = requests.put(url, headers=headers, data=data, timeout=10)
            elif method == "GET":
                response = requests.get(url, headers=headers, timeout=10)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=10)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response  

        except requests.exceptions.HTTPError as e:
            attempt += 1
            resp = e.response
            if resp is not None:
                print(f"🔔 SharePoint {method} HTTP error (Attempt {attempt}/{retries}): {resp.status_code} - {resp.text}")
            else:
                print(f"🔔 SharePoint {method} HTTP error without response (Attempt {attempt}/{retries}).")
        except Exception as e:
            attempt += 1
            print(f"🔔 SharePoint {method} general error (Attempt {attempt}/{retries}): {e}")

        if attempt >= retries:
            print(f"🔔 Max retries reached. Continuing without SharePoint action.")
            return None
        time.sleep(min(delay * (2 ** (attempt - 1)), 30))

def get_access_token():
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": SCOPES[0]
    }
    response = requests.post(token_url, data=payload)
    response.raise_for_status()
    return response.json()["access_token"]

def get_site_ID(access_token, retries=5, delay=5):
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(Graph_API_site_url, headers=headers, timeout=10)

            if response.status_code == 200:
                site_info = response.json()
                return site_info["id"]
            else:
                print(f"🔔 Failed to retrieve SharePoint Site ID (Attempt {attempt}/{retries}): {response.status_code} - {response.text}")

        except requests.exceptions.RequestException as e:
            print(f"🔔 Failed to retrieve SharePoint Site ID: SharePoint GET general error (Attempt {attempt}/{retries}): {e}")

        time.sleep(min(delay * (2 ** (attempt - 1)), 30))

    print(f"🔔 Failed to retrieve SharePoint Site ID. Max retries reached. Returning None.")
    return None

def async_sharepoint_file(method, filename):
    def _process_and_cleanup(filename=filename):
        try:
            if method == "upload":
                upload_file_to_sharepoint(filename)
            elif method == "delete":
                delete_file_from_sharepoint(filename)
            else:
                print(f"🔔 Unknown command for SharePoint: {method}")
        finally:
            del filename
            gc.collect()

    threading.Thread(target=_process_and_cleanup, daemon=True).start()
    
# SharePoint functions
def upload_file_to_sharepoint(filename, file_content=None):
    access_token = get_access_token()
    if not access_token:
        print("🔔 SharePoint token retrieval failed:", token_response)
        return

    SITE_ID = get_site_ID(access_token)
    if SITE_ID is None:
        print(f"🔔 Unable to upload file {filename} to SharePoint because Zenna was unable to retrieve the SharePoint site ID.")
        return
        
    upload_url = f"https://graph.microsoft.com/v1.0/sites/{SITE_ID}/drive/root:/{filename}:/content"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/octet-stream"
    }

    if file_content is None:
        # If no content passed, assume we need to read the file from disk
        if not Path(filename).exists():
            print(f"🔔 Local file {filename} not found for upload.")
            return
        
        with open(filename, "rb") as f:
            file_content = f.read()

    response = safe_sharepoint_call("PUT", upload_url, headers=headers, data=file_content)

    if response is None or not response.status_code in [200, 201]:
        print("🔔 Uploading file to SharePoint failed:", response.text)

def delete_file_from_sharepoint(filename):
    access_token = get_access_token()
    if not access_token:
        print("🔔 SharePoint token retrieval failed:", token_response)
        return

    SITE_ID = get_site_ID(access_token)
    if SITE_ID is None:
        print(f"🔔 Unable to delete file {filename} from SharePoint because Zenna was unable to retrieve the SharePoint site ID.")
        return
        
    delete_url = f"https://graph.microsoft.com/v1.0/sites/{SITE_ID}/drive/root:/{filename}"

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    response = safe_sharepoint_call("DELETE", delete_url, headers=headers)

    if response is None or response.status_code != 204:
        print(f"🔔 Deleting file from SharePoint failed: {response.status_code if response else 'No response'}")
