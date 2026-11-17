import time
import threading
from collections import defaultdict

_counts: dict = defaultdict(list)
_lock         = threading.Lock()
LIMIT         = int(__import__("os").environ.get("RATE_LIMIT","100"))

def is_rate_limited(key: str) -> bool:
    now = time.time()
    with _lock:
        _counts[key] = [t for t in _counts[key] if now - t < 60]
        if len(_counts[key]) >= LIMIT:
            return True
        _counts[key].append(now)
        return False