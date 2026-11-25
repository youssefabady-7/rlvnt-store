"""Vercel entrypoint: FastAPI app (API under /api). The static site in public/ is served by Vercel's CDN."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "backend"))
from app.main import app  # noqa: E402,F401
