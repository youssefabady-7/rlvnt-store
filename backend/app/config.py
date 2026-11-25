import os

PRICE_EGP = 800  # flat price for every product
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
# Free model with tool calling. Override with OPENROUTER_MODEL; fallbacks are tried in order.
MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
FALLBACK_MODELS = [m for m in os.getenv("OPENROUTER_FALLBACKS", "").split(",") if m]
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
ALLOWED_ORIGINS = [o for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o]
MAX_TOOL_STEPS = 5
