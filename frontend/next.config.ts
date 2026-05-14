import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Sentry wrapping (`withSentryConfig`) lands in P2.10. Until then,
  // this is the bare Next.js config.
  //
  // typedRoutes is off until the auth routes land (P2.9b). It type-
  // checks every Link href against the actual app/* file tree, which
  // means placeholder links to routes-yet-to-exist fail at build.
  // Flip back to true once /login and /register are real routes.
};

export default nextConfig;
