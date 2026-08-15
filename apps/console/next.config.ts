import type { NextConfig } from "next";

/**
 * Security headers (CP-32, first pass). The CSP is strict by default and
 * uses a per-request nonce set in ``middleware.ts``; ``unsafe-inline`` is
 * not allowed for scripts. Styles keep ``'unsafe-inline'`` only because
 * Next's dev tooling injects inline styles; production tightens further
 * once every inline style is gone.
 */
const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  transpilePackages: ["@nexus/ui"],
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
