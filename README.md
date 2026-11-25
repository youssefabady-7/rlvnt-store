<div align="center">

<img src="public/images/logo.png" alt="RLVNT logo" width="140">

# RLVNT

**Wear what's relevant.** A streetwear store with a real AI shopping assistant, a live admin panel and cash-on-delivery checkout.

[![Live site](https://img.shields.io/badge/live-rlvnt--store.vercel.app-8F1D1D?style=for-the-badge)](https://rlvnt-store.vercel.app)
![Python](https://img.shields.io/badge/python-3.x-111111?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-8F1D1D?style=flat-square&logo=fastapi&logoColor=white)
![Vercel](https://img.shields.io/badge/deploy-Vercel-111111?style=flat-square&logo=vercel&logoColor=white)
![Upstash](https://img.shields.io/badge/data-Upstash%20Redis-8F1D1D?style=flat-square&logo=redis&logoColor=white)
![Tests](https://img.shields.io/badge/tests-39%20passing-2e7d32?style=flat-square)
![Frontend](https://img.shields.io/badge/frontend-vanilla%20JS-111111?style=flat-square&logo=javascript&logoColor=white)

<img src="docs/screenshots/hero-store.png" alt="RLVNT storefront" width="900">

</div>

---

## Contents

[Features](#features) · [Screenshots](#screenshots) · [Architecture](#architecture) · [Flows](#flows) · [Data model](#data-model) · [Tech stack](#tech-stack) · [Project structure](#project-structure) · [API](#api) · [Run locally](#run-locally) · [Environment variables](#environment-variables) · [Security](#security) · [Disaster recovery](#disaster-recovery) · [Roadmap](#roadmap)

---

## Features

| Area | What you get |
| --- | --- |
| **Storefront** | 35 products, category filters, search, sort, saved items, quick view with image gallery and size picker, cart drawer. English-only UI. |
| **AI assistant** | Real LLM with tool calling. Recommends pieces, answers shipping and returns questions, adds and removes cart items. Replies in Egyptian Arabic or English, matching the customer. |
| **Grounding guard** | Every reply is checked for wrong prices, invented discounts, unknown product names and stray scripts. One corrective retry, then a safe fallback. |
| **Provider chain** | OpenRouter, then Groq, then Gemini. If one is rate limited, the next answers. |
| **Checkout** | Cash on delivery. The order is saved to the database first, then emailed. If email fails, the customer still sees a confirmation. If both fail, a WhatsApp fallback link is shown. |
| **Admin panel** | Password-protected. Add, edit, delete, hide, reorder products. Change prices, sizes, images. Edit store settings. See orders. Export and import backups. No redeploy needed. |
| **Resilience** | Catalog and settings live in Redis with a git seed as fallback. Written recovery plan in [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md). |

## Screenshots

<table>
<tr>
<td width="50%"><b>Quick view</b><br><img src="docs/screenshots/quick-view.png" alt="Quick view"></td>
<td width="50%"><b>AI assistant</b><br><img src="docs/screenshots/chatbot-desktop.png" alt="Chat assistant"></td>
</tr>
<tr>
<td><b>Admin: products</b><br><img src="docs/screenshots/admin-products.png" alt="Admin products"></td>
<td><b>Admin: editor</b><br><img src="docs/screenshots/admin-editor.png" alt="Admin editor"></td>
</tr>
<tr>
<td><b>Admin: settings</b><br><img src="docs/screenshots/admin-settings.png" alt="Admin settings"></td>
<td><b>Admin: login</b><br><img src="docs/screenshots/admin-login.png" alt="Admin login"></td>
</tr>
</table>

<table>
<tr>
<td align="center"><b>Store (phone)</b><br><img src="docs/screenshots/store-mobile.png" width="260" alt="Store on phone"></td>
<td align="center"><b>Assistant (phone)</b><br><img src="docs/screenshots/chatbot-mobile.png" width="260" alt="Chat on phone"></td>
<td align="center"><b>Admin (phone)</b><br><img src="docs/screenshots/admin-mobile.png" width="260" alt="Admin on phone"></td>
</tr>
</table>

> Admin screenshots were taken on a local copy with demo data and a demo password. The store and chat screenshots come from the live site.

## Architecture

```mermaid
flowchart LR
    U([Customer]) -->|HTTPS| CDN[Vercel CDN<br/>static site in public/]
    O([Owner]) -->|HTTPS| CDN
    CDN -->|/api/*| API[FastAPI<br/>Vercel serverless]
    API --> KV[(Upstash Redis<br/>catalog, settings,<br/>orders, images, sessions)]
    API --> LLM{{LLM providers<br/>OpenRouter, Groq, Gemini}}
    API --> MAIL[Resend<br/>order email]
    API -. fallback .-> SEED[[products.json<br/>git seed]]
    U -. fallback .-> WA[WhatsApp<br/>manual order]
```

## Flows

### Order flow

```mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant W as Website
    participant A as FastAPI
    participant K as Redis
    participant E as Resend email
    C->>W: Fill name, phone, city, address
    W->>A: POST /api/order (cart + details)
    A->>A: Re-price items from the live catalog, check sizes and sold-out, add shipping
    A->>K: Save order:NUMBER
    A->>E: Send order email
    alt email sent or order saved
        A-->>W: Confirmed + order number
    else both failed
        A-->>W: NOT confirmed + prefilled WhatsApp link
    end
    W-->>C: Confirmation screen
```

### Chatbot request, guard and fallback chain

```mermaid
flowchart TD
    M[Customer message] --> P[Build prompt<br/>live catalog, prices, shipping, owner notes]
    P --> OR{OpenRouter}
    OR -- ok --> G
    OR -- 429 or error<br/>cooldown --> GQ{Groq}
    GQ -- ok --> G
    GQ -- 429 or error<br/>cooldown --> GM{Gemini}
    GM -- ok --> G
    GM -- error --> SAFE
    G[Guard checks<br/>prices, discounts, product names, scripts] -->|pass| T{Tool call?}
    G -->|fail| R[One corrective retry]
    R -->|pass| T
    R -->|fail| SAFE[Safe fallback reply<br/>with support WhatsApp]
    T -- add or remove --> C[Update cart]
    T -- none --> OUT
    C --> OUT[Reply + product cards]
    SAFE --> OUT
```

### Admin and data flow

```mermaid
flowchart LR
    subgraph Browser
      L[Login form] --> UI[Admin UI]
    end
    L -->|POST /api/admin/login| AUTH[Check pbkdf2 hash<br/>rate limit, lockout]
    AUTH -->|httpOnly cookie + CSRF token| UI
    UI -->|CRUD, upload, settings| ADM[Admin API<br/>session + CSRF + Origin check]
    ADM --> KV[(Redis)]
    KV --> PUB[Public API<br/>15 s cache]
    PUB --> SITE[Storefront]
    PUB --> BOT[Chatbot catalog and price guard]
    ADM -->|snapshot before change| PREV[(catalog:prev<br/>one-step undo)]
```

### Deployment

```mermaid
flowchart LR
    DEV[Code change] --> T[pytest<br/>39 tests]
    T --> GH[(GitHub main)]
    GH --> VC[Vercel build<br/>FastAPI + static public/]
    VC --> PROD[rlvnt-store.vercel.app]
    ENV[Vercel env vars<br/>keys, ADMIN_PASSWORD_HASH, KV] --> VC
    GH -. alternate .-> RD[Render<br/>render.yaml]
```

## Data model

```mermaid
erDiagram
    CATALOG ||--o{ PRODUCT : contains
    PRODUCT ||--o{ IMAGE : "main + gallery"
    ORDER ||--|{ ORDER_ITEM : has
    ORDER_ITEM }o--|| PRODUCT : references
    ORDER ||--o| ORDER_STATE : "done flag"
    SETTINGS ||--|| CATALOG : "shipping, contacts"
    PRODUCT {
        string id
        string name
        int price
        string category
        list sizes
        string description
        bool hidden
        bool sold_out
    }
    IMAGE {
        string id
        string mime
        string data
    }
    ORDER {
        string number
        string text
        int total
        datetime created
    }
    ORDER_ITEM {
        string product_id
        string size
        int qty
    }
    SETTINGS {
        string store_name
        string announcement
        int shipping_fee
        string support_phone
        string whatsapp
        bool chatbot_enabled
    }
```

Redis keys: `catalog:products`, `catalog:prev`, `settings`, `order:<number>`, `orderstate:<number>`, `img:<id>`, `admin:s:*` (sessions), `admin:f:*` and `admin:lock:*` (login limits).

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | Vanilla HTML, CSS, JavaScript. No build step. |
| Backend | Python, FastAPI, httpx, Pydantic |
| AI | OpenRouter, Groq, Gemini (tool calling) with a custom grounding guard |
| Data | Upstash Redis over REST (free plan) |
| Email | Resend |
| Hosting | Vercel (static CDN plus serverless FastAPI). `render.yaml` for an alternate host. |
| Tests | pytest with fake KV and fake provider transports |

## Project structure

```text
.
├── public/                  static site served by the CDN
│   ├── index.html, app.js, style.css
│   ├── policies.html        shipping and returns, filled from live settings
│   ├── admin.html/.js/.css  admin panel
│   └── images/              product photos and logo
├── backend/
│   ├── app/
│   │   ├── main.py          routes, CORS, chat and order endpoints
│   │   ├── agent.py         LLM loop, provider chain, tools
│   │   ├── guard.py         grounding checks and safe fallback
│   │   ├── knowledge.py     system prompt built from live data
│   │   ├── cart.py, orders.py
│   │   ├── catalog.py       live catalog (Redis, seed fallback)
│   │   ├── settings.py      store settings
│   │   ├── admin.py         auth, admin API, image storage
│   │   ├── kv.py            Upstash REST client
│   │   └── products.json    seed catalog (35 products)
│   └── tests/               pytest suite
├── scripts/catalog_backup.py  backup, verify, restore
├── backups/                 catalog snapshots
├── index.py                 Vercel entry point
├── render.yaml              alternate deploy
└── DISASTER_RECOVERY.md
```

## API

Public endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET | `/api/products` | Visible products plus public settings |
| POST | `/api/cart/summary` | Price a cart |
| POST | `/api/chat` | Chat with the assistant |
| POST | `/api/order` | Place a cash-on-delivery order |
| GET | `/api/img/{id}` | Uploaded product image |

Admin endpoints (session cookie and CSRF token required, except login and status):

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/admin/login`, `/logout` | Sign in and out |
| GET | `/api/admin/me`, `/status` | Session info, admin enabled |
| GET, POST | `/api/admin/products` | List, add |
| PUT, DELETE | `/api/admin/products/{id}` | Edit, delete |
| POST | `/api/admin/products-reorder` | Reorder |
| POST | `/api/admin/revert` | Undo last catalog change |
| POST | `/api/admin/image` | Upload an image |
| GET, PUT | `/api/admin/settings` | Read, save settings |
| GET | `/api/admin/orders` | Recent orders |
| PUT | `/api/admin/orders/{number}` | Mark done |
| GET, POST | `/api/admin/export`, `/import` | Backup and restore |

## Run locally

```bash
git clone https://github.com/youssefabady-7/rlvnt-store.git
cd rlvnt-store/backend
pip install -r requirements.txt

# optional: at least one provider key for the chatbot
export OPENROUTER_API_KEY=...
# optional: admin panel (generate a hash, never store the password)
export ADMIN_PASSWORD_HASH="$(python -c 'from app.admin import make_hash; print(make_hash(input()))')"

uvicorn app.main:app --reload      # API on http://localhost:8000
```

Open `public/index.html` in a browser (it talks to `localhost:8000` locally). Without Redis the store runs from the seed `products.json`, and admin edits need Redis.

Run the tests:

```bash
cd backend && pytest
```

## Environment variables

Names only. Set them in Vercel (Production) or a local `.env`. Never commit values.

| Name | Required | Purpose |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | one provider key | First chat provider |
| `GROQ_API_KEY` | optional | Second provider |
| `GEMINI_API_KEY` | optional | Third provider |
| `OPENROUTER_MODEL`, `OPENROUTER_FALLBACKS`, `GROQ_MODEL`, `GEMINI_MODEL` | optional | Model overrides |
| `KV_REST_API_URL`, `KV_REST_API_TOKEN` | for admin and orders | Upstash Redis (`UPSTASH_REDIS_REST_*` also accepted) |
| `ADMIN_PASSWORD_HASH` | for admin | Salted pbkdf2 hash of the admin password |
| `RESEND_API_KEY` | for order email | Email delivery |
| `ORDER_EMAIL`, `ORDER_FROM` | optional | Order recipient and sender |
| `ALLOWED_ORIGINS` | optional | CORS list when the API is on another domain |

## Security

- **Admin auth is server-side only.** The password is stored as a salted pbkdf2-sha256 hash (600k iterations) in an env var. No secrets in client code.
- **Session:** random token in an `httpOnly`, `Secure`, `SameSite=Strict` cookie scoped to `/api/admin`, stored server-side for 8 hours.
- **CSRF:** per-session token header plus an Origin check on every state-changing call.
- **Brute force:** 5 failed logins per IP in 15 minutes locks that IP. 25 failures per hour locks everyone. Failed logins are slowed by 1 second.
- **Uploads:** magic-byte check and a 600 KB limit.
- **Orders:** prices are always recomputed on the server from the live catalog. The client price is ignored.
- **Chatbot:** answers are grounded in live data and checked by the guard. It cannot guarantee zero mistakes, so uncertain cases point to WhatsApp support.
- **Privacy:** logs hold minimal personal data. Secrets are never committed (`.env*` and `.vercel` are git-ignored).

## Disaster recovery

Full plan: **[DISASTER_RECOVERY.md](DISASTER_RECOVERY.md)**.

| If this happens | Do this |
| --- | --- |
| Bad product edit | Admin, Products, **Undo last change** |
| Catalog lost or corrupted | Admin, Backup, **Import** a saved export. Fallback is the git seed. |
| Bad code release | `git revert`, push, Vercel redeploys |
| Locked out of admin | Wait 15 minutes, or delete `admin:lock:*` and `admin:f:*` keys in the Upstash Data Browser |
| Forgot the admin password | New hash in `ADMIN_PASSWORD_HASH`, redeploy |
| Order email down | Orders are still saved in Redis and shown in the admin Orders tab |
| Full outage | Take orders on WhatsApp, redeploy from GitHub (Vercel or Render) |

## Roadmap

- [x] Real LLM assistant with cart tools
- [x] Provider fallback chain and grounding guard
- [x] Live admin panel with image upload
- [x] Redis-backed catalog, settings and orders
- [ ] Online payment (card and wallets)
- [ ] Order status page and customer notifications
- [ ] Discount codes
- [ ] Per-size stock counts
- [ ] Paid LLM credits for higher chat limits

## Credits

Brand and products: RLVNT. Rebuilt from the earlier Brand-mind2 project with a working LLM agent, a live admin and a documented recovery plan.

&copy; RLVNT. All rights reserved.
