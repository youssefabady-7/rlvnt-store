"""Post-check on assistant replies. The model is told the rules, this code enforces the checkable ones:
prices, discounts, product names and ids must exist in the catalog. Not a proof against every wrong sentence."""
import re
from functools import lru_cache
from . import catalog
from .config import PRICE_EGP

_NUM = r"(\d[\d,\.]*)"
_AR = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_MONEY = re.compile(rf"{_NUM}\s*(?:egp|le|l\.e|جنيه|جنية|ج\.م|ج)(?![a-z\u0600-\u06ff])|(?:egp|le)\s*{_NUM}", re.I)
_DISCOUNT = re.compile(r"(\d+\s*%|percent|promo code|coupon|voucher|كوبون|كود خصم|free shipping|شحن مجاني|buy \d+ get)", re.I)
_DISC_WORD = re.compile(r"(discount|sale\b|offer|خصم|تخفيض|عرض)", re.I)
_NEG = re.compile(r"(\bno\b|\bnot\b|n't|n\u2019t|\bnever\b|\bnor\b|invalid|isn|wrong|without|none|مفيش|مافيش|مش |ما فيش|لا يوجد|ليس)", re.I)
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ID = re.compile(r"\brl-\d{3}\b", re.I)
_LINK = re.compile(r"\[\[\s*(rl-\d{3})\s*\]\]", re.I)


def allowed_amounts() -> set:
    from . import settings
    return _amounts(tuple(sorted({p["price"] for p in catalog.load_products()})) or (PRICE_EGP,), settings.load()["shipping_fee"])


@lru_cache(maxsize=8)
def _amounts(prices: tuple, ship: int) -> set:
    """Every amount a customer could legitimately be quoted: item prices, shipping, and cart totals
    (sums of up to 20 pieces, with or without shipping)."""
    sums = {0}
    for _ in range(20):
        sums |= {s + p for s in sums for p in prices}
        if len(sums) > 20000:
            break
    a = {s for s in sums if s} | {s + ship for s in sums} | {ship}
    return a


def _norm(n: str) -> str:
    return re.sub(r"[^a-z0-9\u0600-\u06ff ]", "", n.lower()).strip()


_STRAY = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0400-\u04ff\u0e00-\u0e7f]")


def check(reply: str) -> list[str]:
    """Return a list of problems found in the reply (empty means it passes)."""
    problems = []
    if _STRAY.search(reply):
        problems.append("stray characters from another script")
    t = reply.translate(_AR)
    ok = allowed_amounts()
    for m in _MONEY.finditer(t):
        raw = (m.group(1) or m.group(2) or "").replace(",", "")
        try:
            v = float(raw.rstrip("."))
        except ValueError:
            continue
        if v not in ok:
            problems.append(f"price {raw} is not a valid amount")
    for m in _DISCOUNT.finditer(t):
        window = t[max(0, m.start() - 60): m.end() + 40]
        if not _NEG.search(window):
            problems.append(f"discount claim: {m.group(0)}")
    if re.search(r"\bE(?:PG|GP|PG)\b", t) and re.search(r"\bEPG\b", t):
        problems.append("currency must be written EGP")
    ids = {p["id"] for p in catalog.load_products()}
    for i in _ID.findall(t):
        if i.lower() not in ids:
            problems.append(f"unknown product id {i}")
    names = {_norm(p["name"]) for p in catalog.load_products()}
    for b in _BOLD.findall(t):
        nb = _norm(b)
        if nb and not nb.startswith(("rl", "egp")) and not re.search(r"\d", nb) and nb not in names and not any(nb in n or n in nb for n in names):
            if len(nb) > 3 and nb not in ("order total", "total", "cash on delivery", "rlvnt", "whatsapp", "place order"):
                problems.append(f"unknown product name {b}")
    return problems


def clean_links(reply: str) -> str:
    """Drop [[id]] tokens that are not real products."""
    ids = {p["id"] for p in catalog.load_products()}
    return _LINK.sub(lambda m: m.group(0) if m.group(1).lower() in ids else "", reply)


SAFE = {
    "en": "I don't want to give you wrong info, and I'm not sure about that one. Please ask the team directly on WhatsApp +201270383409 and they'll sort you out. Happy to help with anything else about the drop in the meantime.",
    "ar": "مش عايز أقولك حاجة غلط، ومش متأكد من النقطة دي. كلم الفريق على واتساب +201270383409 وهيفيدوك. وأنا موجود لأي حاجة تانية عن القطع.",
}


def safe_reply(user_text: str) -> str:
    from . import settings
    t = SAFE["ar"] if re.search(r"[\u0600-\u06ff]", user_text or "") else SAFE["en"]
    return t.replace("+201270383409", settings.load()["support_phone"])
