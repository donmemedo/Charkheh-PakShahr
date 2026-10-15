import type { NextConfig } from "next";

// Static security headers: zero runtime cost, set once per response by Next.
// CSP (needs a per-request nonce) lives in proxy.ts.
const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // Next buffers a clone of every request body (default up to 10 MB); the API rejects anything over 16 KB anyway
  experimental: { proxyClientMaxBodySize: "16kb" },
  async headers() {
    return [{ source: "/(.*)", headers: SECURITY_HEADERS }];
  },
  // browser talks to Next only; Next proxies /api to FastAPI (baked at build time)
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.BACKEND_URL ?? "http://localhost:8000"}/api/:path*` }];
  },
};

export default nextConfig;
