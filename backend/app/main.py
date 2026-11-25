import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from . import agent, catalog, cart as cartlib
from .config import ALLOWED_ORIGINS, PRICE_EGP

log = logging.getLogger("rlvnt")
app = FastAPI(title="RLVNT API")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])


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
async def chat(body: ChatIn):
    try:
        return await agent.chat([m.model_dump() for m in body.messages], body.cart)
    except Exception as e:  # surfaced to the user, logged for us (no silent pass)
        log.exception("chat failed")
        raise HTTPException(status_code=502, detail=str(e)[:200])
