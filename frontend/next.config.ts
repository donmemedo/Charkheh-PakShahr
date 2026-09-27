import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // browser talks to Next only; Next proxies /api to FastAPI (baked at build time)
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.BACKEND_URL ?? "http://localhost:8000"}/api/:path*` }];
  },
};

export default nextConfig;
