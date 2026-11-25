import os

PRICE_EGP = 800  # flat price for every product
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
# Free model with tool calling. Override with OPENROUTER_MODEL; fallbacks are tried in order.
MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
FALLBACK_MODELS = [m for m in os.getenv("OPENROUTER_FALLBACKS", "google/gemma-4-31b-it:free,nvidia/nemotron-3-ultra-550b-a55b:free,google/gemma-4-26b-a4b-it:free").split(",") if m]
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
ALLOWED_ORIGINS = [o for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o]
MAX_TOOL_STEPS = 5

SHIPPING_EGP = 100
ORDER_EMAIL = os.getenv("ORDER_EMAIL", "youssefabady6@gmail.com")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
ORDER_FROM = os.getenv("ORDER_FROM", "RLVNT Orders <onboarding@resend.dev>")
SIZES = ["S", "M", "L", "XL", "XXL"]
SUPPORT_EMAIL = "youssefabady6@gmail.com"
SUPPORT_PHONE = "+201270383409"
