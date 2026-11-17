import time
import threading
from collections import deque, defaultdict

_lock         = threading.Lock()
_live_history = deque(maxlen=50)
_dead_history = deque(maxlen=50)
_logs         = deque(maxlen=200)
_stats        = {"total":0,"live":0,"dead":0,"unknown":0,"error":0}
_hourly       = defaultdict(lambda: {"live":0,"dead":0,"total":0})

def _hkey():
    t = time.localtime()
    return f"{t.tm_year}-{t.tm_mon:02d}-{t.tm_mday:02d} {t.tm_hour:02d}:00"

def record(card_line: str, result: dict, elapsed: float):
    with _lock:
        entry = {
            "card":   card_line,
            "result": result.get("result"),
            "reason": result.get("reason"),
            "shop":   result.get("shop",""),
            "time":   f"{elapsed:.2f}s",
            "ts":     time.time(),
        }
        r  = result.get("result","ERROR")
        hk = _hkey()
        _stats["total"] += 1
        _hourly[hk]["total"] += 1

        if r == "LIVE":
            _stats["live"]  += 1
            _hourly[hk]["live"] += 1
            _live_history.append(entry)
        elif r == "DEAD":
            _stats["dead"]  += 1
            _hourly[hk]["dead"] += 1
            _dead_history.append(entry)
        elif r == "UNKNOWN":
            _stats["unknown"] += 1
        else:
            _stats["error"]   += 1
        _logs.append(entry)

def get_stats():      return dict(_stats)
def get_hourly():     return dict(_hourly)
def get_live_history(): return list(_live_history)
def get_dead_history(): return list(_dead_history)
def get_logs():       return list(_logs)