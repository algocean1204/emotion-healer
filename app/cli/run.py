"""서버를 띄우고, 뜨면 브라우저를 연다."""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def _open_when_ready(timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(URL, timeout=0.5).close()
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
            continue
        webbrowser.open(URL)
        return


def run() -> None:
    print(f"emotion healer\n{URL}\n")
    threading.Thread(target=_open_when_ready, daemon=True).start()
    uvicorn.run("app.main:app", host=HOST, port=PORT, log_level="warning")
