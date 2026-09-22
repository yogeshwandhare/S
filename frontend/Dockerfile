# syntax=docker/dockerfile:1
#
# Build context for this Dockerfile is the REPO ROOT (see docker-compose.yml),
# not the frontend/ directory -- that's what lets the final stage pull in
# docker/Caddyfile alongside the frontend build output.
FROM node:22-slim AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .
# VITE_API_BASE_URL is intentionally left empty: the built frontend calls
# same-origin relative paths (/api/...), and Caddy reverse-proxies those to
# the backend container. This avoids baking a backend hostname into the
# static bundle.
RUN npm run build

# --- Final stage: Caddy serves the static build and proxies /api ---
FROM caddy:2-alpine

COPY --from=build /app/dist /srv
COPY docker/Caddyfile /etc/caddy/Caddyfile
