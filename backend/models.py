from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class Account:
	id: Optional[int]
	email_address: str
	imap_host: str
	imap_port: int
	username: str
	allow_remote_images: bool = False


@dataclass
class Message:
	id: Optional[int]
	account_id: int
	uid: int  # IMAP UID
	subject: str
	from_addr: str
	to_addrs: str  # Comma separated
	date_received: datetime
	body_plain: str
	body_html_raw: Optional[str]
	body_html_sanitized: Optional[str]
	hidden: bool = False
	deleted_at: Optional[datetime] = None


@dataclass
class ImageSource:
	id: Optional[int]
	message_id: int
	src: str


@dataclass
class AuditLog:
	id: Optional[int]
	message_id: int
	action: str  # delete or restore
	occurred_at: datetime
	note: Optional[str] = None


__all__ = [
	"Account",
	"Message",
	"ImageSource",
	"AuditLog",
]
