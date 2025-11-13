"""Simple script to exercise the backend without curl.

Run after starting the server:
  set BACKEND_TOKEN=my-secret-token
  python backend\main.py
In a second terminal (same venv):
  python backend\sample_test_calls.py
"""

import os
import requests

BASE = "http://127.0.0.1:8137"
TOKEN = os.environ.get("BACKEND_TOKEN", "dev-token")
HDRS = {"X-Auth-Token": TOKEN}


def show(label, r):
    print(f"\n=== {label} ({r.status_code}) ===")
    try:
        print(r.json())
    except Exception:
        print(r.text)


def main():
    # 1. Health
    show("health", requests.get(f"{BASE}/health", headers=HDRS))

    # 2. (Optional) Sync - requires real IMAP credentials. Uncomment and fill values.
    # sync_params = {
    #     "host": "imap.example.com",
    #     "port": 993,
    #     "username": "user@example.com",
    #     "password": "APP_PASSWORD",
    # }
    # show("sync", requests.post(f"{BASE}/sync", params=sync_params, headers=HDRS))

    # 3. List messages page 1
    show("messages page 1", requests.get(f"{BASE}/messages", headers=HDRS))

    # 4. Search (subject/sender) example
    show("search 'invoice'", requests.get(f"{BASE}/messages", params={"search": "invoice"}, headers=HDRS))

    # 5. Trash (should be empty initially)
    show("trash", requests.get(f"{BASE}/trash", headers=HDRS))

    # 6. If there is at least one message, delete and restore it.
    msgs = requests.get(f"{BASE}/messages", headers=HDRS).json().get("messages", [])
    if msgs:
        mid = msgs[0]["id"]
        show("delete first", requests.post(f"{BASE}/messages/{mid}/delete", headers=HDRS))
        show("trash after delete", requests.get(f"{BASE}/trash", headers=HDRS))
        show("restore first", requests.post(f"{BASE}/messages/{mid}/restore", headers=HDRS))
        show("messages after restore", requests.get(f"{BASE}/messages", headers=HDRS))
    else:
        print("No messages available to delete/restore. Perform /sync once you have credentials.")


if __name__ == "__main__":
    main()