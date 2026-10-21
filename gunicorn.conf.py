"""
Gunicorn settings, loaded automatically by `gunicorn wsgi:app`.

post_fork runs inside the WORKER process right after it is created. The
warm-up (embedding model + Supabase data) and the memory monitor start
there, so only one copy of the model ever exists (Render Starter = 512 MB).
"""
import os
import threading
import time


def _memory_watch(pid: int) -> None:
    last = 0
    while True:
        try:
            with open("/proc/self/status", encoding="utf-8") as handle:
                rss = next(int(l.split()[1]) // 1024 for l in handle if l.startswith("VmRSS"))
            if abs(rss - last) >= 15:
                print(f"[memory-watch] worker {pid}: {rss} MB", flush=True)
                last = rss
        except Exception:
            return
        time.sleep(2)


def post_fork(server, worker):
    from backend.app.app import start_warm_up

    start_warm_up()
    if os.getenv("MEMORY_WATCH", "true").lower() == "true":
        threading.Thread(target=_memory_watch, args=(worker.pid,), daemon=True).start()
