import type { NextConfig } from "next";

/**
 * embed.auphere.com — the iframe host for the partner widget (ADR-028).
 *
 * NO static frame-ancestors here: the per-partner allow-list is resolved
 * dynamically in `middleware.ts` from `GET /v1/embed/partner-config`.
 * Everything else about this app assumes it runs INSIDE someone else's
 * page — no cookies, no localStorage for auth, token only in memory.
 */
const nextConfig: NextConfig = {
  poweredByHeader: false,
};

export default nextConfig;
