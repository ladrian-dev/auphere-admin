import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  // Spec 031: the panel consumes the design system from source, like the console.
  transpilePackages: ["@nexus/ui"],
};

export default nextConfig;
