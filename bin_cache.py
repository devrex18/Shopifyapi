import requests
import threading
import time
import random
from proxy_manager import AGENTS

_cache: dict = {}
_lock        = threading.Lock()
TTL          = 3600

COUNTRY_EMOJIS = {
    "UNITED STATES":"🇺🇸","INDIA":"🇮🇳","UNITED KINGDOM":"🇬🇧",
    "CANADA":"🇨🇦","AUSTRALIA":"🇦🇺","GERMANY":"🇩🇪",
    "FRANCE":"🇫🇷","BRAZIL":"🇧🇷","SOUTH KOREA":"🇰🇷",
    "JAPAN":"🇯🇵","CHINA":"🇨🇳","RUSSIA":"🇷🇺",
    "MEXICO":"🇲🇽","ITALY":"🇮🇹","SPAIN":"🇪🇸",
    "NETHERLANDS":"🇳🇱","SINGAPORE":"🇸🇬","HONG KONG":"🇭🇰",
    "TURKEY":"🇹🇷","SAUDI ARABIA":"🇸🇦","THAILAND":"🇹🇭",
    "INDONESIA":"🇮🇩","PAKISTAN":"🇵🇰","NIGERIA":"🇳🇬",
}

def _emoji(country: str) -> str:
    return COUNTRY_EMOJIS.get(country.upper(), "🌐")

def bin_lookup(cc: str) -> dict:
    bin6    = cc[:6]
    default = {"brand":"UNKNOWN","issuer":"UNKNOWN",
               "country":"UNKNOWN","emoji":"🌐",
               "type":"UNKNOWN","level":"UNKNOWN"}

    with _lock:
        if bin6 in _cache:
            if time.time() - _cache[bin6]["ts"] < TTL:
                return _cache[bin6]["data"]

    result = None

    try:
        r = requests.get(
            f"https://lookup.binlist.net/{bin6}",
            headers={"Accept-Version":"3","User-Agent":random.choice(AGENTS)},
            timeout=6
        )
        if r.status_code == 200:
            d       = r.json()
            country = d.get("country",{}).get("name","UNKNOWN").upper()
            result  = {
                "brand":   d.get("scheme","UNKNOWN").upper(),
                "issuer":  d.get("bank",{}).get("name","UNKNOWN").upper(),
                "country": country,
                "emoji":   d.get("country",{}).get("emoji", _emoji(country)),
                "type":    d.get("type","UNKNOWN").upper(),
                "level":   d.get("brand","UNKNOWN").upper(),
            }
    except:
        pass

    if not result:
        try:
            r = requests.get(
                f"https://api.bincodes.com/bin/?format=json&api_key=free&bin={bin6}",
                timeout=6
            )
            if r.status_code == 200:
                d       = r.json()
                country = d.get("country","UNKNOWN").upper()
                result  = {
                    "brand":   d.get("card","UNKNOWN").upper(),
                    "issuer":  d.get("bank","UNKNOWN").upper(),
                    "country": country,
                    "emoji":   _emoji(country),
                    "type":    d.get("type","UNKNOWN").upper(),
                    "level":   "UNKNOWN",
                }
        except:
            pass

    if not result:
        result = default

    with _lock:
        _cache[bin6] = {"data": result, "ts": time.time()}

    return result