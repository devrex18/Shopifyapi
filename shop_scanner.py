import requests
import threading
import time
import random
import re
from concurrent.futures import ThreadPoolExecutor
from proxy_manager import proxy_mgr, AGENTS

# seed domains — popular Shopify stores
SEED_DOMAINS = [
    "allbirds.com", "gymshark.com", "fashionnova.com",
    "bombas.com", "brooklinen.com", "mejuri.com",
    "rothys.com", "tentree.com", "kotn.com",
    "rarebeauty.com", "feastables.com", "hexclad.com",
    "blendjet.com", "ourplace.com", "chubbiesshorts.com",
    "puravidabracelets.com", "ruggable.com", "skims.com",
    "mvmtwatches.com", "mountainhardwear.com",
    "nativecos.com", "drinkag1.com", "mudwtr.com",
    "olehenriksen.com", "trueclassictees.com",
    "cuts.com", "vuoriclothing.com", "mack-weldon.com",
    "publiclands.com", "badgley-mischka.com",
    "shopdisney.com", "colourpop.com", "morphe.com",
    "peachslices.com", "juicycouture.com",
]

class ShopPool:
    def __init__(self):
        self._shops:   list  = []
        self._lock           = threading.Lock()
        self._idx            = 0
        self._scanning       = False

        threading.Thread(target=self._auto_scan, daemon=True).start()

    # ── helpers ──────────────────────────────────────

    def _req(self, url, method="get", **kwargs):
        proxy = proxy_mgr.get()
        try:
            fn = getattr(requests, method)
            r  = fn(
                url,
                proxies=proxy,
                headers={"User-Agent": random.choice(AGENTS),
                         "Accept": "application/json",
                         "Accept-Language": "en-US,en;q=0.9"},
                timeout=10,
                allow_redirects=True,
                **kwargs
            )
            return r
        except Exception as e:
            if proxy:
                proxy_mgr.mark_dead(list(proxy.values())[0])
            raise

    def _is_shopify(self, domain: str) -> bool:
        try:
            r = self._req(f"https://{domain}/products.json?limit=1")
            return r.status_code == 200 and "products" in r.json()
        except:
            return False

    def _get_product(self, domain: str) -> dict | None:
        """$0-$10 product dhundo — digital ya small item"""
        try:
            r = self._req(f"https://{domain}/products.json?limit=250")
            if r.status_code != 200:
                return None

            products = r.json().get("products", [])
            candidates = []

            for p in products:
                for v in p.get("variants", []):
                    try:
                        price = float(v.get("price", 999))
                    except:
                        continue

                    # $1 to $10 range
                    if 1.0 <= price <= 10.0:
                        requires_shipping = v.get("requires_shipping", True)
                        candidates.append({
                            "variant_id":        v["id"],
                            "title":             p["title"],
                            "price":             price,
                            "requires_shipping": requires_shipping,
                        })

            if not candidates:
                return None

            # shipping required nahi wala prefer karo
            digital = [c for c in candidates if not c["requires_shipping"]]
            return random.choice(digital) if digital else random.choice(candidates)

        except:
            return None

    def _test_checkout(self, domain: str, variant_id: int) -> bool:
        """Cart add test"""
        try:
            r = self._req(
                f"https://{domain}/cart/add.js",
                method="post",
                json={"id": variant_id, "quantity": 1}
            )
            return r.status_code in (200, 201)
        except:
            return False

    def _get_payment_gateway(self, domain: str) -> str:
        """Store ka payment gateway detect karo"""
        try:
            r = self._req(f"https://{domain}/")
            html = r.text.lower()
            if "shopify_payments" in html or "shopify-payments" in html:
                return "shopify_payments"
            if "stripe" in html:
                return "stripe"
            if "braintree" in html:
                return "braintree"
            return "shopify_payments"  # default
        except:
            return "shopify_payments"

    # ── scan ─────────────────────────────────────────

    def _scan_domain(self, domain: str) -> dict | None:
        if not self._is_shopify(domain):
            return None

        product = self._get_product(domain)
        if not product:
            return None

        if not self._test_checkout(domain, product["variant_id"]):
            return None

        gateway = self._get_payment_gateway(domain)

        return {
            "domain":     domain,
            "variant_id": product["variant_id"],
            "title":      product["title"],
            "price":      product["price"],
            "gateway":    gateway,
            "failures":   0,
            "healthy":    True,
            "cooled_at":  0,
            "total":      0,
            "success":    0,
        }

    def _scan_all(self, domains: list):
        print(f"[scanner] scanning {len(domains)} domains...")
        with ThreadPoolExecutor(max_workers=10) as ex:
            results = list(ex.map(self._scan_domain, domains))

        found = [r for r in results if r]
        with self._lock:
            existing = {s["domain"] for s in self._shops}
            for shop in found:
                if shop["domain"] not in existing:
                    self._shops.append(shop)
            print(f"[scanner] {len(self._shops)} total working shops")

    def _auto_scan(self):
        while True:
            self._scan_all(SEED_DOMAINS)
            time.sleep(3600)  # har 1 hour re-scan

    # ── pool management ───────────────────────────────

    def get(self) -> dict | None:
        with self._lock:
            # dead shops revive check
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
                        print(f"[shop] {domain} marked dead")
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
                    "price":        s["price"],
                    "healthy":      s["healthy"],
                    "failures":     s["failures"],
                    "success_rate": f"{round(s['success']/s['total']*100)}%" if s['total'] else "0%",
                }
                for s in self._shops
            ]

shop_pool = ShopPool()