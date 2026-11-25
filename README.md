# RLVNT

English-only streetwear site. Every product is 800 EGP. A chat agent backed by a real LLM
(OpenRouter free model, tool calling) can recommend products and add/remove cart items.

- `backend/` FastAPI. Deploy on Render (`render.yaml`). Env: `OPENROUTER_API_KEY`, `ALLOWED_ORIGINS`.
- `public/` static site and `api/index.py` serverless entry: deploy the repo root on Vercel (one project). Set env `OPENROUTER_API_KEY`.
- Products: edit `backend/app/products.json` (price is forced to 800 in code).

Run locally: `cd backend && pip install -r requirements.txt && OPENROUTER_API_KEY=... uvicorn app.main:app`,
then open `public/index.html`. Tests: `cd backend && pytest`.

Fixes vs Brand-mind2: the real LLM is actually called; one config source (no threshold mismatch);
errors are logged and returned, never swallowed; dependencies pinned in one requirements file;
README matches the file layout.
