"""
Run the Solution Mapper for colleagues on the OFFICE NETWORK only.

    python run_office_server.py          (or double-click start_website.bat)

- Anyone on the office network opens:  http://<this computer's IP>:5000
- Nobody outside the office can reach it (no internet exposure).
- The site works only while this window is open, this computer is on,
  and the Oracle database computer (Terragni-10) is on.
"""
from __future__ import annotations

import faulthandler
import logging
import os
import socket
import sys
import traceback

# If Python itself crashes (e.g. inside the AI model library), print where.
faulthandler.enable()
# Show waitress messages such as "Serving on http://0.0.0.0:5000".
logging.basicConfig(level=logging.INFO, format="%(message)s")
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.app import app, _warm_up  # noqa: E402

PORT = int(os.getenv("PORT", "5000"))


def office_ip() -> str:
    """This computer's address on the office network."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # no data is sent; picks the active network
            return s.getsockname()[0]
    except OSError:
        return socket.gethostbyname(socket.gethostname())


def main() -> None:
    ip = office_ip()
    name = socket.gethostname()

    print("=" * 64)
    print(" Terragni Solution Mapper - office network server")
    print("=" * 64)
    print(" Link for colleagues (office network only):")
    print(f"     http://{ip}:{PORT}")
    print(f"     http://{name}:{PORT}      (also works on most office networks)")
    print()
    print(" Keep this window open. Close it (or press Ctrl+C) to stop.")
    print(" The first answer takes ~30 seconds while the AI model loads.")
    print("=" * 64)

    # Load the AI model and data FIRST, then start serving.
    print(" Loading the AI model and case studies (about 30 seconds)...")
    _warm_up()

    try:
        from waitress import serve
    except ImportError:
        print("waitress is not installed - using Flask's simple server instead.")
        app.run(host="0.0.0.0", port=PORT, threaded=True)
        return

    print()
    print(f" READY - the website is running. Open http://{ip}:{PORT}")
    print(" (If you see the PS> prompt again, the website has STOPPED.)")
    print()
    try:
        serve(app, host="0.0.0.0", port=PORT, threads=8)
    except Exception:
        print("\n*** The website stopped because of this error: ***")
        traceback.print_exc()
    finally:
        print("\n*** Website stopped. Copy the messages above and share them. ***")


if __name__ == "__main__":
    main()

