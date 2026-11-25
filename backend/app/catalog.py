import json, time
from pathlib import Path
from . import kv
from .config import PRICE_EGP, SIZES

_PATH = Path(__file__).parent / "products.json"
TTL = 15
_cache = {"t": 0.0, "v": None}


def _seed() -> list[dict]:
    return json.loads(_PATH.read_text(encoding="utf-8"))


def _norm(p: dict) -> dict:
    p = dict(p)
    p["price"] = int(p.get("price") or PRICE_EGP)
    p["sizes"] = [s for s in SIZES if s in (p.get("sizes") or SIZES)]
    p["hidden"] = bool(p.get("hidden", False))
    p["sold_out"] = bool(p.get("sold_out", False))
    p.setdefault("tags", [])
    return p


def load_all(force: bool = False) -> list[dict]:
    """Every product including hidden ones, in display order. KV (admin edits) wins, the seed file is the fallback."""
    now = time.monotonic()
    if not force and _cache["v"] is not None and now - _cache["t"] < TTL:
        return _cache["v"]
    items = None
    if kv.available():
        try:
            raw = kv.cmd("GET", "catalog:products")
            items = json.loads(raw) if raw else _seed()
        except Exception:
            items = _cache["v"]  # last good copy while KV is unreachable
    if items is None:
        items = _seed()
    items = [_norm(p) for p in items]
    _cache.update(t=now, v=items)
    return items


def set_cache(items: list[dict]) -> None:
    _cache.update(t=time.monotonic(), v=[_norm(p) for p in items])


def load_products() -> list[dict]:
    """What customers and the chatbot see: visible products only."""
    return [p for p in load_all() if not p["hidden"]]


def by_id(pid: str) -> dict | None:
    return next((p for p in load_products() if p["id"] == pid), None)


def search(query: str = "", category: str = "", limit: int = 5) -> list[dict]:
    q = query.lower().split()
    out = []
    for p in load_products():
        if category and p["category"].lower() != category.lower():
            continue
        hay = " ".join([p["name"], p["category"], p["description"], *p["tags"]]).lower()
        score = sum(1 for w in q if w in hay)
        if not q or score:
            out.append((score, p))
    out.sort(key=lambda x: -x[0])
    return [p for _, p in out[:limit]]
