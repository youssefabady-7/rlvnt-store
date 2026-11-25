import html, random, re, string, time
import httpx
from pydantic import BaseModel, Field, field_validator
from . import catalog
from .config import (PRICE_EGP, SHIPPING_EGP, SIZES, ORDER_EMAIL, RESEND_API_KEY, ORDER_FROM)


class Line(BaseModel):
    id: str
    size: str
    qty: int = Field(ge=1, le=20)

    @field_validator("size")
    @classmethod
    def _size(cls, v):
        v = v.upper()
        if v not in SIZES:
            raise ValueError("invalid size")
        return v


class OrderIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=8, max_length=20)
    city: str = Field(min_length=2, max_length=60)
    address: str = Field(min_length=5, max_length=300)
    notes: str = Field(default="", max_length=300)
    items: list[Line] = Field(min_length=1, max_length=30)
    website: str = ""  # honeypot, real users leave it empty

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        if not re.fullmatch(r"\+?[0-9 ()-]{8,20}", v):
            raise ValueError("invalid phone")
        return v


def order_number() -> str:
    tail = "".join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"RL-{int(time.time()) % 10**8:08d}{tail}"


def price(order: OrderIn) -> dict:
    lines, subtotal = [], 0
    for l in order.items:
        p = catalog.by_id(l.id)
        if not p:
            raise ValueError(f"unknown product {l.id}")
        lines.append({"name": p["name"], "id": l.id, "size": l.size, "qty": l.qty, "total": l.qty * PRICE_EGP})
        subtotal += l.qty * PRICE_EGP
    return {"lines": lines, "subtotal": subtotal, "shipping": SHIPPING_EGP, "total": subtotal + SHIPPING_EGP}


def render(order: OrderIn, num: str, pr: dict) -> tuple[str, str, str]:
    rows = "\n".join(f"- {l['qty']} x {l['name']} ({l['id']}), size {l['size']}: {l['total']} EGP" for l in pr["lines"])
    text = (f"New RLVNT order {num} (cash on delivery)\n\n{rows}\n\nSubtotal: {pr['subtotal']} EGP\nShipping: {pr['shipping']} EGP\n"
            f"TOTAL TO COLLECT: {pr['total']} EGP\n\nCustomer: {order.name}\nPhone/WhatsApp: {order.phone}\nCity: {order.city}\n"
            f"Address: {order.address}\nNotes: {order.notes or '-'}\n")
    h = "<br>".join(html.escape(text).split("\n"))
    return f"New RLVNT order {num}: {pr['total']} EGP COD", text, f"<div style='font-family:Arial'>{h}</div>"


async def send_email(subject: str, text: str, body_html: str, transport=None) -> None:
    if not RESEND_API_KEY:
        raise RuntimeError("order email is not configured")
    async with httpx.AsyncClient(timeout=20, transport=transport) as c:
        r = await c.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                         json={"from": ORDER_FROM, "to": [ORDER_EMAIL], "subject": subject, "text": text, "html": body_html})
    if r.status_code >= 300:
        raise RuntimeError(f"email provider error {r.status_code}")


def mask_phone(p: str) -> str:
    d = re.sub(r"\D", "", p)
    return "*" * max(len(d) - 3, 0) + d[-3:]


def whatsapp_link(text: str) -> str:
    """Prefilled WhatsApp link so the customer can send the order themselves if email delivery fails."""
    from urllib.parse import quote
    from .config import SUPPORT_PHONE
    return f"https://wa.me/{SUPPORT_PHONE.lstrip('+')}?text={quote(text)}"


async def deliver(subject: str, text: str, body_html: str, transport=None, retries: int = 2) -> bool:
    """Try the email provider (retrying once). Return False when every attempt failed."""
    import asyncio
    for attempt in range(retries):
        try:
            await send_email(subject, text, body_html, transport=transport)
            return True
        except Exception:
            if attempt + 1 < retries:
                await asyncio.sleep(0.5)
    return False


ORDER_TTL_SECONDS = 90 * 24 * 3600


def kv_config():
    import os
    url = os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or ""
    tok = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
    return (url.rstrip("/"), tok) if url and tok else None


async def persist(num: str, text: str, pr: dict, transport=None) -> bool:
    """Write the order to Vercel KV (Upstash Redis, private, token-only) BEFORE emailing.
    Returns False when KV is not configured or the write failed. Records expire after 90 days."""
    cfg = kv_config()
    if not cfg:
        return False
    import json as _json
    url, tok = cfg
    record = _json.dumps({"order": num, "total": pr["total"], "text": text, "ts": int(time.time())}, ensure_ascii=False)
    try:
        async with httpx.AsyncClient(timeout=8, transport=transport) as c:
            r = await c.post(url, headers={"Authorization": f"Bearer {tok}"},
                             json=["SET", f"order:{num}", record, "EX", str(ORDER_TTL_SECONDS)])
        return r.status_code < 300 and "error" not in r.json()
    except Exception:
        return False
