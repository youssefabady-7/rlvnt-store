import base64, json, time, fnmatch
import pytest
from fastapi.testclient import TestClient
from app import admin, catalog, cart as cartlib, guard, kv, main, orders, settings
from app.knowledge import system_prompt

PW = "Correct-Horse-Battery-9!"


class FakeKV:
    def __init__(self):
        self.d, self.exp = {}, {}

    def _alive(self, k):
        if k in self.exp and self.exp[k] <= time.time():
            self.d.pop(k, None); self.exp.pop(k, None)
        return k in self.d

    def __call__(self, *a, timeout=4.0):
        op, args = a[0].upper(), [str(x) for x in a[1:]]
        if op == "GET": return self.d.get(args[0]) if self._alive(args[0]) else None
        if op == "SET":
            self.d[args[0]] = args[1]; self.exp.pop(args[0], None)
            if len(args) >= 4 and args[2].upper() == "EX": self.exp[args[0]] = time.time() + int(args[3])
            return "OK"
        if op == "DEL": return int(self.d.pop(args[0], None) is not None)
        if op == "INCR":
            self._alive(args[0]); self.d[args[0]] = str(int(self.d.get(args[0], 0)) + 1); return int(self.d[args[0]])
        if op == "EXPIRE": self.exp[args[0]] = time.time() + int(args[1]); return 1
        if op == "TTL":
            if not self._alive(args[0]): return -2
            return int(self.exp[args[0]] - time.time()) if args[0] in self.exp else -1
        if op == "SCAN":
            pat = args[args.index("MATCH") + 1]
            return ["0", [k for k in list(self.d) if self._alive(k) and fnmatch.fnmatch(k, pat)]]
        if op == "MGET": return [self.d.get(k) if self._alive(k) else None for k in args]
        raise AssertionError(op)


@pytest.fixture()
def env(monkeypatch):
    fk = FakeKV()
    monkeypatch.setattr(kv, "cmd", fk)
    monkeypatch.setattr(kv, "kv_config", lambda: ("https://kv.test", "t"))
    monkeypatch.setattr(kv, "available", lambda: True)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", admin.make_hash(PW, iterations=1000))
    monkeypatch.setattr(admin.time, "sleep", lambda s: None)
    catalog._cache.update(t=0.0, v=None); settings._cache.update(t=0.0, v=None)
    return fk


def client():
    return TestClient(main.app, base_url="https://testserver")


def login(c, pw=PW, ip="1.1.1.1"):
    return c.post("/api/admin/login", json={"password": pw}, headers={"x-forwarded-for": ip})


def authed():
    c = client(); r = login(c); assert r.status_code == 200
    return c, {"X-CSRF-Token": r.json()["csrf"]}


PROD = {"name": "Test Tee", "price": 650, "category": "tees", "sizes": ["M", "L"], "description": "d", "tags": ["x"], "image": "images/c-004.jpg"}


def test_login_cookie_flags_and_wrong_password(env):
    c = client()
    assert c.get("/api/admin/products").status_code == 401
    assert login(c, "nope").status_code == 401
    r = login(c)
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "secure" in sc and "samesite=strict" in sc and "path=/api/admin" in sc
    assert PW not in r.text and "ADMIN_PASSWORD_HASH" not in r.text
    assert r.headers["cache-control"] == "no-store"
    assert c.get("/api/admin/products").status_code == 200


def test_lockout_after_five_failures_and_global_lock(env):
    c = client()
    for _ in range(5):
        assert login(c, "bad", ip="9.9.9.9").status_code == 401
    r = login(c, PW, ip="9.9.9.9")           # even the right password is refused while locked
    assert r.status_code == 429
    assert login(c, PW, ip="8.8.8.8").status_code == 200   # other IP unaffected
    c2 = client()
    for i in range(25):                       # distributed guessing hits the global lock
        login(c2, "bad", ip=f"7.7.{i}.1")
    assert login(client(), PW, ip="6.6.6.6").status_code == 429


def test_csrf_and_origin_required_for_changes(env):
    c, h = authed()
    assert c.post("/api/admin/products", json=PROD).status_code == 403
    assert c.post("/api/admin/products", json=PROD, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert c.post("/api/admin/products", json=PROD, headers={**h, "Origin": "https://evil.example"}).status_code == 403
    assert c.post("/api/admin/products", json=PROD, headers={**h, "Origin": "https://testserver"}).status_code == 200


def test_not_configured_means_admin_off(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    assert client().post("/api/admin/login", json={"password": "x"}).status_code == 503


def test_product_crud_price_hide_soldout_reorder_and_public_view(env):
    c, h = authed()
    pub0 = c.get("/api/products").json()
    assert len(pub0["products"]) == 35
    p = c.post("/api/admin/products", json=PROD, headers=h).json()["product"]
    assert p["id"] == "rl-036"
    pub = c.get("/api/products").json()["products"]
    assert pub[0]["id"] == "rl-036" and pub[0]["price"] == 650 and pub[0]["sizes"] == ["M", "L"]
    # price flows into orders, chatbot prompt and guard
    o = orders.OrderIn(name="Test User", phone="01012345678", city="Cairo", address="1 Test St", items=[{"id": "rl-036", "size": "M", "qty": 2}])
    assert orders.price(o)["subtotal"] == 1300
    with pytest.raises(ValueError):
        orders.price(orders.OrderIn(name="Test User", phone="01012345678", city="Cairo", address="1 Test St", items=[{"id": "rl-036", "size": "S", "qty": 1}]))
    assert "rl-036 | Test Tee | 650 |" in system_prompt()
    assert guard.check("The Test Tee is 650 EGP, total 750 EGP") == [] and guard.check("It is 640 EGP") != []
    # hide
    c.put("/api/admin/products/rl-036", json={**PROD, "hidden": True}, headers=h)
    assert all(x["id"] != "rl-036" for x in c.get("/api/products").json()["products"])
    assert any(x["id"] == "rl-036" for x in c.get("/api/admin/products").json()["products"])
    # sold out cannot be added or ordered
    c.put("/api/admin/products/rl-036", json={**PROD, "sold_out": True}, headers=h)
    assert cartlib.add({}, "rl-036")[1].startswith("error") and "SOLD OUT" in system_prompt()
    with pytest.raises(ValueError):
        orders.price(o)
    # reorder
    ids = [x["id"] for x in c.get("/api/admin/products").json()["products"]]
    c.post("/api/admin/products-reorder", json={"ids": ids[::-1]}, headers=h)
    assert c.get("/api/products").json()["products"][0]["id"] == ids[::-1][0] or ids[::-1][0] == "rl-036"
    assert c.post("/api/admin/products-reorder", json={"ids": ids[:3]}, headers=h).status_code == 422
    # delete + undo
    assert c.delete("/api/admin/products/rl-036", headers=h).status_code == 200
    assert not any(x["id"] == "rl-036" for x in c.get("/api/admin/products").json()["products"])
    assert c.post("/api/admin/revert", headers=h).status_code == 200
    assert any(x["id"] == "rl-036" for x in c.get("/api/admin/products").json()["products"])


def test_product_validation(env):
    c, h = authed()
    for bad in ({**PROD, "price": 0}, {**PROD, "sizes": ["XS"]}, {**PROD, "image": "http://evil/x.jpg"}, {**PROD, "image": "../../etc/passwd"}, {**PROD, "name": "x"}, {**PROD, "category": "Bad/Cat"}):
        assert c.post("/api/admin/products", json=bad, headers=h).status_code == 422, bad


JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200


def test_image_upload_validation_and_public_serving(env):
    c, h = authed()
    r = c.post("/api/admin/image", json={"data": base64.b64encode(JPEG).decode()}, headers=h)
    url = r.json()["url"]
    g = client().get(url)                    # public, no cookie
    assert g.status_code == 200 and g.headers["content-type"] == "image/jpeg" and g.content == JPEG
    assert "immutable" in g.headers["cache-control"]
    assert c.post("/api/admin/image", json={"data": base64.b64encode(b"<svg onload=alert(1)>").decode()}, headers=h).status_code == 422
    assert c.post("/api/admin/image", json={"data": base64.b64encode(b"\xff\xd8\xff" + b"0" * 700_000).decode()}, headers=h).status_code in (413, 422)
    assert client().get("/api/img/../../etc").status_code in (404, 422)
    p = c.post("/api/admin/products", json={**PROD, "image": url, "images": [url, "images/c-004.jpg"]}, headers=h)
    assert p.status_code == 200 and p.json()["product"]["images"][0] == url


def test_settings_flow_into_site_orders_and_chatbot(env):
    c, h = authed()
    r = c.put("/api/admin/settings", json={**c.get("/api/admin/settings").json()["settings"], "shipping_fee": 60, "announcement": "Winter sale soon", "support_phone": "+20111222333", "whatsapp_number": "20111222333", "order_email": "owner@example.com", "delivery_text": "Delivery in 2 days now", "chatbot_enabled": True}, headers=h)
    assert r.status_code == 200
    pub = c.get("/api/products").json()
    assert pub["shipping"] == 60 and pub["settings"]["announcement"] == "Winter sale soon" and "order_email" not in pub["settings"]
    o = orders.OrderIn(name="Test User", phone="01012345678", city="Cairo", address="1 Test St", items=[{"id": "rl-001", "size": "M", "qty": 1}])
    assert orders.price(o)["total"] == 860
    p = system_prompt()
    assert "60 EGP" in p and "Delivery in 2 days now" in p and "+20111222333" in p
    assert orders.whatsapp_link("hi").startswith("https://wa.me/20111222333")
    assert c.put("/api/admin/settings", json={"shipping_fee": -5}, headers=h).status_code == 422
    c.put("/api/admin/settings", json={**settings.load(), "chatbot_enabled": False}, headers=h)
    assert c.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}], "cart": {}}).status_code == 503


def test_orders_listing_and_state(env):
    c, h = authed()
    env("SET", "order:RL-12345678ABC", json.dumps({"order": "RL-12345678ABC", "total": 900, "text": "t", "ts": 5}))
    env("SET", "order:RL-12345679XYZ", json.dumps({"order": "RL-12345679XYZ", "total": 1700, "text": "t2", "ts": 9}))
    o = c.get("/api/admin/orders").json()
    assert [x["order"] for x in o["orders"]] == ["RL-12345679XYZ", "RL-12345678ABC"] and o["orders"][0]["status"] == "new"
    c.put("/api/admin/orders/RL-12345679XYZ", json={"status": "done"}, headers=h)
    assert c.get("/api/admin/orders").json()["orders"][0]["status"] == "done"
    assert c.put("/api/admin/orders/bad", json={"status": "done"}, headers=h).status_code == 422


def test_export_import_roundtrip_and_rejects_bad_backup(env):
    c, h = authed()
    ex = c.get("/api/admin/export").json()
    assert len(ex["products"]) == 35
    assert c.post("/api/admin/import", json=ex, headers=h).status_code == 200
    bad = {**ex, "products": ex["products"][:2] + [{"id": "rl-999", "name": "x"}]}
    assert c.post("/api/admin/import", json=bad, headers=h).status_code == 422
    assert len(c.get("/api/admin/products").json()["products"]) == 35


def test_logout_kills_session(env):
    c, h = authed()
    assert c.post("/api/admin/logout", headers=h).status_code == 200
    c.cookies.clear()
    assert c.get("/api/admin/products").status_code == 401
