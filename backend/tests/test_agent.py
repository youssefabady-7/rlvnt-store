import asyncio, json, httpx
from app import agent, cart as cartlib, catalog


def test_flat_price():
    assert all(p["price"] == 800 for p in catalog.load_products())


def test_cart_ops():
    c, _ = cartlib.add({}, "rl-001", 2)
    assert c == {"rl-001": 2}
    c, _ = cartlib.remove(c, "rl-001", 1)
    assert c == {"rl-001": 1}
    assert cartlib.summary(c)["total_egp"] == 800
    _, msg = cartlib.add(c, "nope")
    assert msg.startswith("error")


def test_agent_tool_loop(monkeypatch):
    monkeypatch.setattr(agent, "OPENROUTER_API_KEY", "x")
    replies = iter([
        {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "1", "type": "function", "function": {"name": "add_to_cart",
             "arguments": json.dumps({"product_id": "rl-002"})}}]}}]},
        {"choices": [{"message": {"role": "assistant", "content": "Added the tee."}}]},
    ])
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=next(replies)))
    out = asyncio.run(agent.chat([{"role": "user", "content": "add the tee"}], {}, transport))
    assert out["cart"] == {"rl-002": 1} and out["reply"] == "Added the tee."


def test_prompt_has_policies_and_unconfirmed():
    from app.knowledge import system_prompt
    p = system_prompt()
    assert "unworn" in p and "Not confirmed yet" in p and "Egyptian Arabic" in p


def test_set_quantity():
    from app import agent
    cart, out = agent.run_tool("set_quantity", {"product_id": "rl-001", "quantity": 3}, {"rl-001": 1}, [])
    assert cart == {"rl-001": 3}
    cart, out = agent.run_tool("set_quantity", {"product_id": "rl-001", "quantity": 0}, cart, [])
    assert cart == {}


def test_order_pricing_and_email(monkeypatch):
    import asyncio, httpx
    from app import orders
    o = orders.OrderIn(name="Test User", phone="+201000000000", city="Cairo", address="1 Test St",
                       items=[{"id": "rl-001", "size": "m", "qty": 2}])
    pr = orders.price(o)
    assert pr["subtotal"] == 1600 and pr["total"] == 1700
    sent = {}
    monkeypatch.setattr(orders, "RESEND_API_KEY", "k")
    def h(req): sent["b"] = req.content.decode(); return httpx.Response(200, json={"id": "1"})
    s, t, hh = orders.render(o, "RL-1", pr)
    asyncio.run(orders.send_email(s, t, hh, httpx.MockTransport(h)))
    assert "youssefabady6@gmail.com" in sent["b"] and "1700" in sent["b"]
