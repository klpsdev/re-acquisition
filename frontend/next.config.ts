import type { NextConfig } from "next";

// The browser only ever talks to this Next.js app. Requests to /api/* are
// proxied server-side to FastAPI, so there are no CORS issues and the backend
// URL never ships to the client.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};

export default nextConfig;
