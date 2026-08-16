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
  // Self-contained server for the container image (apps/console/Dockerfile).
  output: "standalone",
  reactStrictMode: true,
  transpilePackages: ["@nexus/ui"],
  // Lane agent-tools (CP-15): knowledge uploads go through a Server Action
  // as multipart (API caps at 10 MB → 413); the default 1 MB would 413 first.
  experimental: { serverActions: { bodySizeLimit: "11mb" } },
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
