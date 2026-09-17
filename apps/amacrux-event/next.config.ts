import type { NextConfig } from "next";

/**
 * Landing pública del diagnóstico. Sin `output: standalone` (se despliega en
 * Vercel). Cabeceras de seguridad básicas; no hay CSP con nonce porque no se
 * cargan scripts de terceros salvo la analítica opcional.
 */
const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
