import json
import httpx
from . import cart as cartlib, catalog
from .knowledge import system_prompt
from . import guard
from .config import (OPENROUTER_API_KEY, OPENROUTER_URL, MODEL, FALLBACK_MODELS,
                     MAX_TOOL_STEPS, PRICE_EGP)


TOOLS = [
    {"type": "function", "function": {
        "name": "search_products", "description": "Search the catalog.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}, "category": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "add_to_cart", "description": "Add a product to the cart.",
        "parameters": {"type": "object", "properties": {
            "product_id": {"type": "string"}, "quantity": {"type": "integer"}},
            "required": ["product_id"]}}},
    {"type": "function", "function": {
        "name": "remove_from_cart", "description": "Remove a product (or some units) from the cart.",
        "parameters": {"type": "object", "properties": {
            "product_id": {"type": "string"}, "quantity": {"type": "integer"}},
            "required": ["product_id"]}}},
    {"type": "function", "function": {
        "name": "set_quantity", "description": "Set the exact quantity of a product in the cart (0 removes it).",
        "parameters": {"type": "object", "properties": {
            "product_id": {"type": "string"}, "quantity": {"type": "integer"}},
            "required": ["product_id", "quantity"]}}},
    {"type": "function", "function": {
        "name": "clear_cart", "description": "Empty the cart.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "view_cart", "description": "Show cart contents and total.",
        "parameters": {"type": "object", "properties": {}}}},
]


def run_tool(name: str, args: dict, cart: dict, shown: list) -> tuple[dict, str]:
    if name == "search_products":
        res = catalog.search(args.get("query", ""), args.get("category", ""))
        for p in res:
            if p["id"] not in [s["id"] for s in shown]:
                shown.append(p)
        return cart, json.dumps(res)
    if name == "add_to_cart":
        cart, msg = cartlib.add(cart, str(args.get("product_id", "")), args.get("quantity", 1))
    elif name == "remove_from_cart":
        cart, msg = cartlib.remove(cart, str(args.get("product_id", "")), args.get("quantity"))
    elif name == "set_quantity":
        pid, q = str(args.get("product_id", "")), int(args.get("quantity", 0) or 0)
        cart = {k: v for k, v in cart.items() if k != pid} if q <= 0 else cart
        msg = "ok"
        if q > 0:
            cart, msg = cartlib.remove(cart, pid) if pid in cart else (cart, "ok")
            cart, msg = cartlib.add(cart, pid, q)
    elif name == "clear_cart":
        cart, msg = cartlib.clear(cart)
    elif name == "view_cart":
        return cart, json.dumps(cartlib.summary(cart))
    else:
        return cart, f"error: unknown tool {name}"
    return cart, json.dumps({"result": msg, "cart": cartlib.summary(cart)})


async def _call(client: httpx.AsyncClient, model: str, messages: list) -> dict:
    r = await client.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
        json={"model": model, "messages": messages, "tools": TOOLS, "temperature": 0.2},
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]


async def chat(history: list[dict], cart: dict, transport=None, viewing: str = "") -> dict:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    messages = [{"role": "system", "content": system_prompt(cart, viewing)}] + history[-12:]
    last_user = next((m["content"] for m in reversed(history) if m.get("role") == "user"), "")
    retried = False
    shown: list = []
    async with httpx.AsyncClient(timeout=45, transport=transport) as client:
        for _ in range(MAX_TOOL_STEPS):
            msg, last_err = None, None
            for model in [MODEL, *FALLBACK_MODELS]:
                try:
                    msg = await _call(client, model, messages)
                    break
                except httpx.HTTPError as e:  # rate limit etc: try next model
                    last_err = e
            if msg is None:
                raise RuntimeError(f"LLM unavailable: {last_err}")
            calls = msg.get("tool_calls") or []
            if not calls:
                reply = msg.get("content") or ""
                bad = guard.check(reply)
                if bad and not retried:
                    retried = True  # one corrective retry, then the safe fallback
                    messages.append({"role": "assistant", "content": reply})
                    messages.append({"role": "user", "content": "SYSTEM CHECK: your last reply broke the grounding rules (" + "; ".join(bad[:3]) + "). Reply again directly to the customer's last message (do not mention this check or your earlier reply), using only real catalog products, the flat 800 EGP price and 100 EGP shipping, no discounts, same language and tone."})
                    continue
                if bad:
                    reply = guard.safe_reply(last_user)
                reply = guard.clean_links(reply)
                return {"reply": reply, "cart": cart,
                        "summary": cartlib.summary(cart), "products": shown}
            messages.append(msg)
            for c in calls:
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                cart, out = run_tool(c["function"]["name"], args, cart, shown)
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": out})
    return {"reply": "Sorry, I could not finish that. Try again.", "cart": cart,
            "summary": cartlib.summary(cart), "products": shown}
