import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Sentry wrapping (`withSentryConfig`) lands in P2.10. Until then,
  // this is the bare Next.js config.
  experimental: {
    // Re-enabled now that /login and /register routes exist (P2.9b).
    // Build-time checks Link hrefs against the app/* file tree.
    typedRoutes: true,
  },
};

export default nextConfig;
