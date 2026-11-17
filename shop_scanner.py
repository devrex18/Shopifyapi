import requests
import threading
import time
import random
import re
from concurrent.futures import ThreadPoolExecutor
from proxy_manager import proxy_mgr, AGENTS

SEED_DOMAINS = [
    "allbirds.com", "gymshark.com", "fashionnova.com",
    "bombas.com", "brooklinen.com", "mejuri.com",
    "rothys.com", "tentree.com", "kotn.com",
    "rarebeauty.com", "feastables.com", "hexclad.com",
    "blendjet.com", "ourplace.com", "chubbiesshorts.com",
    "puravidabracelets.com", "ruggable.com",
    "mvmtwatches.com", "nativecos.com", "drinkag1.com",
    "trueclassictees.com", "cuts.com", "vuoriclothing.com",
    "colourpop.com", "morphe.com", "peachslices.com",
    "juicycouture.com", "badgley-mischka.com",
    "mack-weldon.com", "publiclands.com",
]

class ShopPool:
    def __init__(self):
        self._shops: list = []
        self._lock        = threading.Lock()
        self._idx         = 0

    def _req(self, url, method="get", **kwargs):
        proxy = proxy_mgr.get()
        try:
            fn = getattr(requests, method)
            r  = fn(
                url,
                proxies=proxy,
                headers={
                    "User-Agent":      random.choice(AGENTS),
                    "Accept":          "application/json",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=10,
                allow_redirects=True,
                **kwargs
            )
            return r
        except Exception as e:
            if proxy:
                try:
                    proxy_mgr.mark_dead(list(proxy.values())[0])
                except:
                    pass
            raise

    def _is_shopify(self, domain: str) -> bool:
        try:
            r = self._req(f"https://{domain}/products.json?limit=1")
            return r.status_code == 200 and "products" in r.json()
        except:
            return False

    def _get_product(self, domain: str) -> dict | None:
        try:
            r = self._req(f"https://{domain}/products.json?limit=250")
            if r.status_code != 200:
                return None

            candidates = []
            for p in r.json().get("products", []):
                for v in p.get("variants", []):
                    try:
                        price = float(v.get("price", 999))
                    except:
                        continue
                    if 1.0 <= price <= 10.0:
                        candidates.append({
                            "variant_id":        v["id"],
                            "title":             p["title"],
                            "price":             price,
                            "requires_shipping": v.get("requires_shipping", True),
                        })

            if not candidates:
                return None

            digital = [c for c in candidates if not c["requires_shipping"]]
            return random.choice(digital) if digital else random.choice(candidates)
        except:
            return None

    def _test_checkout(self, domain: str, variant_id: int) -> bool:
        try:
            r = self._req(
                f"https://{domain}/cart/add.js",
                method="post",
                json={"id": variant_id, "quantity": 1}
            )
            return r.status_code in (200, 201)
        except:
            return False

    def _scan_domain(self, domain: str) -> dict | None:
        try:
            if not self._is_shopify(domain):
                return None
            product = self._get_product(domain)
            if not product:
                return None
            if not self._test_checkout(domain, product["variant_id"]):
                return None
            print(f"[shop] ✓ {domain} — {product['title']} ${product['price']}")
            return {
                "domain":     domain,
                "variant_id": product["variant_id"],
                "title":      product["title"],
                "price":      product["price"],
                "failures":   0,
                "healthy":    True,
                "cooled_at":  0,
                "total":      0,
                "success":    0,
            }
        except:
            return None

    def scan(self, domains: list = None):
        targets = domains or SEED_DOMAINS
        print(f"[scanner] scanning {len(targets)} domains...")
        # Railway free tier — 5 workers max
        with ThreadPoolExecutor(max_workers=5) as ex:
            results = list(ex.map(self._scan_domain, targets))

        with self._lock:
            existing = {s["domain"] for s in self._shops}
            added = 0
            for r in results:
                if r and r["domain"] not in existing:
                    self._shops.append(r)
                    added += 1
            print(f"[scanner] +{added} shops — total {len(self._shops)}")

    def _auto_scan(self):
        while True:
            self.scan()
            time.sleep(3600)

    def start(self):
        threading.Thread(target=self._auto_scan, daemon=True).start()

    def get(self) -> dict | None:
        with self._lock:
            now = time.time()
            for s in self._shops:
                if not s["healthy"] and (now - s["cooled_at"]) > 300:
                    s["healthy"]  = True
                    s["failures"] = 0

            alive = [s for s in self._shops if s["healthy"]]
            if not alive:
                return None

            self._idx = self._idx % len(alive)
            shop = alive[self._idx]
            self._idx += 1
            return shop

    def mark_fail(self, domain: str):
        with self._lock:
            for s in self._shops:
                if s["domain"] == domain:
                    s["failures"] += 1
                    s["cooled_at"] = time.time()
                    if s["failures"] >= 3:
                        s["healthy"] = False
                    break

    def mark_win(self, domain: str):
        with self._lock:
            for s in self._shops:
                if s["domain"] == domain:
                    s["total"]   += 1
                    s["success"] += 1
                    s["failures"] = 0
                    break

    def status(self) -> list:
        with self._lock:
            return [
                {
                    "domain":       s["domain"],
                    "product":      s["title"],
                    "price":        f"${s['price']}",
                    "healthy":      s["healthy"],
                    "failures":     s["failures"],
                    "success_rate": f"{round(s['success']/s['total']*100)}%" if s["total"] else "0%",
                }
                for s in self._shops
            ]

shop_pool = ShopPool()