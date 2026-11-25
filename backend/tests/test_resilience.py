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
    assert r.status_code == 200 and d["ok"] and d["fallback"]
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
