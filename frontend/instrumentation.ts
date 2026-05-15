/**
 * Next.js instrumentation hook. Runs at server startup.
 *
 * Loads the right Sentry config based on the runtime. The configs
 * themselves no-op when NEXT_PUBLIC_SENTRY_DSN is unset, so this
 * registration is always safe to run.
 */

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }
  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

// `onRequestError` re-export lands once we bump to @sentry/nextjs
// v8.50+ (the App Router error-capture entry point added in that
// version). For now Sentry's `withSentryConfig` wrapping handles
// most error capture via the existing integrations.
