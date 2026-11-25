import json
from pathlib import Path
from .config import PRICE_EGP

_PATH = Path(__file__).parent / "products.json"


def load_products() -> list[dict]:
    items = json.loads(_PATH.read_text(encoding="utf-8"))
    for p in items:
        p["price"] = PRICE_EGP  # price is forced flat, whatever the file says
    return items


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
