/**
 * Sentry client-side config.
 *
 * Loaded automatically by @sentry/nextjs at boot. Silently no-ops
 * when NEXT_PUBLIC_SENTRY_DSN is empty — dev environments never need
 * Sentry credentials. P11.5 polishes PII scrubbing + source maps.
 */

import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENV ?? "dev",
    tracesSampleRate: 0.1,
    sendDefaultPii: false,
    replaysSessionSampleRate: 0, // P11.5 may turn on session replay
    replaysOnErrorSampleRate: 0,
  });
}
