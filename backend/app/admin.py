"""Password-protected admin API. Server-side auth only.

- Password: only a salted PBKDF2 hash lives in env (ADMIN_PASSWORD_HASH). Nothing secret is in client code.
- Session: random token in an httpOnly, SameSite=Strict, Secure cookie. Only its SHA-256 is stored (KV, 8 h).
- CSRF: every state-changing call needs the per-session X-CSRF-Token header, plus an Origin/Host match.
- Brute force: 5 failed logins per IP in 15 min locks that IP for 15 min; 25 failures overall per hour
  lock all logins for the rest of that hour. Failures also cost 1 second.
- Data lives in Upstash KV: catalog:products, settings, img:<id>, order:<num>, orderstate:<num>.
"""
import unicodedata
import base64, binascii, hashlib, hmac, json, os, re, secrets, time
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel, Field

from . import catalog, kv, settings
from .config import SIZES

router = APIRouter()
public_router = APIRouter()

COOKIE = "rl_admin"
SESSION_SECONDS = 8 * 3600
MAX_IP_FAILS, IP_WINDOW = 5, 900
MAX_ALL_FAILS, ALL_WINDOW = 25, 3600
MAX_IMAGE_BYTES = 600_000
_mem_fail: dict = {}  # used only when KV is down (login is refused anyway), kept for tests


# ---------- password hashing ----------
def _norm(p: str) -> str:
    return unicodedata.normalize("NFKC", p).strip()


def make_hash(password: str, iterations: int = 600_000) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", _norm(password).encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def check_password(password: str, stored: str) -> bool:
    try:
        algo, it, salt, dk = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", _norm(password).encode(), base64.b64decode(salt), int(it))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except (ValueError, binascii.Error):
        return False


def _enabled() -> bool:
    return bool(os.getenv("ADMIN_PASSWORD_HASH")) and kv.available()


def _ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "x")).split(",")[0].strip()


def _h(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()[:24]


# ---------- brute force protection ----------
def _locked(ip: str) -> int:
    """Seconds left on a lock, 0 if not locked."""
    for key in (f"admin:lock:ip:{_h(ip)}", "admin:lock:all"):
        ttl = kv.cmd("TTL", key)
        if isinstance(ttl, int) and ttl > 0:
            return ttl
    return 0


def _fail(ip: str) -> None:
    n = int(kv.cmd("INCR", f"admin:f:ip:{_h(ip)}"))
    if n == 1:
        kv.cmd("EXPIRE", f"admin:f:ip:{_h(ip)}", IP_WINDOW)
    if n >= MAX_IP_FAILS:
        kv.cmd("SET", f"admin:lock:ip:{_h(ip)}", "1", "EX", IP_WINDOW)
    m = int(kv.cmd("INCR", "admin:f:all"))
    if m == 1:
        kv.cmd("EXPIRE", "admin:f:all", ALL_WINDOW)
    if m >= MAX_ALL_FAILS:
        kv.cmd("SET", "admin:lock:all", "1", "EX", ALL_WINDOW)


# ---------- sessions ----------
def _secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def session(request: Request) -> dict:
    if not _enabled():
        raise HTTPException(status_code=503, detail="Admin is not configured")
    tok = request.cookies.get(COOKIE, "")
    if not tok:
        raise HTTPException(status_code=401, detail="Not signed in")
    raw = kv.cmd("GET", f"admin:s:{_h(tok)}")
    if not raw:
        raise HTTPException(status_code=401, detail="Session expired")
    return json.loads(raw)


def csrf_guard(request: Request, s: dict = Depends(session)) -> dict:
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.headers.get("x-csrf-token", "")
        if not sent or not hmac.compare_digest(sent, s["csrf"]):
            raise HTTPException(status_code=403, detail="Bad CSRF token")
        origin = request.headers.get("origin")
        if origin:
            host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
            if origin.split("://", 1)[-1] != host:
                raise HTTPException(status_code=403, detail="Bad origin")
    return s


def _nostore(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response):
    _nostore(response)
    if not _enabled():
        raise HTTPException(status_code=503, detail="Admin is not configured")
    ip = _ip(request)
    left = _locked(ip)
    if left:
        raise HTTPException(status_code=429, detail=f"Too many attempts. Try again in {max(1, left // 60)} min.")
    if not check_password(body.password, os.getenv("ADMIN_PASSWORD_HASH", "")):
        _fail(ip)
        time.sleep(1)
        raise HTTPException(status_code=401, detail="Wrong password")
    kv.cmd("DEL", f"admin:f:ip:{_h(ip)}")
    tok, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    kv.cmd("SET", f"admin:s:{_h(tok)}", json.dumps({"csrf": csrf, "t": int(time.time())}), "EX", SESSION_SECONDS)
    response.set_cookie(COOKIE, tok, max_age=SESSION_SECONDS, httponly=True, secure=_secure(request), samesite="strict", path="/api/admin")
    return {"ok": True, "csrf": csrf}


@router.post("/logout")
def logout(request: Request, response: Response, s: dict = Depends(csrf_guard)):
    _nostore(response)
    kv.cmd("DEL", f"admin:s:{_h(request.cookies.get(COOKIE, ''))}")
    response.delete_cookie(COOKIE, path="/api/admin")
    return {"ok": True}


@router.get("/me")
def me(response: Response, s: dict = Depends(session)):
    _nostore(response)
    return {"ok": True, "csrf": s["csrf"], "sizes": SIZES}


@router.get("/status")
def status(response: Response):
    """Tells the login page whether admin is configured. No secrets."""
    _nostore(response)
    return {"enabled": _enabled()}


# ---------- products ----------
CAT_RE = re.compile(r"^[a-z0-9][a-z0-9 -]{1,29}$")
IMG_RE = re.compile(r"^(images/[A-Za-z0-9._-]{1,80}|/api/img/[a-f0-9]{16,40})$")


class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    price: int = Field(ge=1, le=100000)
    category: str
    sizes: list[str] = Field(default_factory=lambda: list(SIZES), min_length=1)
    description: str = Field(default="", max_length=600)
    tags: list[str] = Field(default_factory=list, max_length=15)
    image: str
    images: list[str] = Field(default_factory=list, max_length=8)
    hidden: bool = False
    sold_out: bool = False


def _validate_product(p: ProductIn) -> dict:
    d = p.model_dump()
    d["category"] = d["category"].strip().lower()
    if not CAT_RE.match(d["category"]):
        raise HTTPException(422, "category must be 2-30 letters, numbers, spaces or dashes")
    bad = [s for s in d["sizes"] if s not in SIZES]
    if bad:
        raise HTTPException(422, f"unknown sizes: {bad}")
    d["sizes"] = [s for s in SIZES if s in d["sizes"]]
    d["tags"] = [t.strip().lower()[:30] for t in d["tags"] if t.strip()]
    d["name"] = d["name"].strip()
    for u in [d["image"], *d["images"]]:
        if not IMG_RE.match(u):
            raise HTTPException(422, "image must be an uploaded image or a built-in image path")
    if len(d["images"]) < 2:
        d.pop("images")  # a single image needs no gallery
    return d


def _save_catalog(items: list[dict]) -> None:
    prev = kv.cmd("GET", "catalog:products")
    if prev:
        kv.cmd("SET", "catalog:prev", prev)  # one-step undo
    kv.cmd("SET", "catalog:products", json.dumps(items, ensure_ascii=False))
    catalog.set_cache(items)


def _current() -> list[dict]:
    return [dict(p) for p in catalog.load_all(force=True)]


def _clean_store(p: dict) -> dict:
    return {k: v for k, v in p.items() if v is not None}


def _next_id(items: list[dict]) -> str:
    nums = [int(m.group(1)) for p in items if (m := re.fullmatch(r"rl-(\d+)", p["id"]))]
    return f"rl-{(max(nums) + 1 if nums else 1):03d}"


@router.get("/products")
def list_products(response: Response, s: dict = Depends(session)):
    _nostore(response)
    return {"products": _current()}


@router.post("/products")
def add_product(body: ProductIn, response: Response, s: dict = Depends(csrf_guard)):
    _nostore(response)
    items = _current()
    p = {"id": _next_id(items), **_validate_product(body)}
    items.insert(0, p)  # new pieces show first
    _save_catalog(items)
    return {"product": p}


@router.put("/products/{pid}")
def edit_product(pid: str, body: ProductIn, response: Response, s: dict = Depends(csrf_guard)):
    _nostore(response)
    items = _current()
    idx = next((i for i, p in enumerate(items) if p["id"] == pid), None)
    if idx is None:
        raise HTTPException(404, "No such product")
    items[idx] = {"id": pid, **_validate_product(body)}
    _save_catalog(items)
    return {"product": items[idx]}


@router.delete("/products/{pid}")
def delete_product(pid: str, response: Response, s: dict = Depends(csrf_guard)):
    _nostore(response)
    items = _current()
    if not any(p["id"] == pid for p in items):
        raise HTTPException(404, "No such product")
    _save_catalog([p for p in items if p["id"] != pid])
    return {"ok": True}


class ReorderIn(BaseModel):
    ids: list[str] = Field(max_length=500)


@router.post("/products-reorder")
def reorder(body: ReorderIn, response: Response, s: dict = Depends(csrf_guard)):
    _nostore(response)
    items = _current()
    by = {p["id"]: p for p in items}
    if set(body.ids) != set(by) or len(body.ids) != len(by):
        raise HTTPException(422, "ids must list every product exactly once")
    _save_catalog([by[i] for i in body.ids])
    return {"ok": True}


@router.post("/revert")
def revert(response: Response, s: dict = Depends(csrf_guard)):
    """Undo the last catalog change (one step)."""
    _nostore(response)
    prev = kv.cmd("GET", "catalog:prev")
    if not prev:
        raise HTTPException(404, "Nothing to undo")
    items = json.loads(prev)
    _save_catalog(items)
    return {"ok": True, "count": len(items)}


# ---------- images (stored in KV, served by /api/img/<id>) ----------
class ImageIn(BaseModel):
    data: str = Field(max_length=900_000)  # base64 of the resized image


MAGIC = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG": "image/png", b"RIFF": "image/webp"}


def _sniff(raw: bytes) -> str | None:
    for m, t in MAGIC.items():
        if raw.startswith(m):
            if t == "image/webp" and raw[8:12] != b"WEBP":
                return None
            return t
    return None


@router.post("/image")
def upload_image(body: ImageIn, response: Response, s: dict = Depends(csrf_guard)):
    _nostore(response)
    b64 = body.data.split(",", 1)[-1]
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "Not a valid image")
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image too large (max 600 KB after resize)")
    mime = _sniff(raw)
    if not mime:
        raise HTTPException(422, "Only JPEG, PNG or WebP images are allowed")
    iid = secrets.token_hex(10)
    kv.cmd("SET", f"img:{iid}", json.dumps({"m": mime, "d": b64}))
    return {"url": f"/api/img/{iid}"}


@public_router.get("/img/{iid}")
def get_image(iid: str):
    if not re.fullmatch(r"[a-f0-9]{16,40}", iid) or not kv.available():
        raise HTTPException(404, "Not found")
    try:
        raw = kv.cmd("GET", f"img:{iid}")
    except kv.KVError:
        raise HTTPException(503, "Image store unavailable")
    if not raw:
        raise HTTPException(404, "Not found")
    rec = json.loads(raw)
    return RawResponse(content=base64.b64decode(rec["d"]), media_type=rec["m"],
                       headers={"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"})


# ---------- settings ----------
@router.get("/settings")
def get_settings(response: Response, s: dict = Depends(session)):
    _nostore(response)
    return {"settings": settings.load(force=True)}


@router.put("/settings")
def put_settings(body: dict, response: Response, s: dict = Depends(csrf_guard)):
    _nostore(response)
    try:
        return {"settings": settings.save(body)}
    except ValueError as e:
        raise HTTPException(422, str(e))


# ---------- orders ----------
@router.get("/orders")
def orders_list(response: Response, s: dict = Depends(session)):
    _nostore(response)
    keys, cursor = [], "0"
    for _ in range(30):
        res = kv.cmd("SCAN", cursor, "MATCH", "order:*", "COUNT", 200)
        cursor, batch = str(res[0]), res[1]
        keys += batch
        if cursor == "0" or len(keys) >= 500:
            break
    out = []
    if keys:
        vals = kv.cmd("MGET", *keys[:500])
        states = kv.cmd("MGET", *[k.replace("order:", "orderstate:", 1) for k in keys[:500]])
        for k, v, st in zip(keys, vals, states):
            try:
                rec = json.loads(v)
            except (TypeError, ValueError):
                continue
            rec["status"] = st or "new"
            out.append(rec)
    out.sort(key=lambda r: r.get("ts", 0), reverse=True)
    return {"orders": out[:100], "total": len(out)}


class OrderState(BaseModel):
    status: str = Field(pattern="^(new|done)$")


@router.put("/orders/{num}")
def order_state(num: str, body: OrderState, response: Response, s: dict = Depends(csrf_guard)):
    _nostore(response)
    if not re.fullmatch(r"RL-[0-9A-Z]{8,16}", num):
        raise HTTPException(422, "bad order number")
    if body.status == "done":
        kv.cmd("SET", f"orderstate:{num}", "done", "EX", 90 * 24 * 3600)
    else:
        kv.cmd("DEL", f"orderstate:{num}")
    return {"ok": True}


# ---------- backup ----------
@router.get("/export")
def export(response: Response, s: dict = Depends(session)):
    _nostore(response)
    return {"version": 1, "exported_at": int(time.time()), "settings": settings.load(force=True), "products": _current()}


class ImportIn(BaseModel):
    settings: dict
    products: list[dict] = Field(max_length=500)


@router.post("/import")
def import_backup(body: ImportIn, response: Response, s: dict = Depends(csrf_guard)):
    _nostore(response)
    try:
        st = settings.validate(body.settings)
    except ValueError as e:
        raise HTTPException(422, str(e))
    items = []
    for raw in body.products:
        try:
            pid = str(raw.get("id", ""))
            if not re.fullmatch(r"rl-\d{3,}", pid):
                raise ValueError("bad id")
            d = _validate_product(ProductIn(**{k: v for k, v in raw.items() if k != "id"}))
            items.append({"id": pid, **d})
        except Exception as e:
            raise HTTPException(422, f"Invalid product in backup: {str(e)[:120]}")
    if len({p["id"] for p in items}) != len(items):
        raise HTTPException(422, "Duplicate product ids in backup")
    _save_catalog(items)
    settings.save(st)
    return {"ok": True, "products": len(items)}
