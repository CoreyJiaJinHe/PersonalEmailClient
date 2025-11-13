import os
import sys
from pathlib import Path
import uvicorn
import socket


def ensure_root_in_path():
    # Allow running this file from project root OR from inside the backend directory.
    this_file = Path(__file__).resolve()
    backend_dir = this_file.parent
    project_root = backend_dir.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def pick_free_port(preferred: int) -> int:
    # Try preferred first, then scan upward to preferred+20
    for p in [preferred] + list(range(preferred + 1, preferred + 21)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
            except OSError:
                continue
            return p
    raise RuntimeError("No free port found near preferred range")


def main():
    ensure_root_in_path()
    token = os.environ.get("BACKEND_TOKEN", "dev-token")
    preferred_port = int(os.environ.get("BACKEND_PORT", "8137"))
    port = pick_free_port(preferred_port)
    if port != preferred_port:
        print(f"Preferred port {preferred_port} busy; using {port}.")
    print("Starting backend server")
    print("Token set (override with BACKEND_TOKEN env var):", token)
    print(f"Listening on 127.0.0.1:{port}")
    print("Run sample tests: python backend\\sample_test_calls.py")
    uvicorn.run("backend.api:app", host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    main()