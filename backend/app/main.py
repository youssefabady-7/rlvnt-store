import json, logging, time
from collections import defaultdict, deque
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from . import agent, catalog, cart as cartlib, orders
from .config import ALLOWED_ORIGINS, RESEND_API_KEY, OPENROUTER_API_KEY, PRICE_EGP, SHIPPING_EGP, SIZES

log = logging.getLogger("rlvnt")
app = FastAPI(title="RLVNT API")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])


_hits: dict = defaultdict(deque)
RATE_LIMIT, RATE_WINDOW = 20, 60  # chat calls per IP per minute (best effort per instance)


def _limited(ip: str) -> bool:
    now, q = time.time(), _hits[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    return False


class Msg(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=2000)


class ChatIn(BaseModel):
    messages: list[Msg] = Field(max_length=30)
    cart: dict[str, int] = {}
    viewing: str = Field(default="", max_length=20)


@app.get("/api/health")
@app.get("/health")
def health():
    n = len(catalog.load_products())
    checks = {"products": n > 0, "order_email_key_set": bool(RESEND_API_KEY), "order_store_configured": orders.kv_config() is not None, "assistant": bool(OPENROUTER_API_KEY)}
    return {"ok": checks["products"], "status": "ok" if all(checks.values()) else "degraded", "products": n, "checks": checks}


@app.get("/api/products")
def products():
    return {"currency": "EGP", "price": PRICE_EGP, "shipping": SHIPPING_EGP, "sizes": SIZES, "products": catalog.load_products()}


@app.post("/api/cart/summary")
def summary(cart: dict[str, int]):
    return cartlib.summary(cart)


@app.post("/api/chat")
async def chat(body: ChatIn, request: Request):
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "x")).split(",")[0].strip()
    if _limited(ip):
        raise HTTPException(status_code=429, detail="Too many messages, please wait a minute.")
    try:
        return await agent.chat([m.model_dump() for m in body.messages], body.cart, viewing=body.viewing)
    except Exception as e:  # surfaced to the user, logged for us (no silent pass)
        log.exception("chat failed")
        raise HTTPException(status_code=502, detail="The assistant is busy right now. Please try again in a moment.")


_order_hits: dict = defaultdict(deque)


@app.post("/api/order")
async def place_order(body: orders.OrderIn, request: Request):
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "x")).split(",")[0].strip()
    now, q = time.time(), _order_hits[ip]
    while q and now - q[0] > 600:
        q.popleft()
    if len(q) >= 5:
        raise HTTPException(status_code=429, detail="Too many orders from this connection. Please contact support.")
    if body.website:  # honeypot tripped: pretend success
        return {"ok": True, "order_number": orders.order_number()}
    try:
        pr = orders.price(body)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    num = orders.order_number()
    subject, text, html_ = orders.render(body, num, pr)
    stored = await orders.persist(num, text, pr)  # durable record first, before email
    sent = await orders.deliver(subject, text, html_)
    if not sent and stored:
        # Order is safe in KV; the owner reads it there. Customer gets a normal confirmation.
        log.error("ORDER_STORED_EMAIL_FAILED %s", json.dumps({"order": num, "total": pr["total"]}))
        q.append(now)
        return {"ok": True, "confirmed": True, "order_number": num, "total": pr["total"], "shipping": pr["shipping"]}
    if not sent:
        # Fallback: the order is NOT confirmed. Log a minimal trail (no name, address or notes) and make the
        # customer send the prefilled WhatsApp message. Vercel runtime logs are short-lived, so this is a hint only.
        items = [f"{l.qty}x{l.id}/{l.size}" for l in body.items]
        log.error("ORDER_FALLBACK %s", json.dumps({"order": num, "items": items, "total": pr["total"],
                  "phone": orders.mask_phone(body.phone)}))
        q.append(now)
        return {"ok": True, "confirmed": False, "order_number": num, "total": pr["total"], "shipping": pr["shipping"],
                "fallback": True, "whatsapp_url": orders.whatsapp_link(text)}
    q.append(now)
    return {"ok": True, "confirmed": True, "order_number": num, "total": pr["total"], "shipping": pr["shipping"]}
