import type { NextConfig } from "next";

/**
 * Re-export Meta Embedded Signup IDs to the client bundle.
 *
 * Doppler injects them as ``NEXUS_META_*`` (the prefix the FastAPI backend
 * uses); Next.js only exposes env vars with the ``NEXT_PUBLIC_*`` prefix
 * to client-side code. This block maps the two prefixes at build time so
 * the FB SDK loader (which runs in the browser) can read them without
 * duplicating values in Doppler.
 *
 * Only IDs that are safe to ship to the browser go here. ``META_APP_SECRET``
 * and ``META_WEBHOOK_VERIFY_TOKEN`` are NOT in this list — they MUST stay
 * server-side only.
 */
const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_META_APP_ID: process.env.NEXUS_META_APP_ID,
    NEXT_PUBLIC_META_CONFIG_ID_WA_CLOUD_API:
      process.env.NEXUS_META_CONFIG_ID_WA_CLOUD_API,
    NEXT_PUBLIC_META_CONFIG_ID_WA_COEXISTENCE:
      process.env.NEXUS_META_CONFIG_ID_WA_COEXISTENCE,
    NEXT_PUBLIC_META_GRAPH_API_VERSION:
      process.env.NEXUS_META_GRAPH_API_VERSION ?? "v22.0",
  },
};

export default nextConfig;
