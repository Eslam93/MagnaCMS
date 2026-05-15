"use client";

import { useMeQuery } from "@/lib/auth/use-me";

/**
 * Account page. Shows the basics the user can verify at a glance —
 * full preferences (theme, default content type, notification opt-ins)
 * are out of scope for the current demo window.
 */
export default function SettingsPage() {
  const me = useMeQuery();
  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold">Account</h1>
        <p className="text-sm text-muted-foreground">
          Read-only for now. Full settings (theme, defaults, notifications) ship after the demo.
        </p>
      </header>
      {me.isPending ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : me.data ? (
        <section className="rounded-lg border bg-card p-6">
          <dl className="grid gap-2 text-sm">
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
      ) : null}
    </div>
  );
}
