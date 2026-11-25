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
