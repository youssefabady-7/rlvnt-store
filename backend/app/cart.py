"""Pure cart logic. The cart is a dict {product_id: qty} owned by the client and
sent with each request, so the backend stays stateless."""
from . import catalog


def add(cart: dict, pid: str, qty: int = 1) -> tuple[dict, str]:
    p = catalog.by_id(pid)
    if not p:
        return cart, f"error: unknown product id {pid}"
    if p.get("sold_out"):
        return cart, f"error: {p['name']} is sold out"
    qty = max(1, min(int(qty), 10))
    cart = dict(cart)
    cart[pid] = min(cart.get(pid, 0) + qty, 20)
    return cart, "ok"


def remove(cart: dict, pid: str, qty: int | None = None) -> tuple[dict, str]:
    if pid not in cart:
        return cart, f"error: {pid} is not in the cart"
    cart = dict(cart)
    if qty is None or qty >= cart[pid]:
        del cart[pid]
    else:
        cart[pid] -= max(1, int(qty))
    return cart, "ok"


def clear(cart: dict) -> tuple[dict, str]:
    return {}, "ok"


def summary(cart: dict) -> dict:
    lines = []
    for pid, q in cart.items():
        p = catalog.by_id(pid)
        if p:
            lines.append({"id": pid, "name": p["name"], "qty": q, "line_total": q * p["price"]})
    return {"items": lines, "total_egp": sum(l["line_total"] for l in lines)}
