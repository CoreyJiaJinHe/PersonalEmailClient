from fastapi import FastAPI, HTTPException, Header, Query, Body
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime
import os

from .storage import (
    init_db,
    list_messages,
    get_message,
    delete_message,
    restore_message,
    list_trash,
    ensure_account,
    insert_message,
    get_highest_uid,
    get_oauth_tokens,
    add_account,
    get_accounts,
    get_account_credentials,
    delete_account,
)
from .gmail_oauth import generate_auth_url, exchange_code, gmail_sync
from .fetch import sync_imap, sanitize_html
from .crypto import encrypt_secret, decrypt_secret
from datetime import datetime
import random

APP_TOKEN = os.environ.get("BACKEND_TOKEN", "dev-token")

app = FastAPI(title="Personal Email Client Backend")


@app.on_event("startup")
def _startup():
    init_db()


def _require_token(x_auth_token: str = Header(...)):
    if x_auth_token != APP_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.post("/sync")
def sync(
    account_id: int = Query(None, description="Existing account id if using stored credentials"),
    host: Optional[str] = Query(None),
    port: int = Query(993),
    username: Optional[str] = Query(None),
    password: Optional[str] = Query(None),
    x_auth_token: str = Header(...),
):
    _require_token(x_auth_token)
    # If account_id provided, pull stored encrypted password
    if account_id is not None:
        acct = get_account_credentials(account_id)
        if not acct:
            raise HTTPException(status_code=404, detail="Account not found")
        if not acct.get("encrypted_password"):
            raise HTTPException(status_code=400, detail="Account has no stored password")
        try:
            dec_pw = decrypt_secret(acct["encrypted_password"])
        except ValueError:
            raise HTTPException(status_code=500, detail="Failed to decrypt stored password")
        new_count = sync_imap(account_id, acct["imap_host"], acct["imap_port"], acct["username"], dec_pw)
        return {"fetched": new_count, "account_id": account_id}
    # Otherwise require direct credentials
    if not (host and username and password):
        raise HTTPException(status_code=400, detail="host, username, password required if account_id not provided")
    # Use ensure_account for a one-off default (or create ephemeral)
    account_id = ensure_account(email_address=username, imap_host=host, imap_port=port, username=username)
    new_count = sync_imap(account_id, host, port, username, password)
    return {"fetched": new_count, "account_id": account_id}


@app.get("/accounts")
def list_accounts(x_auth_token: str = Header(...)):
    _require_token(x_auth_token)
    return {"accounts": get_accounts()}


@app.post("/accounts")
def create_account(
    email_address: str = Body(...),
    imap_host: str = Body(...),
    imap_port: int = Body(993),
    username: str = Body(...),
    password: str = Body(...),
    x_auth_token: str = Header(...),
):
    _require_token(x_auth_token)
    enc = encrypt_secret(password)
    account_id = add_account(email_address, imap_host, imap_port, username, enc)
    return {"status": "ok", "account_id": account_id}


# Gmail OAuth flow
@app.get("/gmail/auth_url")
def gmail_auth_url(x_auth_token: str = Header(...)):
    _require_token(x_auth_token)
    return {"url": generate_auth_url()}


@app.get("/gmail/callback")
def gmail_callback(code: str, state: str = Query("state123")):
    # Google redirects to this endpoint after user consents.
    result = exchange_code(code, state)
    return result


@app.post("/gmail/sync")
def gmail_sync_endpoint(account_id: int = Query(...), x_auth_token: str = Header(...)):
    _require_token(x_auth_token)
    # Require explicit account_id created via OAuth callback
    acct = get_account_credentials(account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    result = gmail_sync(account_id)
    return {"account_id": account_id, **result}


@app.post("/accounts/{account_id}/sync")
def account_sync(account_id: int, x_auth_token: str = Header(...)):
    _require_token(x_auth_token)
    acct = get_account_credentials(account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    # Decide provider: if oauth_tokens exists for gmail provider, use Gmail API; else IMAP.
    oauth = get_oauth_tokens(account_id, "gmail")
    if oauth:
        result = gmail_sync(account_id)
        return {"mode": "gmail", **result, "account_id": account_id}
    # IMAP path requires encrypted_password
    if not acct.get("encrypted_password"):
        raise HTTPException(status_code=400, detail="No credentials stored for IMAP sync")
    try:
        dec_pw = decrypt_secret(acct["encrypted_password"])
    except ValueError:
        raise HTTPException(status_code=500, detail="Failed to decrypt password")
    new_count = sync_imap(account_id, acct["imap_host"], acct["imap_port"], acct["username"], dec_pw)
    return {"mode": "imap", "fetched": new_count, "account_id": account_id}


@app.put("/accounts/{account_id}/password")
def rotate_password(account_id: int, password: str = Body(...), x_auth_token: str = Header(...)):
    _require_token(x_auth_token)
    acct = get_account_credentials(account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    enc = encrypt_secret(password)
    conn = None
    try:
        from .storage import get_connection
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE accounts SET encrypted_password=? WHERE id=?", (enc, account_id))
        conn.commit()
    finally:
        if conn:
            conn.close()
    return {"status": "updated", "account_id": account_id}


@app.delete("/accounts/{account_id}")
def remove_account(account_id: int, x_auth_token: str = Header(...)):
    _require_token(x_auth_token)
    acct = get_account_credentials(account_id)
    if not acct:
        raise HTTPException(status_code=404, detail="Account not found")
    stats = delete_account(account_id)
    return {"status": "deleted", "account_id": account_id, **stats}


@app.get("/messages")
def messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    x_auth_token: str = Header(...),
):
    _require_token(x_auth_token)
    rows = list_messages(search, page, page_size)
    return {"page": page, "page_size": page_size, "messages": rows}


@app.get("/messages/{message_id}")
def message_detail(message_id: int, x_auth_token: str = Header(...)):
    _require_token(x_auth_token)
    msg = get_message(message_id)
    if not msg or msg.get("hidden"):
        raise HTTPException(status_code=404, detail="Message not found")
    return msg


@app.post("/messages/{message_id}/delete")
def message_delete(message_id: int, x_auth_token: str = Header(...)):
    _require_token(x_auth_token)
    msg = get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    delete_message(message_id)
    return {"status": "deleted", "id": message_id}


@app.post("/messages/{message_id}/restore")
def message_restore(message_id: int, x_auth_token: str = Header(...)):
    _require_token(x_auth_token)
    msg = get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    restore_message(message_id)
    return {"status": "restored", "id": message_id}


@app.get("/trash")
def trash(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), x_auth_token: str = Header(...)):
    _require_token(x_auth_token)
    rows = list_trash(page, page_size)
    return {"page": page, "page_size": page_size, "messages": rows}


@app.get("/account/settings")
def account_settings(x_auth_token: str = Header(...)):
    _require_token(x_auth_token)
    # Placeholder: would query accounts table; single account fixed for MVP
    return {"allow_remote_images": False}


@app.put("/account/settings")
def update_account_settings(allow_remote_images: bool, x_auth_token: str = Header(...)):
    _require_token(x_auth_token)
    # Scaffold only; no DB update yet
    return {"allow_remote_images": allow_remote_images, "status": "scaffold"}


@app.post("/dummy/insert")
def dummy_insert(
    subject: str = Query("Sample Subject"),
    from_addr: str = Query("sender@example.com"),
    to_addrs: str = Query("recipient@example.com"),
    body_plain: str = Query("Plain text body"),
    body_html_raw: str = Query("<p>HTML body</p>"),
    x_auth_token: str = Header(...),
):
    _require_token(x_auth_token)
    account_id = ensure_account()
    next_uid = get_highest_uid(account_id) + 1
    sanitized_html, image_srcs = sanitize_html(body_html_raw) if body_html_raw else ("", [])
    insert_message(
        account_id,
        next_uid,
        subject,
        from_addr,
        to_addrs,
        datetime.utcnow(),
        body_plain,
        body_html_raw,
        sanitized_html,
        image_srcs,
    )
    return {"status": "ok", "uid": next_uid}


@app.post("/dummy/seed")
def dummy_seed(
    count: int = Query(10, ge=1, le=200),
    x_auth_token: str = Header(...),
):
    _require_token(x_auth_token)
    account_id = ensure_account()
    start_uid = get_highest_uid(account_id)
    created = 0
    for i in range(count):
        uid = start_uid + i + 1
        subject = f"Test Message {uid}"
        from_addr = f"user{uid}@example.com"
        to_addrs = "recipient@example.com"
        body_plain = f"This is plain body for message {uid}."
        body_html_raw = f"<p>This is <strong>HTML</strong> body for message {uid}.</p>"
        sanitized_html, image_srcs = sanitize_html(body_html_raw)
        insert_message(
            account_id,
            uid,
            subject,
            from_addr,
            to_addrs,
            datetime.utcnow(),
            body_plain,
            body_html_raw,
            sanitized_html,
            image_srcs,
        )
        created += 1
    return {"status": "ok", "created": created}


__all__ = ["app"]