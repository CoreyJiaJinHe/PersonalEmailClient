from fastapi import FastAPI, HTTPException, Header, Query
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
)
from .fetch import sync_imap, sanitize_html
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
    account_id: int = Query(1, description="Account identifier (fixed to 1 for MVP)"),
    host: str = Query(...),
    port: int = Query(993),
    username: str = Query(...),
    password: str = Query(...),
    x_auth_token: str = Header(...),
):
    _require_token(x_auth_token)
    new_count = sync_imap(account_id, host, port, username, password)
    return {"fetched": new_count}


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