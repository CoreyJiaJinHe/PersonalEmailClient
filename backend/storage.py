import sqlite3
from pathlib import Path
from typing import Optional, Iterable, Tuple, List
from datetime import datetime
import os

# Determine a stable root-relative database path so Electron's working directory
# does not cause separate copies. Allow override via EMAIL_DB_PATH.
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("EMAIL_DB_PATH", str(ROOT / "data" / "email.db")))


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()
    # Accounts table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_address TEXT NOT NULL,
            imap_host TEXT NOT NULL,
            imap_port INTEGER NOT NULL,
            username TEXT NOT NULL,
            encrypted_password TEXT,
            allow_remote_images INTEGER NOT NULL DEFAULT 0
        );
        """
    )

    # Messages table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            uid INTEGER NOT NULL,
            external_id TEXT,
            subject TEXT,
            from_addr TEXT,
            to_addrs TEXT,
            date_received TEXT,
            body_plain TEXT,
            body_html_raw TEXT,
            body_html_sanitized TEXT,
            hidden INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT,
            UNIQUE(account_id, uid),
            FOREIGN KEY(account_id) REFERENCES accounts(id)
        );
        """
    )

    # Image sources extracted from HTML (blocked initially)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS image_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            src TEXT NOT NULL,
            FOREIGN KEY(message_id) REFERENCES messages(id)
        );
        """
    )

    # Audit log for delete/restore actions
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            note TEXT,
            FOREIGN KEY(message_id) REFERENCES messages(id)
        );
        """
    )

    # OAuth tokens table for external providers (e.g., Gmail)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            expiry TEXT,
            scope TEXT,
            UNIQUE(account_id, provider),
            FOREIGN KEY(account_id) REFERENCES accounts(id)
        );
        """
    )

    # Full text search virtual table for subject and from address only
    cur.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS message_search USING fts5(
            subject, from_addr, content='messages', content_rowid='id'
        );
        """
    )

    # Triggers to keep message_search in sync (external content table)
    cur.execute(
        """
        CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
            INSERT INTO message_search(rowid, subject, from_addr)
            VALUES (new.id, new.subject, new.from_addr);
        END;"""
    )
    cur.execute(
        """
        CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
            UPDATE message_search SET subject = new.subject, from_addr = new.from_addr
            WHERE rowid = new.id;
        END;"""
    )
    cur.execute(
        """
        CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
            DELETE FROM message_search WHERE rowid = old.id;
        END;"""
    )

    conn.commit()
    conn.close()
    # Attempt migration: add encrypted_password if missing (older deployments)
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(accounts)")
        cols = [r[1] for r in cur.fetchall()]
        if "encrypted_password" not in cols:
            cur.execute("ALTER TABLE accounts ADD COLUMN encrypted_password TEXT")
            conn.commit()
        # Add external_id column + unique index for Gmail dedup if missing
        cur.execute("PRAGMA table_info(messages)")
        mcols = [r[1] for r in cur.fetchall()]
        if "external_id" not in mcols:
            cur.execute("ALTER TABLE messages ADD COLUMN external_id TEXT")
            conn.commit()
            # Create unique index avoiding NULL external_ids (SQLite treats NULLs as distinct so index still works)
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_account_external ON messages(account_id, external_id)")
            conn.commit()
        conn.close()
    except Exception:
        pass


def insert_message(
    account_id: int,
    uid: int,
    subject: str,
    from_addr: str,
    to_addrs: str,
    date_received: datetime,
    body_plain: str,
    body_html_raw: str,
    body_html_sanitized: str,
    image_srcs: List[str],
    external_id: Optional[str] = None,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO messages(
            account_id, uid, external_id, subject, from_addr, to_addrs, date_received,
            body_plain, body_html_raw, body_html_sanitized
        ) VALUES(?,?,?,?,?,?,?,?,?,?);
        """,
        (
            account_id,
            uid,
            external_id,
            subject,
            from_addr,
            to_addrs,
            date_received.isoformat(),
            body_plain,
            body_html_raw,
            body_html_sanitized,
        ),
    )
    message_id = cur.lastrowid
    if message_id:
        for src in image_srcs:
            cur.execute(
                "INSERT INTO image_sources(message_id, src) VALUES(?, ?);",
                (message_id, src),
            )
    conn.commit()
    conn.close()


def list_messages(search: Optional[str], page: int, page_size: int, include_hidden: bool = False):
    """Return paginated messages.
    Search behavior: substring match across subject OR from_addr OR body_plain.
    Each space-separated token must be found in at least one of these fields (AND semantics across tokens).
    """
    offset = (page - 1) * page_size
    conn = get_connection()
    cur = conn.cursor()
    hidden_clause = "" if include_hidden else "AND hidden=0"
    if search and search.strip():
        tokens = [t.strip() for t in search.split() if t.strip()]
        like_clauses = ["(subject LIKE ? OR from_addr LIKE ? OR body_plain LIKE ?)" for _ in tokens]
        where_search = " AND ".join(like_clauses)
        params: List[str] = []
        for tok in tokens:
            pattern = f"%{tok}%"
            params.extend([pattern, pattern, pattern])
        params.extend([page_size, offset])
        cur.execute(
            f"""
            SELECT id, subject, from_addr, date_received, hidden, body_plain
            FROM messages
            WHERE 1=1 {hidden_clause} AND {where_search}
            ORDER BY datetime(date_received) DESC
            LIMIT ? OFFSET ?
            """,
            params,
        )
    else:
        cur.execute(
            f"""
            SELECT id, subject, from_addr, date_received, hidden, body_plain
            FROM messages
            WHERE 1=1 {hidden_clause}
            ORDER BY datetime(date_received) DESC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_message(message_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM messages WHERE id=?",
        (message_id,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_message(message_id: int):
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE messages SET hidden=1, deleted_at=? WHERE id=?",
        (now, message_id),
    )
    cur.execute(
        "INSERT INTO audit_log(message_id, action, occurred_at) VALUES(?, 'delete', ?);",
        (message_id, now),
    )
    conn.commit()
    conn.close()


def restore_message(message_id: int):
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE messages SET hidden=0, deleted_at=NULL WHERE id=?",
        (message_id,),
    )
    cur.execute(
        "INSERT INTO audit_log(message_id, action, occurred_at) VALUES(?, 'restore', ?);",
        (message_id, now),
    )
    conn.commit()
    conn.close()


def store_oauth_tokens(account_id: int, provider: str, access_token: str, refresh_token: Optional[str], expiry_iso: Optional[str], scope: Optional[str]):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO oauth_tokens(account_id, provider, access_token, refresh_token, expiry, scope)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(account_id, provider) DO UPDATE SET
          access_token=excluded.access_token,
          refresh_token=excluded.refresh_token,
          expiry=excluded.expiry,
          scope=excluded.scope
        """,
        (account_id, provider, access_token, refresh_token, expiry_iso, scope),
    )
    conn.commit()
    conn.close()


def get_oauth_tokens(account_id: int, provider: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT access_token, refresh_token, expiry, scope FROM oauth_tokens WHERE account_id=? AND provider=?",
        (account_id, provider),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "access_token": row["access_token"],
        "refresh_token": row["refresh_token"],
        "expiry": row["expiry"],
        "scope": row["scope"],
    }


def list_trash(page: int, page_size: int):
    offset = (page - 1) * page_size
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, subject, from_addr, date_received, hidden, body_plain
        FROM messages
        WHERE hidden=1
        ORDER BY datetime(date_received) DESC
        LIMIT ? OFFSET ?
        """,
        (page_size, offset),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_highest_uid(account_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT MAX(uid) AS max_uid FROM messages WHERE account_id=?",
        (account_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row["max_uid"] if row and row["max_uid"] is not None else 0


def ensure_account(email_address: str = "test@example.com", imap_host: str = "", imap_port: int = 993, username: str = "test") -> int:
    """Ensure a default account exists and return its id."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM accounts LIMIT 1")
    row = cur.fetchone()
    if row:
        conn.close()
        return row["id"]
    cur.execute(
        "INSERT INTO accounts(email_address, imap_host, imap_port, username, allow_remote_images) VALUES(?,?,?,?,0)",
        (email_address, imap_host, imap_port, username),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def add_account(email_address: str, imap_host: str, imap_port: int, username: str, encrypted_password: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO accounts(email_address, imap_host, imap_port, username, encrypted_password, allow_remote_images)
        VALUES(?,?,?,?,?,0)
        """,
        (email_address, imap_host, imap_port, username, encrypted_password),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def get_accounts() -> List[dict]:
    conn = get_connection()
    cur = conn.cursor()
    # Include flags indicating stored password and gmail oauth presence for UI purposes.
    cur.execute(
        """
        SELECT a.id, a.email_address, a.imap_host, a.imap_port, a.username,
               CASE WHEN a.encrypted_password IS NOT NULL AND a.encrypted_password <> '' THEN 1 ELSE 0 END AS has_password,
               CASE WHEN EXISTS (SELECT 1 FROM oauth_tokens ot WHERE ot.account_id = a.id AND ot.provider='gmail') THEN 1 ELSE 0 END AS has_gmail
        FROM accounts a
        ORDER BY a.id ASC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_account_credentials(account_id: int) -> Optional[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT email_address, imap_host, imap_port, username, encrypted_password FROM accounts WHERE id=?",
        (account_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "email_address": row["email_address"],
        "imap_host": row["imap_host"],
        "imap_port": row["imap_port"],
        "username": row["username"],
        "encrypted_password": row["encrypted_password"],
    }


def delete_account(account_id: int) -> dict:
    """Remove an account and all related data (messages, image sources, oauth tokens).
    Returns counts of deleted rows for transparency."""
    conn = get_connection()
    cur = conn.cursor()
    # Count related rows first
    cur.execute("SELECT COUNT(*) AS c FROM messages WHERE account_id=?", (account_id,))
    msg_count = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM oauth_tokens WHERE account_id=?", (account_id,))
    oauth_count = cur.fetchone()["c"]
    # Delete image sources via messages ids
    cur.execute("SELECT id FROM messages WHERE account_id=?", (account_id,))
    msg_ids = [r["id"] for r in cur.fetchall()]
    img_count = 0
    if msg_ids:
        placeholders = ",".join(["?"] * len(msg_ids))
        cur.execute(f"SELECT COUNT(*) AS c FROM image_sources WHERE message_id IN ({placeholders})", msg_ids)
        img_count = cur.fetchone()["c"]
        cur.execute(f"DELETE FROM image_sources WHERE message_id IN ({placeholders})", msg_ids)
        cur.execute(f"DELETE FROM audit_log WHERE message_id IN ({placeholders})", msg_ids)
    # Delete messages, oauth tokens, account
    cur.execute("DELETE FROM messages WHERE account_id=?", (account_id,))
    cur.execute("DELETE FROM oauth_tokens WHERE account_id=?", (account_id,))
    cur.execute("DELETE FROM accounts WHERE id=?", (account_id,))
    conn.commit()
    conn.close()
    return {
        "messages_deleted": msg_count,
        "images_deleted": img_count,
        "oauth_tokens_deleted": oauth_count,
        "account_deleted": 1 if msg_count or oauth_count or True else 0,
    }


__all__ = [
    "init_db",
    "insert_message",
    "list_messages",
    "get_message",
    "delete_message",
    "restore_message",
    "list_trash",
    "get_highest_uid",
    "ensure_account",
    "store_oauth_tokens",
    "get_oauth_tokens",
    "add_account",
    "get_accounts",
    "get_account_credentials",
    "delete_account",
]