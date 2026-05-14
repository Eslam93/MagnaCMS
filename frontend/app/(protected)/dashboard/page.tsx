"use client";

import { useMeQuery } from "@/lib/auth/use-me";

/**
 * Dashboard landing page (inside the protected layout).
 *
 * Phase 2 ships only the welcome state — the real dashboard (content
 * list, search, filters) lands in P6.4. For now we just confirm the
 * auth round-trip works by displaying the /me response.
 */
export default function DashboardPage() {
  const me = useMeQuery();
  if (!me.data) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Welcome back, {me.data.full_name.split(" ")[0]}.</h1>
        <p className="text-sm text-muted-foreground">
          You&apos;re signed in. Phase 3 ships the content-generation flow.
        </p>
      </div>

      <section className="rounded-lg border bg-card p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Account
        </h2>
        <dl className="mt-4 grid gap-2 text-sm">
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Email</dt>
            <dd className="font-mono">{me.data.email}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Full name</dt>
            <dd>{me.data.full_name}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Member since</dt>
            <dd className="font-mono">{new Date(me.data.created_at).toLocaleDateString()}</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
