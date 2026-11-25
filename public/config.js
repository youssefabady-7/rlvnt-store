// Same-origin on Vercel (API lives at /api). For local dev use http://localhost:8000
window.RLVNT_API = location.hostname === "localhost" || location.protocol === "file:" ? "http://localhost:8000" : "";
