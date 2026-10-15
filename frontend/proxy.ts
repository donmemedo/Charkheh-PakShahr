import { NextResponse, type NextRequest } from "next/server";

/**
 * Per-request CSP nonce (Next.js 16 `proxy`, the renamed middleware).
 * Next reads the nonce out of the forwarded Content-Security-Policy header and
 * stamps it on its own script tags; app/layout.tsx reads `x-nonce` for the inline theme script.
 * style-src keeps 'unsafe-inline': React `style={{}}` attributes and Tailwind v4 are used
 * throughout, and a style nonce would not cover attributes anyway.
 */
export function proxy(request: NextRequest) {
  const nonce = btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(16))));
  const dev = process.env.NODE_ENV === "development";
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  const https = request.headers.get("x-forwarded-proto") === "https" || request.nextUrl.protocol === "https:";
  if (https) response.headers.set("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
  return response;
}

export const config = {
  matcher: [
    {
      // everything except the proxied API, static assets and icons; skip router prefetches
      source: "/((?!api/|_next/static|_next/image|favicon.ico|icon.svg).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
