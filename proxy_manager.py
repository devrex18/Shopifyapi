import requests
import threading
import time
import random
import itertools
from concurrent.futures import ThreadPoolExecutor

AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
]

# free proxy sources
PROXY_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
]

class ProxyManager:
    def __init__(self):
        self._live:    list  = []
        self._dead:    set   = set()
        self._lock           = threading.Lock()
        self._cycle          = None
        self._last_refresh   = 0
        self._refreshing     = False

        # startup pe fetch karo
        threading.Thread(target=self._auto_refresh, daemon=True).start()

    def _fetch_raw(self) -> list:
        all_proxies = []
        for url in PROXY_SOURCES:
            try:
                r = requests.get(url, timeout=10,
                    headers={"User-Agent": random.choice(AGENTS)})
                if r.status_code == 200:
                    lines = r.text.strip().split("\n")
                    for line in lines:
                        line = line.strip()
                        if ":" in line and len(line) < 30:
                            all_proxies.append(f"http://{line}")
            except:
                pass
        return list(set(all_proxies))

    def _test_proxy(self, proxy: str) -> bool:
        try:
            r = requests.get(
                "https://httpbin.org/ip",
                proxies={"http": proxy, "https": proxy},
                timeout=6,
                headers={"User-Agent": random.choice(AGENTS)}
            )
            return r.status_code == 200
        except:
            return False

    def _refresh(self):
        if self._refreshing:
            return
        self._refreshing = True
        print("[proxy] fetching proxy list...")

        raw = self._fetch_raw()
        print(f"[proxy] testing {len(raw)} proxies...")

        live = []
        with ThreadPoolExecutor(max_workers=50) as ex:
            results = list(ex.map(self._test_proxy, raw[:500]))  # top 500 test

        for proxy, ok in zip(raw[:500], results):
            if ok:
                live.append(proxy)

        with self._lock:
            self._live  = live
            self._cycle = itertools.cycle(live) if live else None
            self._dead  = set()

        print(f"[proxy] {len(live)} live proxies ready")
        self._last_refresh = time.time()
        self._refreshing   = False

    def _auto_refresh(self):
        while True:
            self._refresh()
            time.sleep(1800)  # har 30 min refresh

    def get(self) -> dict | None:
        with self._lock:
            if not self._cycle:
                return None
            # dead skip karo
            for _ in range(len(self._live)):
                p = next(self._cycle)
                if p not in self._dead:
                    return {"http": p, "https": p}
        return None

    def mark_dead(self, proxy_str: str):
        with self._lock:
            self._dead.add(proxy_str)
            # 70% dead toh refresh
            if len(self._dead) > len(self._live) * 0.7:
                threading.Thread(target=self._refresh, daemon=True).start()

    def status(self) -> dict:
        with self._lock:
            return {
                "live":  len(self._live),
                "dead":  len(self._dead),
                "ready": self._cycle is not None
            }

proxy_mgr = ProxyManager()