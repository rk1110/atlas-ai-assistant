import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Production image (Phase 7D): `next build` also writes .next/standalone, a self-contained
  // server.js plus only the node_modules files it needs. No effect on `next dev`.
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
