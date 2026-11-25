import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))
from app.main import app  # noqa: E402,F401  (Vercel serves this ASGI app)
