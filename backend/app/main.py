import logging, time
from collections import defaultdict, deque
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from . import agent, catalog, cart as cartlib
from .config import ALLOWED_ORIGINS, PRICE_EGP

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


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/products")
def products():
    return {"currency": "EGP", "price": PRICE_EGP, "products": catalog.load_products()}


@app.post("/api/cart/summary")
def summary(cart: dict[str, int]):
    return cartlib.summary(cart)


@app.post("/api/chat")
async def chat(body: ChatIn, request: Request):
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "x")).split(",")[0].strip()
    if _limited(ip):
        raise HTTPException(status_code=429, detail="Too many messages, please wait a minute.")
    try:
        return await agent.chat([m.model_dump() for m in body.messages], body.cart)
    except Exception as e:  # surfaced to the user, logged for us (no silent pass)
        log.exception("chat failed")
        raise HTTPException(status_code=502, detail="The assistant is busy right now. Please try again in a moment.")
