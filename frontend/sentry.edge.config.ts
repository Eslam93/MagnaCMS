/**
 * Sentry edge-runtime config (used by Next.js edge functions /
 * middleware). Silently no-ops when NEXT_PUBLIC_SENTRY_DSN is empty.
 */

import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENV ?? "dev",
    tracesSampleRate: 0.1,
    sendDefaultPii: false,
  });
}
