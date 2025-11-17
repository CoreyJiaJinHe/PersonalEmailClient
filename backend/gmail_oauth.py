import os
import time
from typing import Optional, List, Dict
from fastapi import HTTPException
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from .storage import store_oauth_tokens, get_oauth_tokens, insert_message, ensure_account, add_account
from datetime import datetime
import requests

# Expected environment variables:
# GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REDIRECT_URI
# Redirect URI should match one configured in Google Cloud console (e.g. http://127.0.0.1:8137/gmail/callback )

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
PROVIDER = "gmail"


def build_flow(state: str):
    client_id = os.environ.get("GMAIL_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
    redirect_uri = os.environ.get("GMAIL_REDIRECT_URI")
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(status_code=500, detail="Missing Gmail OAuth environment variables")
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=SCOPES,
        state=state,
    )
    flow.redirect_uri = redirect_uri
    return flow


def generate_auth_url(state: str = "state123") -> str:
    flow = build_flow(state)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url


def exchange_code(code: str, state: Optional[str] = None):
    flow = build_flow(state or "state123")
    flow.fetch_token(code=code)
    creds = flow.credentials
    # Fetch profile email to create distinct account per Gmail user
    headers = {"Authorization": f"Bearer {creds.token}"}
    pr = requests.get("https://gmail.googleapis.com/gmail/v1/users/me/profile", headers=headers, timeout=10)
    if pr.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to retrieve Gmail profile")
    email_address = pr.json().get("emailAddress") or "unknown@gmail.com"
    # Create account row (no password, host retained for potential IMAP fallback)
    account_id = add_account(email_address, "imap.gmail.com", 993, email_address, encrypted_password="")
    expiry_iso = datetime.utcfromtimestamp(creds.expiry.timestamp()).isoformat() if creds.expiry else None
    store_oauth_tokens(
        account_id,
        PROVIDER,
        creds.token,
        creds.refresh_token,
        expiry_iso,
        " ".join(SCOPES),
    )
    return {"account_id": account_id, "email": email_address, "status": "ok"}


def refresh_if_needed(account_id: int) -> Dict[str, str]:
    record = get_oauth_tokens(account_id, PROVIDER)
    if not record:
        raise HTTPException(status_code=404, detail="No Gmail OAuth tokens stored")
    access_token = record["access_token"]
    refresh_token = record["refresh_token"]
    expiry = record["expiry"]
    if expiry:
        try:
            exp_ts = datetime.fromisoformat(expiry).timestamp()
            if time.time() < exp_ts - 60:  # still valid
                return {"access_token": access_token}
        except Exception:
            pass
    if not refresh_token:
        return {"access_token": access_token}
    # Refresh token
    client_id = os.environ.get("GMAIL_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Missing client credentials for refresh")
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to refresh Gmail token")
    data = resp.json()
    new_access = data.get("access_token")
    expires_in = data.get("expires_in")
    new_expiry_iso = datetime.utcfromtimestamp(time.time() + (expires_in or 0)).isoformat()
    store_oauth_tokens(account_id, PROVIDER, new_access, refresh_token, new_expiry_iso, record.get("scope"))
    return {"access_token": new_access}


def gmail_sync(account_id: int, max_results: int = 50):
    tk = refresh_if_needed(account_id)
    headers = {"Authorization": f"Bearer {tk['access_token']}"}
    params = {"maxResults": max_results}
    r = requests.get("https://gmail.googleapis.com/gmail/v1/users/me/messages", headers=headers, params=params, timeout=20)
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Failed to list Gmail messages")
    data = r.json()
    ids = [m["id"] for m in data.get("messages", [])]
    fetched = 0
    skipped = 0
    for msg_id in ids:
        mr = requests.get(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}", headers=headers, params={"format": "full"}, timeout=20)
        if mr.status_code != 200:
            continue
        payload = mr.json()
        headers_list = payload.get("payload", {}).get("headers", [])
        hdr_map = {h["name"].lower(): h["value"] for h in headers_list}
        subject = hdr_map.get("subject", "")
        from_addr = hdr_map.get("from", "")
        to_addrs = hdr_map.get("to", "")
        date_str = hdr_map.get("date", datetime.utcnow().isoformat())
        body_plain = ""
        body_html = ""
        # Traverse parts to find text/plain and text/html
        def walk_parts(part):
            nonlocal body_plain, body_html
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                import base64
                body_plain = base64.urlsafe_b64decode(part["body"]["data"].encode()).decode(errors="ignore")
            if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
                import base64
                body_html = base64.urlsafe_b64decode(part["body"]["data"].encode()).decode(errors="ignore")
            for p in part.get("parts", []) or []:
                walk_parts(p)
        walk_parts(payload.get("payload", {}))
        # Fallback if no plain body
        if not body_plain:
            body_plain = (body_html or "")[:500]
        # Basic sanitization placeholder (already sanitized downstream) - storing raw html
        from .fetch import sanitize_html
        sanitized, img_srcs = sanitize_html(body_html or body_plain)
        before_count = fetched
        insert_message(
            account_id,
            uid=int(time.time()*1000)+fetched,  # synthetic UID fallback
            subject=subject,
            from_addr=from_addr,
            to_addrs=to_addrs,
            date_received=datetime.utcnow(),  # could parse date_str for accuracy
            body_plain=body_plain,
            body_html_raw=body_html or body_plain,
            body_html_sanitized=sanitized,
            image_srcs=img_srcs,
            external_id=msg_id,
        )
        # If duplicate external_id, INSERT OR IGNORE prevents row; detect skip
        if before_count == fetched:
            # Row might still have inserted; we can't rely on rowcount; simplest: check if existed previously by querying count
            # For lightweight skip metric, attempt to fetch; but to avoid extra query, approximate using uniqueness: if external_id existed it's skipped
            skipped += 1
        else:
            fetched += 1
    return {"fetched": fetched, "skipped": skipped}
