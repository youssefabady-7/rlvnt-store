import asyncio, json, time, httpx
from app import agent, config


def _setup(monkeypatch, gemini=True, groq=True):
    agent._cooldown.clear()
    monkeypatch.setattr(agent, "OPENROUTER_API_KEY", "or")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "g" if gemini else "")
    monkeypatch.setattr(config, "GROQ_API_KEY", "q" if groq else "")


def _transport(behaviour, log):
    """behaviour: host -> (status, content). Records (host, system prompt) for every call."""
    def h(req):
        body = json.loads(req.content)
        log.append((req.url.host, body["messages"][0]["content"], body.get("temperature")))
        status, content = behaviour[req.url.host]
        if status != 200:
            return httpx.Response(status, text=content)
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})
    return httpx.MockTransport(h)


def _chat(t, msg="hi"):
    return asyncio.run(agent.chat([{"role": "user", "content": msg}], {}, t))


def test_falls_through_openrouter_429_to_gemini_and_sets_cooldown(monkeypatch):
    _setup(monkeypatch); log = []
    t = _transport({"openrouter.ai": (429, "Rate limit exceeded: free-models-per-day"),
                    "generativelanguage.googleapis.com": (200, "gemini"), "api.groq.com": (200, "Hey from groq")}, log)
    assert _chat(t)["reply"] == "Hey from groq"
    assert agent._cooldown["openrouter"] - time.monotonic() > 1000  # daily quota -> long cooldown
    log.clear()
    assert _chat(t)["reply"] == "Hey from groq"
    assert all(h != "openrouter.ai" for h, _, _ in log)              # skipped while cooling down


def test_same_grounded_prompt_and_temperature_on_every_provider(monkeypatch):
    _setup(monkeypatch); log = []
    t = _transport({"openrouter.ai": (500, "x"), "api.groq.com": (429, "slow down"), "generativelanguage.googleapis.com": (200, "From gemini")}, log)
    assert _chat(t)["reply"] == "From gemini"
    assert {h for h, _, _ in log} >= {"openrouter.ai", "generativelanguage.googleapis.com", "api.groq.com"}
    prompts = {p for _, p, _ in log}
    assert len(prompts) == 1 and "CATALOG" in next(iter(prompts)) and all(tp == 0.2 for _, _, tp in log)


def test_guard_runs_on_fallback_provider_output(monkeypatch):
    _setup(monkeypatch); log = []
    t = _transport({"openrouter.ai": (429, "x"), "api.groq.com": (200, "Yes! 40% off today, code SAVE40"),
                    "generativelanguage.googleapis.com": (200, "x")}, log)
    out = _chat(t, "any discount?")
    assert "40%" not in out["reply"] and "WhatsApp" in out["reply"]


def test_all_providers_down_raises_and_no_keys_is_noop(monkeypatch):
    _setup(monkeypatch); log = []
    t = _transport({"openrouter.ai": (500, "x"), "generativelanguage.googleapis.com": (503, "x"), "api.groq.com": (429, "x")}, log)
    try:
        _chat(t); assert False
    except RuntimeError as e:
        assert "all providers" in str(e)
    _setup(monkeypatch, gemini=False, groq=False)
    assert [p["name"] for p in agent.providers()] == ["openrouter"]   # current behaviour until keys arrive


def test_chain_order_is_openrouter_groq_gemini(monkeypatch):
    _setup(monkeypatch)
    assert [p["name"] for p in agent.providers()] == ["openrouter", "groq", "gemini"]


def test_bad_key_is_parked(monkeypatch):
    _setup(monkeypatch); log = []
    t = _transport({"openrouter.ai": (401, "bad key"), "api.groq.com": (200, "ok groq"), "generativelanguage.googleapis.com": (200, "x")}, log)
    assert _chat(t)["reply"] == "ok groq" and agent._cooldown["openrouter"] - time.monotonic() > 3000
