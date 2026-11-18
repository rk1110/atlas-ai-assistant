# Deploying Atlas (Phase 7D)

Atlas is **deploy-ready**: production images, a production Compose file, and CI that builds both. It is **not deployed publicly** (decision 2026-11-16: no public deploy for now). This guide is the path when that changes.

## Dev vs production

| | Dev (`docker-compose.yml`) | Production (`+ docker-compose.prod.yml`) |
| --- | --- | --- |
| Frontend | `next dev`: each page compiles on its first visit (1-3 s) | `next build` output (`output: "standalone"`): login page in 0.03 s, 300 MB image, non-root |
| Backend | your code bind-mounted, `--reload` on save, runs as root | code baked into the image, no reload, non-root user `atlas`, `--proxy-headers` |
| Migrations | the backend runs `alembic upgrade head` on every start | a one-off `migrate` container runs them before the backend starts |
| Published ports | databases on 127.0.0.1 for your tools | only frontend 3000, backend 8000, Langfuse 3001 |
| Session cookie | HTTP is fine (`secure_cookie: false`) | HTTPS only (`AUTH_SECURE_COOKIE=true`) |
| CORS | `http://localhost:3000` | your real frontend address (`CORS_ORIGINS`) |

Why migrations move out: with two backend containers, both would run `alembic upgrade` at startup and race on the same tables. One short-lived job, then the app, is the standard pattern.

## The simplest real deployment: one VM

Atlas runs 11 services (Postgres + pgvector, Redis, Neo4j, Langfuse with ClickHouse and MinIO, two MCP servers, backend, frontend). Splitting them across managed services (Vercel + Render + Neo4j Aura + Langfuse Cloud) is possible but means four accounts and four sets of secrets. One VM with Docker runs the same Compose stack you use every day.

- **Size:** 4 vCPU / 8 GB RAM minimum (the stack uses ~5 GB on your Mac; the embedding and reranker models load into the backend). About $40-50/month at Hetzner, DigitalOcean or Fly.io machines.
- **Domains:** put the frontend and API under ONE site, for example `atlas.example.com` and `api.atlas.example.com`. The session cookie is `SameSite=Lax`: it travels between subdomains of the same site, but not between unrelated domains (`atlas.vercel.app` + `atlas-api.onrender.com` would break login).
- **HTTPS:** a reverse proxy in front terminates TLS and forwards to ports 3000 and 8000. Caddy is the least work (automatic Let's Encrypt certificates). Not part of the Compose stack, because it depends on your domain; a two-line-per-site `Caddyfile`:

  ```
  atlas.example.com      { reverse_proxy localhost:3000 }
  api.atlas.example.com  { reverse_proxy localhost:8000 }
  ```

## Steps

1. **Server:** a fresh Ubuntu VM with Docker installed; firewall open only for 22 (SSH), 80 and 443.
2. **Code:** `git clone` the repo onto the server.
3. **Secrets:** `cp .env.example .env` and fill in real values. New, strong ones for every password and `AUTH_SECRET`, never the dev ones. Uncomment and set the Production block:
   - `NEXT_PUBLIC_API_URL=https://api.atlas.example.com` (baked into the frontend image at build time: change it = rebuild)
   - `CORS_ORIGINS=["https://atlas.example.com"]`
   - `AUTH_SECURE_COOKIE=true`
   - `LANGFUSE_UI_URL=https://langfuse.atlas.example.com` (or keep Langfuse private and reach it over an SSH tunnel)
4. **Start:**

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   docker compose -f docker-compose.yml -f docker-compose.prod.yml ps    # all healthy, migrate "exited (0)"
   ```

5. **Data** (once; the same commands as dev, against the prod stack):

   ```bash
   P="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
   $P exec backend python -m scripts.seed_users     # demo logins from config/auth.yaml
   $P exec backend python -m ingestion.run          # knowledge base from data/ (uses the model for scans/images)
   $P exec backend python -m graph.build            # knowledge graph (one model call per document)
   ```

6. **Reverse proxy:** install Caddy with the `Caddyfile` above.

## Check before calling it live

- `https://api.atlas.example.com/health/ready` returns `{"status":"ready"}` (the database is reachable).
- Log in on `https://atlas.example.com`; in the browser's dev tools the `atlas_session` cookie shows **Secure** and **HttpOnly**.
- Logged out, `https://api.atlas.example.com/api/conversations` returns 401.
- One chat answer appears in Langfuse with environment `production`.
- **Analytics → Model spend** shows the daily budget (`budget.daily_usd` in `config/models.yaml`): a public URL needs a cap.
- Ports 5432, 6379, 7474 and 7687 are NOT reachable from outside (`nc -zv <server-ip> 5432` fails).

## Update, roll back, back up

- **Update:** `git pull`, then the same `up -d --build`. The `migrate` container applies new migrations before the new backend starts.
- **Roll back code:** `git checkout <previous tag>` and `up -d --build`. A migration is only undone with `alembic downgrade`, so review migrations before deploying them.
- **Back up:** Postgres holds everything that matters (chats, memory, documents, vectors, usage, evals). Nightly: `$P exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > atlas-$(date +%F).sql.gz`, copied off the server.

## Try the prod stack on your Mac

```bash
docker compose down                          # the prod stack reuses the same ports
NEXT_PUBLIC_API_URL=http://localhost:8000 CORS_ORIGINS='["http://localhost:3000"]' AUTH_SECURE_COOKIE=false \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

`AUTH_SECURE_COOKIE=false` only because http://localhost has no HTTPS. The prod stack uses its own volumes for the model cache and uploads (it runs as a non-root user), so the first start downloads the embedding model again. Back to dev: `docker compose -f docker-compose.yml -f docker-compose.prod.yml down`, then `docker compose up -d`.

## Not covered yet

- Automatic deploys from CI (build images in CI, push them to a registry, pull on the server).
- More than one backend container behind a load balancer (the app is ready: sessions are signed cookies, rate limits live in Redis, migrations run separately).
- Managed databases and Langfuse Cloud instead of running them yourself.
