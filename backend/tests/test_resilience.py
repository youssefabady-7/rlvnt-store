import json, subprocess, sys
from pathlib import Path
from fastapi.testclient import TestClient
from app import main, orders

ORDER = {"name": "Test User", "phone": "01012345678", "city": "Alexandria", "address": "12 Test Street",
         "items": [{"id": "rl-001", "size": "M", "qty": 1}]}


def test_order_falls_back_to_whatsapp_when_email_fails(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("provider down")
    monkeypatch.setattr(orders, "send_email", boom)
    r = TestClient(main.app).post("/api/order", json=ORDER, headers={"x-forwarded-for": "9.9.9.9"})
    d = r.json()
    assert r.status_code == 200 and d["fallback"] and d["confirmed"] is False
    assert d["whatsapp_url"].startswith("https://wa.me/201270383409?text=")
    assert d["order_number"] in d["whatsapp_url"].replace("%20", " ") or d["order_number"]


def test_order_email_ok_has_no_fallback(monkeypatch):
    async def ok(*a, **k):
        return None
    monkeypatch.setattr(orders, "send_email", ok)
    d = TestClient(main.app).post("/api/order", json=ORDER, headers={"x-forwarded-for": "8.8.8.8"}).json()
    assert d["ok"] and "fallback" not in d and d["total"] == 900


def test_health_reports_degraded_not_crash():
    d = TestClient(main.app).get("/health").json()
    assert d["ok"] and d["products"] >= 35 and "checks" in d


def test_catalog_backup_script_verifies_live_catalog():
    root = Path(__file__).resolve().parents[2]
    r = subprocess.run([sys.executable, str(root / "scripts" / "catalog_backup.py"), "verify"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_fallback_log_has_no_pii(monkeypatch, caplog):
    async def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(orders, "send_email", boom)
    with caplog.at_level("ERROR"):
        TestClient(main.app).post("/api/order", json=ORDER, headers={"x-forwarded-for": "7.7.7.7"})
    t = " ".join(r.getMessage() for r in caplog.records)
    assert "ORDER_FALLBACK" in t and "RL-" in t
    for k in ("name", "address", "notes", "city"):
        assert not ORDER.get(k) or str(ORDER[k]) not in t
    assert str(ORDER["phone"]) not in t and orders.mask_phone("01012345678").endswith("678") and "0101" not in orders.mask_phone("01012345678")


def _kv(monkeypatch, status=200, body=None):
    import httpx
    monkeypatch.setenv("KV_REST_API_URL", "https://kv.example.test")
    monkeypatch.setenv("KV_REST_API_TOKEN", "t")
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(status, json=body or {"result": "OK"})
    real = httpx.AsyncClient
    monkeypatch.setattr(orders.httpx, "AsyncClient", lambda **k: real(transport=httpx.MockTransport(handler), **{x: y for x, y in k.items() if x != "transport"}))
    return seen


def test_order_stored_in_kv_before_email_and_confirmed_when_email_fails(monkeypatch):
    seen = _kv(monkeypatch)
    async def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(orders, "send_email", boom)
    d = TestClient(main.app).post("/api/order", json=ORDER, headers={"x-forwarded-for": "6.6.6.6"}).json()
    assert d["confirmed"] is True and "fallback" not in d
    cmd = seen[0]
    assert cmd[0] == "SET" and cmd[1] == "order:" + d["order_number"] and "EX" in cmd


def test_kv_failure_and_email_failure_is_not_confirmed(monkeypatch):
    _kv(monkeypatch, status=500, body={"error": "x"})
    async def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(orders, "send_email", boom)
    d = TestClient(main.app).post("/api/order", json=ORDER, headers={"x-forwarded-for": "5.5.5.5"}).json()
    assert d["confirmed"] is False and d["fallback"]


def test_no_kv_configured_keeps_old_behaviour(monkeypatch):
    for k in ("KV_REST_API_URL", "KV_REST_API_TOKEN", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    import asyncio
    assert asyncio.run(orders.persist("RL-1", "t", {"total": 1})) is False
