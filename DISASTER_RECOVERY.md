# RLVNT Disaster Recovery and Business Continuity Plan

Scope: the RLVNT online store (static site + FastAPI backend on Vercel, code on GitHub, order email through Resend, assistant through OpenRouter).
Owner: Youssef Abady (youssefabady6@gmail.com, +201270383409). Last reviewed: 2026-11-25.

## 1. Goals

- **RTO** (max time to get the store back): 1 hour for the site and API, 15 minutes for taking orders by an alternative channel (WhatsApp).
- **RPO** (max data we can lose): 0 orders (every order is emailed, and logged on failure). Catalog: last Git commit (at most 1 day of edits).
- Customers can always place an order, even when a part of the system is down.

## 2. What we protect (assets)

| Asset | Where it lives | Backup |
|---|---|---|
| Source code, site, product images | GitHub `youssefabady-7/rlvnt-store` | Git history, any clone |
| Product catalog | `backend/app/products.json` | Git + `backups/` snapshots (`scripts/catalog_backup.py`) |
| Orders | Email to the owner (Resend), failure log, WhatsApp copy | Owner's inbox, Vercel logs, WhatsApp chat |
| Hosting config | Vercel project `rlvnt-store` | Redeploy from GitHub in minutes |
| Secrets (API keys) | Vercel env vars | Stored in the owner's password vault, rotate if leaked |

## 3. Risk table

| # | Risk | Likelihood | Impact | Built-in protection | Recovery action | RTO | RPO |
|---|---|---|---|---|---|---|---|
| 1 | Order email provider (Resend) fails or key expires | Medium | High (orders not seen) | Retry once, then fallback: order written to server log (`ORDER_FALLBACK`) and customer gets a prefilled WhatsApp button | Read orders from Vercel logs, fix/rotate key, redeploy | 15 min | 0 |
| 2 | Assistant (OpenRouter free model) is down or rate limited | High | Low | Model fallback list, friendly error, shop and checkout keep working without chat | Change `OPENROUTER_MODEL`/fallbacks env var | 10 min | 0 |
| 3 | Bad deploy breaks the site | Medium | High | Tests (`pytest`), `/health` check, Vercel keeps every previous deployment | Instant rollback (section 5) | 5 min | 0 |
| 4 | Product data corrupted or deleted | Low | High | `scripts/catalog_backup.py verify/backup/restore`, Git history | Restore latest backup, commit, redeploy | 30 min | 1 day |
| 5 | Vercel outage | Low | High | Static assets on CDN, customers can still message on WhatsApp (policy page and footer) | Take orders by WhatsApp; redeploy on Render (`render.yaml`) if outage is long | 1 h | 0 |
| 6 | GitHub account or repo lost | Low | High | Repo can be re-created from any local clone; Vercel keeps deployed source | Push a clone to a new repo, reconnect Vercel | 1 h | last push |
| 7 | API key or token leaked | Low | High | Keys only in env vars and vault, never in code | Revoke and rotate key, redeploy | 20 min | 0 |
| 8 | Customer has no internet or API is unreachable | High | Low | Catalog cached in browser, cart saved locally, offline banner, retry button | Automatic when connection returns | auto | 0 |
| 9 | Spam or abusive orders | Medium | Medium | Rate limit per IP, honeypot field, server-side price (800 EGP flat), input validation | Block abusive IP, review logs | 15 min | 0 |
| 10 | Domain/DNS problem (if a custom domain is added later) | Low | Medium | Keep the `*.vercel.app` URL working | Remove or fix the DNS record | 1 h | 0 |

## 4. Technical resilience features (implemented)

1. **Order fallback.** `POST /api/order` retries the email once. If it still fails the order is logged as `ORDER_FALLBACK` (full order text) and the response includes a prefilled `wa.me` link; the site shows a "Send order on WhatsApp" button. The customer always gets a confirmation with an order number.
2. **Health endpoint.** `GET /api/health` (or `/health`) reports `ok` or `degraded` with checks for catalog, order email and assistant, for uptime monitoring.
3. **Graceful errors and offline states.** The catalog is cached in the browser (stale-while-revalidate), automatic retries with a Retry button, an offline banner, and the cart is kept in local storage so nothing is lost on a refresh or disconnect.
4. **Catalog backup and restore.** `python scripts/catalog_backup.py backup | verify | list | restore`. Backups are validated (JSON, required fields, unique ids, image files exist). Restore saves the current file first, so it can be undone.
5. **Automated tests.** `cd backend && pytest` covers pricing, the assistant, order fallback, health and catalog verification.
6. **Safe config.** Price is forced to 800 EGP on the server; secrets only in environment variables.

## 5. Procedures

### 5.1 Roll back a bad deployment (fastest)
1. Open Vercel, project `rlvnt-store`, tab **Deployments**.
2. Pick the last good deployment, menu **Promote to Production** (or CLI: `vercel rollback`).
3. Check `/health` and the home page.

### 5.2 Roll back a bad code change in GitHub
1. `git log --oneline` and find the last good commit.
2. `git revert <bad-commit>` (keeps history) then `git push origin main`.
3. Vercel redeploys automatically or run `vercel deploy --prod`.

### 5.3 Restore the product catalog
1. `python scripts/catalog_backup.py list` then `python scripts/catalog_backup.py restore backups/<file>` (no file = newest).
2. `python scripts/catalog_backup.py verify`, commit and push, redeploy.
3. Take a new backup after any catalog change: `python scripts/catalog_backup.py backup`.

### 5.4 Order email is down
1. Search Vercel logs for `ORDER_FALLBACK` to list orders that were not emailed; also check the WhatsApp chat.
2. Fix `RESEND_API_KEY` or `ORDER_EMAIL` in Vercel env vars, redeploy.
3. Contact affected customers to confirm orders.

### 5.5 Full site outage
1. Post on Instagram/WhatsApp status that orders are taken by WhatsApp: +201270383409.
2. Redeploy from GitHub to Vercel, or deploy the same repo on Render using `render.yaml`.
3. Verify with `/health`, a test order, and the chat.

## 6. Roles and communication

- Owner: decides, redeploys, rotates keys, contacts customers.
- Customers are told through the WhatsApp number and the Service continuity section of the policies page.

## 7. Testing and review

- Before each release: `pytest`, `catalog_backup.py verify`, a live test order flow.
- Monthly: take a catalog backup, test one restore on a copy, check env vars and API key validity.
- After any incident: write what happened, the fix and what to change in this plan.
