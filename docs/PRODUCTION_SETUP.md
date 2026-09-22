# Production Setup

This is the secure initialization flow for a real deployment, as opposed to
local development.

## 1. Generate real secrets

Never use the placeholder values in `.env.example`.

```bash
# SECRET_KEY (JWT signing key)
python3 -c "import secrets; print(secrets.token_urlsafe(64))"

# POSTGRES_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put the real values in `.env` at the repo root (never commit this file —
it's already in `.gitignore`).

## 2. Set the production posture

In `.env`:

```
ENVIRONMENT=production
ALLOW_DEV_BOOTSTRAP=false
```

With `ALLOW_DEV_BOOTSTRAP=false`, the `POST /api/auth/bootstrap-admin`
endpoint refuses every request with `403 Forbidden`, regardless of whether
the database is empty. There is no way to create the first admin over HTTP
in this posture — that's intentional.

## 3. Create the first admin user

```bash
docker compose up -d postgres backend
docker compose exec backend python scripts/create_admin.py
```

This runs an interactive CLI directly against the database (see
`scripts/create_admin.py`). It prompts for email, full name, and a password
(minimum 10 characters, entered without echo), and refuses to run if a user
with that email already exists.

## 4. Set a real domain and enable HTTPS

Edit `docker/Caddyfile`:

```diff
- :80 {
+ smartvision.yourdomain.com {
```

and remove the `auto_https off` global option. Caddy will then
automatically obtain and renew a Let's Encrypt certificate on first
request — no other configuration is required. Update `CORS_ORIGINS` and
`PUBLIC_BASE_URL` in `.env` to match the real domain.

## 5. Restrict direct database/API port exposure

The default `docker-compose.yml` binds Postgres (`5432`) and the backend
(`8000`) to `127.0.0.1` only, for local debugging. On a real server, either
remove those `ports:` entries entirely (Caddy is the only thing that needs
to reach the backend, over the internal Docker network) or keep them bound
to localhost and reach them only over SSH tunnel.

## 6. Review `docs/LIMITATIONS.md` before relying on this in any real
deployment

In particular: the login rate limiter is per-process, and no detection
category should be treated as authoritative without human review.
