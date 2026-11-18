# Two targets from one file (Phase 7D):
#   dev   `next dev` with hot reload; docker-compose.yml builds this one
#   prod  `next build` output only, run by Node as a non-root user; docker-compose.prod.yml
#
# Shared first step: dependencies, cached until package files change.
FROM node:24.22.1-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json .npmrc ./
RUN npm ci

# ---------------------------------------------------------------------------- dev
FROM deps AS dev
COPY . .
EXPOSE 3000
# -H 0.0.0.0: listen on all interfaces so the port is reachable from outside the container.
CMD ["npm", "run", "dev", "--", "-H", "0.0.0.0"]

# ---------------------------------------------------------------------------- build
FROM deps AS build
COPY . .
# NEXT_PUBLIC_* values are inlined into the browser JavaScript AT BUILD TIME, so the public
# API URL must be known now; changing it later means rebuilding the image.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_TELEMETRY_DISABLED=1
# public/ is empty today and git doesn't keep empty folders; create it so the copy below works.
RUN mkdir -p public && npm run build

# ---------------------------------------------------------------------------- prod
# A fresh, small image: no source, no dev dependencies, no build tools. Only the standalone
# server, its traced node_modules, and the static assets it serves.
FROM node:24.22.1-alpine AS prod
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
# Run as an unprivileged user: a bug in the app can't modify the image or bind low ports.
RUN addgroup -S atlas && adduser -S atlas -G atlas
COPY --from=build --chown=atlas:atlas /app/.next/standalone ./
COPY --from=build --chown=atlas:atlas /app/.next/static ./.next/static
COPY --from=build --chown=atlas:atlas /app/public ./public
USER atlas
EXPOSE 3000
CMD ["node", "server.js"]
