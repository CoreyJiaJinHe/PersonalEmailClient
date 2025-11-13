import email
import imaplib
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from typing import List, Tuple
from bs4 import BeautifulSoup
from datetime import datetime, timezone

from .storage import insert_message, get_highest_uid

BATCH_SIZE = 50


def sanitize_html(raw_html: str) -> Tuple[str, List[str]]:
    """Remove script/style tags and block image loading, extracting src values separately."""
    soup = BeautifulSoup(raw_html, "html.parser")
    # Remove scripts and styles
    for tag in soup(["script", "style"]):
        tag.decompose()
    image_srcs: List[str] = []
    for img in soup.find_all("img"):
        if img.has_attr("src"):
            image_srcs.append(img["src"])
        # Replace img with placeholder span
        placeholder = soup.new_tag("span")
        placeholder.string = "[Image blocked]"
        img.replace_with(placeholder)
    cleaned = str(soup)
    return cleaned, image_srcs


def extract_plain_and_html(msg: email.message.Message) -> Tuple[str, str]:
    plain_parts: List[str] = []
    html_parts: List[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                try:
                    plain_parts.append(part.get_content())
                except Exception:
                    pass
            elif ctype == "text/html":
                try:
                    html_parts.append(part.get_content())
                except Exception:
                    pass
    else:
        ctype = msg.get_content_type()
        if ctype == "text/plain":
            plain_parts.append(msg.get_content())
        elif ctype == "text/html":
            html_parts.append(msg.get_content())
    body_plain = "\n".join(plain_parts).strip()
    body_html = "\n".join(html_parts).strip()
    return body_plain, body_html


def sync_imap(account_id: int, host: str, port: int, username: str, password: str):
    """Fetch new messages (subject, from, to, date, bodies) in batches and store locally."""
    highest_uid = get_highest_uid(account_id)
    M = imaplib.IMAP4_SSL(host, port)
    M.login(username, password)
    M.select("INBOX")
    # Search for messages with UID greater than highest_uid
    search_criteria = f"UID {highest_uid + 1}:*" if highest_uid else "ALL"
    typ, data = M.uid("SEARCH", None, search_criteria)
    if typ != "OK":
        M.logout()
        return 0
    uids = [int(u) for u in data[0].split() if u]
    new_count = 0
    for uid in uids[:BATCH_SIZE]:
        typ, msg_data = M.uid("FETCH", str(uid), "(RFC822)")
        if typ != "OK" or not msg_data or not msg_data[0]:
            continue
        raw = msg_data[0][1]
        msg = BytesParser(policy=policy.default).parsebytes(raw)
        subject = msg.get("Subject", "")
        from_addr = msg.get("From", "")
        to_addrs = msg.get("To", "")
        date_hdr = msg.get("Date")
        if date_hdr:
            try:
                dt = parsedate_to_datetime(date_hdr)
                # Ensure timezone-aware and convert to UTC
                if dt.tzinfo is not None:
                    dt = dt.astimezone(timezone.utc)
                else:
                    dt = dt.replace(tzinfo=timezone.utc)
                date_received = dt
            except Exception:
                date_received = datetime.utcnow().replace(tzinfo=timezone.utc)
        else:
            date_received = datetime.utcnow().replace(tzinfo=timezone.utc)
        body_plain, body_html_raw = extract_plain_and_html(msg)
        sanitized_html, image_srcs = sanitize_html(body_html_raw) if body_html_raw else ("", [])
        insert_message(
            account_id,
            uid,
            subject,
            from_addr,
            to_addrs,
            date_received,
            body_plain,
            body_html_raw,
            sanitized_html,
            image_srcs,
        )
        new_count += 1
    M.logout()
    return new_count


__all__ = ["sync_imap", "sanitize_html"]