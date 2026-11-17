import time
import threading

def luhn_check(cc: str) -> bool:
    try:
        digits  = [int(d) for d in cc if d.isdigit()]
        if not (13 <= len(digits) <= 19):
            return False
        total   = 0
        reverse = digits[::-1]
        for i, d in enumerate(reverse):
            if i % 2 == 1:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        return total % 10 == 0
    except:
        return False

def validate_card(cc, month, year, cvv) -> tuple[bool, str]:
    if not cc.isdigit():
        return False, "CC_NOT_DIGITS"
    if not (13 <= len(cc) <= 19):
        return False, "CC_INVALID_LENGTH"
    if not luhn_check(cc):
        return False, "CC_LUHN_FAIL"
    try:
        if not (1 <= int(month) <= 12):
            return False, "INVALID_MONTH"
    except:
        return False, "INVALID_MONTH"
    try:
        if int(year) < time.localtime().tm_year % 100:
            return False, "CARD_EXPIRED"
    except:
        return False, "INVALID_YEAR"
    if not cvv.isdigit() or not (3 <= len(cvv) <= 4):
        return False, "INVALID_CVV"
    return True, "OK"

class DuplicateFilter:
    def __init__(self):
        self._seen = set()
        self._lock = threading.Lock()

    def is_duplicate(self, cc: str) -> bool:
        with self._lock:
            if cc in self._seen:
                return True
            self._seen.add(cc)
            return False

    def clear(self):
        with self._lock:
            self._seen.clear()

dup_filter = DuplicateFilter()