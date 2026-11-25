"""Tiny sync client for the Upstash REST API (Vercel KV). Private: needs the token from env, never exposed."""
import httpx
import os


def kv_config():
    url = os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or ""
    tok = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
    return (url.rstrip("/"), tok) if url and tok else None


class KVError(RuntimeError):
    pass


def available() -> bool:
    return kv_config() is not None


def cmd(*args, timeout: float = 4.0):
    cfg = kv_config()
    if not cfg:
        raise KVError("KV not configured")
    url, tok = cfg
    try:
        r = httpx.post(url, headers={"Authorization": f"Bearer {tok}"}, json=[str(a) for a in args], timeout=timeout)
        data = r.json()
    except Exception as e:
        raise KVError(f"KV unreachable: {type(e).__name__}") from e
    if r.status_code >= 300 or "error" in data:
        raise KVError(f"KV error {r.status_code}")
    return data.get("result")
