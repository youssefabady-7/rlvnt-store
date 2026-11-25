"""Store settings. Defaults are the original values; the owner overrides them from the admin page (stored in KV)."""
import json, re, time
from . import kv
from .config import ORDER_EMAIL, SHIPPING_EGP, SUPPORT_EMAIL, SUPPORT_PHONE

DEFAULTS = {
    "store_name": "RLVNT",
    "announcement": "Cash on delivery · 3 to 5 day delivery · 800 EGP every piece",
    "shipping_fee": SHIPPING_EGP,
    "delivery_text": "",
    "return_text": "",
    "support_phone": SUPPORT_PHONE,
    "support_email": SUPPORT_EMAIL,
    "order_email": ORDER_EMAIL,
    "whatsapp_number": SUPPORT_PHONE.lstrip("+"),
    "chatbot_enabled": True,
}
PRIVATE = {"order_email"}
TTL = 15
_cache = {"t": 0.0, "v": None}


def _clean(raw: dict) -> dict:
    out = dict(DEFAULTS)
    for k, v in (raw or {}).items():
        if k in DEFAULTS:
            out[k] = v
    return out


def validate(raw: dict) -> dict:
    """Return a validated full settings dict or raise ValueError with a readable message."""
    s = _clean(raw)
    def text(k, lo, hi):
        v = str(s[k]).strip()
        if not (lo <= len(v) <= hi):
            raise ValueError(f"{k} must be {lo} to {hi} characters")
        s[k] = v
    text("store_name", 2, 40); text("announcement", 0, 140); text("delivery_text", 0, 300); text("return_text", 0, 500)
    try:
        s["shipping_fee"] = int(s["shipping_fee"])
    except (TypeError, ValueError):
        raise ValueError("shipping_fee must be a number")
    if not (0 <= s["shipping_fee"] <= 5000):
        raise ValueError("shipping_fee must be between 0 and 5000")
    if not re.fullmatch(r"\+?[0-9 ()-]{8,20}", str(s["support_phone"]).strip()):
        raise ValueError("support_phone is not a valid phone number")
    s["support_phone"] = str(s["support_phone"]).strip()
    for k in ("support_email", "order_email"):
        s[k] = str(s[k]).strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", s[k]) or len(s[k]) > 120:
            raise ValueError(f"{k} is not a valid email")
    s["whatsapp_number"] = re.sub(r"\D", "", str(s["whatsapp_number"]))
    if not (8 <= len(s["whatsapp_number"]) <= 15):
        raise ValueError("whatsapp_number must be digits with country code, e.g. 201270383409")
    s["chatbot_enabled"] = bool(s["chatbot_enabled"])
    return s


def load(force: bool = False) -> dict:
    now = time.monotonic()
    if not force and _cache["v"] is not None and now - _cache["t"] < TTL:
        return _cache["v"]
    val = None
    if kv.available():
        try:
            raw = kv.cmd("GET", "settings")
            val = validate(json.loads(raw)) if raw else dict(DEFAULTS)
        except Exception:
            val = _cache["v"]  # keep last good on KV trouble
    _cache.update(t=now, v=val if val is not None else dict(DEFAULTS))
    return _cache["v"]


def save(raw: dict) -> dict:
    s = validate(raw)
    kv.cmd("SET", "settings", json.dumps(s, ensure_ascii=False))
    _cache.update(t=time.monotonic(), v=s)
    return s


def public() -> dict:
    return {k: v for k, v in load().items() if k not in PRIVATE}
