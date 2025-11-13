# Personal Email Client (MVP)

Minimal desktop backend (Python FastAPI) for a personal email viewer. Fetches messages manually from a single IMAP inbox, stores locally in SQLite, supports keyword search (subject & sender only), local delete (hide) and restore, plus scaffold for future remote image opt-in.

## Features
- Manual fetch: `/sync` endpoint pulls up to 50 new messages.
- Storage: Subject, sender, recipients, received date, plain text body, raw HTML, sanitized HTML.
- Sanitization: Removes scripts, styles; blocks images (stores sources separately for future opt-in).
- Search: Keyword match over subject and sender using a SQLite virtual table.
- Local delete & restore: Soft hide with audit log; trash listing.
- Token auth: Header `X-Auth-Token` must match environment `BACKEND_TOKEN`.

## Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Server status |
| POST | /sync | Fetch new messages (query params: host, port, username, password, account_id=1) |
| GET | /messages | Paginated messages (`page`, `page_size`, optional `search`) |
| GET | /messages/{id} | Message detail (hidden messages not returned) |
| POST | /messages/{id}/delete | Hide a message (soft delete) |
| POST | /messages/{id}/restore | Restore a hidden message |
| GET | /trash | Paginated hidden messages |
| GET | /account/settings | Returns remote image flag (always false) |
| PUT | /account/settings | Scaffold to update remote image flag |

## Quick Start
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

UI Usage:
- Enter IMAP host, username, and password (app password recommended).
- Click Sync to fetch up to 50 new messages.
- Messages list shows subject | sender | date.
- Search box filters by subject or sender (simple space-separated AND logic).
- Pagination controls (Prev/Next) navigate pages of 50 messages; Next disabled when the last page is reached.
- Delete hides a message; use Show Trash checkbox to view hidden messages and Restore.
- HTML images are blocked and replaced with placeholders.


### Fetch Mail Example
```cmd
REM Replace 8137 with actual port if different
curl -X POST "http://127.0.0.1:8137/sync?host=imap.example.com&port=993&username=user@example.com&password=APP_PASS" ^
  -H "X-Auth-Token: dev-token"
```

### List Messages
### Dummy Data (No IMAP Needed)
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
- Date parsing is simplified; falls back to current UTC if header parse fails.
- Future enhancements: body search, multi-account, remote image toggle, WebSocket events.

## License
User-specific project (no license specified).
