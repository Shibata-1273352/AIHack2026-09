"""Serialize demo mutations and protect reset from in-flight agent work."""
from threading import RLock

lock = RLock()
workers: set[str] = set()


def run_worker(key, fn, *args):
    try:
        fn(*args)
    finally:
        with lock:
            workers.discard(key)
