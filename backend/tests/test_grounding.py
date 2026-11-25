import asyncio, json, httpx
from app import agent, guard
from app.knowledge import system_prompt, live_context


def _llm(*contents):
    it = iter(contents)
    def h(req):
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": next(it)}}]})
    return httpx.MockTransport(h)


def _run(user, transport, cart=None, viewing=""):
    agent.OPENROUTER_API_KEY = "x"
    return asyncio.run(agent.chat([{"role": "user", "content": user}], cart or {}, transport, viewing=viewing))


def test_guard_flags_bad_prices_discounts_and_products():
    assert guard.check("It is 800 EGP, shipping 100 EGP, total 900 EGP.") == []
    assert guard.check("إجمالي 1700 جنيه") == []
    assert guard.check("Only 650 EGP today") != []
    assert guard.check("Use code SAVE for 20% off") != []
    assert guard.check("There is no discount, flat 800 EGP.") == []
    assert guard.check("Try the **Galaxy Hoodie Pro**") != []
    assert guard.check("Try the **Fight Club** hoodie") == []
    assert guard.check("see rl-999") != []


def test_fake_discount_gets_corrected_then_safe():
    # first reply hallucinates, the corrective retry is clean
    out = _run("any discount?", _llm("Yes! 30% off with code RLVNT30", "No discounts right now, every piece is a flat 800 EGP."))
    assert "30%" not in out["reply"] and "800" in out["reply"]
    # model keeps hallucinating -> safe fallback, never the bad text
    out = _run("any discount?", _llm("20% off today", "Still 20% off today"))
    assert "20%" not in out["reply"] and "WhatsApp" in out["reply"]
    out = _run("في خصم؟", _llm("خصم 50%", "خصم 50%"))
    assert "50%" not in out["reply"] and "واتساب" in out["reply"]


def test_fake_product_not_passed_through():
    out = _run("do you have the Nike Air Jordan hoodie?", _llm("Yes, **Nike Air Jordan Hoodie** is 900 EGP", "Yes **Nike Air Jordan Hoodie** 900 EGP"))
    assert "Nike" not in out["reply"]


def test_bad_link_tokens_removed_good_kept():
    out = _run("show me one", _llm("Check **Fight Club** [[rl-009]] and [[rl-777]]", "Check **Fight Club** [[rl-009]]"))
    assert "[[rl-009]]" in out["reply"] and "rl-777" not in out["reply"]


def test_prompt_is_grounded_and_aware():
    p = system_prompt({"rl-001": 2}, "rl-009")
    assert "Real Madrid Los Blancos Set" in p and "Fight Club" in p      # live catalog injected
    assert "2 x Real Madrid Los Blancos Set" in p and "1700 EGP" in p     # cart aware
    assert "currently viewing: " in p and "rl-009" in p
    assert "NO discounts" in p and "Egyptian Arabic" in p and "[[rl-009]]" in p


def test_temperature_is_low(monkeypatch):
    seen = {}
    def h(req):
        seen.update(json.loads(req.content)); return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "Hi"}}]})
    _run("hi", httpx.MockTransport(h))
    assert seen["temperature"] <= 0.3


def test_guard_negation_and_typo():
    assert guard.check("Sorry, the code RLVNT30 isn't valid and there is no 30% off.") == []
    assert guard.check("It costs 800 EPG") != []


def test_language_hint_and_stray_script_and_shipping_unconfirmed():
    p = system_prompt({}, "", "Do you have hoodies?")
    assert "ENGLISH only" in p
    assert "Egyptian Arabic (Masri" in system_prompt({}, "", "عايز هودي")
    assert "shipping outside Egypt" in p
    assert guard.check("الدロップ الحالي") != []
