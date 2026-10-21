"""
WSGI entry point for Render (and any other WSGI host).

Gunicorn command:
    gunicorn wsgi:app
"""
import faulthandler
import os
import sys
import threading
import time

# If the process dies inside native code (segfault etc.), print where.
faulthandler.enable(file=sys.stderr, all_threads=True)


def _memory_watch() -> None:
    """Log memory every 2 s when it changes, so an out-of-memory kill shows up."""
    last = 0
    while True:
        try:
            with open("/proc/self/status", encoding="utf-8") as handle:
                rss = next(int(l.split()[1]) // 1024 for l in handle if l.startswith("VmRSS"))
            if abs(rss - last) >= 15:
                print(f"[memory-watch] {rss} MB", flush=True)
                last = rss
        except Exception:
            return
        time.sleep(2)


if os.getenv("MEMORY_WATCH", "true").lower() == "true":
    threading.Thread(target=_memory_watch, daemon=True).start()

from backend.app.app import app  # noqa: E402,F401

if __name__ == "__main__":
    app.run()
