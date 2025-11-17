# Personal Email Client

Local desktop email viewer (FastAPI backend + Electron frontend) with multi-account support, Gmail OAuth, message deduplication, soft delete/restore, search, and local SQLite storage. Manual IMAP password login is currently disabled while focusing on secure OAuth flows.

## Features
- Gmail OAuth multi-account: Add multiple Gmail inboxes; each stored as its own account.
- Message deduplication: Gmail messages keyed by `external_id` (Gmail message ID) ensuring no duplicates.
- Per-account sync: `/accounts/{id}/sync` chooses Gmail API vs IMAP automatically (IMAP path currently disabled in UI).
- Storage: Subject, sender, recipients, received date, plain/plain+HTML bodies (sanitized), image sources harvested.
- Sanitization: Strips scripts/styles; blocks remote images (sources retained for future opt-in).
- Search: Substring AND across tokens over subject/from/body_plain.
- Soft delete & restore: Hidden messages go to Trash; restore individually.
- Account removal: Delete an account and all its messages and tokens.
- Token auth: Header `X-Auth-Token` must match `BACKEND_TOKEN`.

## Endpoints (Core)
| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Server status |
| GET | /messages | Paginated messages (`page`, `page_size`, `search`) |
| GET | /messages/{id} | Message detail (hidden excluded) |
| POST | /messages/{id}/delete | Soft delete (hide) |
| POST | /messages/{id}/restore | Restore hidden |
| GET | /trash | Paginated hidden messages |
| POST | /dummy/seed | Seed test messages |
| POST | /dummy/insert | Insert one test message |

## Endpoints (Accounts & Gmail)
| Method | Path | Description |
|--------|------|-------------|
| GET | /accounts | List accounts (flags: `has_gmail`, `has_password`) |
| POST | /accounts | Create IMAP account (legacy; UI disabled) |
| PUT | /accounts/{id}/password | Rotate stored IMAP password (legacy) |
| DELETE | /accounts/{id} | Remove account + all related data |
| POST | /accounts/{id}/sync | Sync (Gmail API if tokens exist; IMAP otherwise) |
| GET | /gmail/auth_url | Generate Gmail OAuth consent URL |
| GET | /gmail/callback | OAuth redirect target; stores tokens & creates account |
| POST | /gmail/sync | Explicit Gmail sync (prefer /accounts/{id}/sync) |

Legacy: `POST /sync` exists for direct IMAP credentials but is not exposed in the UI.

## Quick Start (Backend + Electron)
```cmd
REM (Optional) Create virtual environment
python -m venv .venv
call .venv\Scripts\activate

pip install -r requirements.txt
set BACKEND_TOKEN=dev-token
python backend\main.py
```

### Electron Frontend

Install Node dependencies (requires Node.js):
```cmd
cd frontend
npm install
npm start
```
This will launch Electron, start the Python backend automatically (using the same `BACKEND_TOKEN` if set in the environment), and open the UI.

### Dynamic Port Selection
The backend tries to bind to the port specified by `BACKEND_PORT` (default 8137). If that port is occupied, it scans the next 20 ports and picks the first free one, printing `Listening on 127.0.0.1:XXXX`. Electron parses this line and routes API calls to the chosen port automatically. If you are calling the API manually (e.g. with `curl`), verify which port was selected in the Electron console output.

UI Notes:
- Manual IMAP login form hidden (temporary). Use "Add Gmail Account" to onboard.
- Accounts panel: each account shows tags `[Gmail]` / `[IMAP]`, plus Sync/Rotate/Remove actions (Rotate only for IMAP accounts).
- Delete/Restore toolbar sticks to top; Trash toggle reveals hidden messages.
- Search supports multiple tokens (all must match somewhere in subject/from/body).


### Gmail OAuth Setup

1. Create a Google Cloud project → Enable "Gmail API".
2. Configure OAuth consent screen (External for regular Gmail users). Add scope: `https://www.googleapis.com/auth/gmail.readonly`.
3. Create OAuth Client ID (Web Application). Authorized redirect URI must EXACTLY match your backend: `http://127.0.0.1:8137/gmail/callback` (adjust port if needed).
4. Copy Client ID and Client Secret.
5. Generate a stable Fernet key for encryption (Windows cmd):
  ```cmd
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
6. Create `.env` in project root:
  ```env
  BACKEND_TOKEN=dev-token
  BACKEND_PORT=8137
  GMAIL_CLIENT_ID=your_client_id.apps.googleusercontent.com
  GMAIL_CLIENT_SECRET=your_client_secret
  GMAIL_REDIRECT_URI=http://127.0.0.1:8137/gmail/callback
  EMAIL_ENCRYPTION_KEY=base64_fernet_key_here
  ```
7. Start Electron (`npm start` inside `frontend/`). Backend reads `.env` and launches FastAPI.
8. Click "Add Gmail Account" → consent → account appears → click Sync.

If port 8137 is busy, change `BACKEND_PORT` AND update both the redirect URI here and in Google Cloud.

### Manual IMAP (Disabled)
Legacy fields/flow remain in the API (`/sync`, `/accounts` creation) but the UI hides them while focusing on secure OAuth. Re-enable later by unhiding the section in `frontend/index.html` and restoring the handler in `renderer.js`.

### Fetch Mail Example (Legacy IMAP)
```cmd
REM Replace 8137 with actual port if different
curl -X POST "http://127.0.0.1:8137/sync?host=imap.example.com&port=993&username=user@example.com&password=APP_PASS" ^
  -H "X-Auth-Token: dev-token"
```

### List Messages
### Dummy Data (Testing Without IMAP/OAuth)
Seed test messages:
```cmd
REM Replace 8137 with actual port if different
curl -X POST "http://127.0.0.1:8137/dummy/seed?count=25" -H "X-Auth-Token: dev-token"
```
Insert one message:
```cmd
REM Replace 8137 with actual port if different
curl -X POST "http://127.0.0.1:8137/dummy/insert?subject=Hello&from_addr=a@b.com" -H "X-Auth-Token: dev-token"
```
```cmd
REM Replace 8137 with actual port if different
curl "http://127.0.0.1:8137/messages?page=1&page_size=50" -H "X-Auth-Token: dev-token"
```

### Search by Subject/Sender
```cmd
REM Replace 8137 with actual port if different
curl "http://127.0.0.1:8137/messages?search=invoice" -H "X-Auth-Token: dev-token"
```

### Delete / Restore
```cmd
REM Replace 8137 with actual port if different
curl -X POST "http://127.0.0.1:8137/messages/10/delete" -H "X-Auth-Token: dev-token"
curl -X POST "http://127.0.0.1:8137/messages/10/restore" -H "X-Auth-Token: dev-token"
```

## Notes
- Gmail message date currently uses fetch timestamp (header parse improvement pending).
- Dedup uses `external_id` unique index (Gmail message ID); skipped count approximated.
- Remote images blocked by default; stored in `image_sources` for future opt-in.
- Manual IMAP disabled; rotate password & direct `/sync` remain for potential reactivation.
- Account removal deletes messages, image sources, audit logs, and OAuth tokens.

## License
User-specific project (no license specified).
