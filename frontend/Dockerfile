# Development image: runs `next dev` with hot reload. A production build stage is added in Phase 7.
FROM node:24.22.1-alpine

WORKDIR /app

# Install dependencies first so Docker caches this layer until package files change.
COPY package.json package-lock.json .npmrc ./
RUN npm ci

COPY . .

EXPOSE 3000
# -H 0.0.0.0: listen on all interfaces so the port is reachable from outside the container.
CMD ["npm", "run", "dev", "--", "-H", "0.0.0.0"]
