"use client";

import { Button } from "@/components/ui/button";
import { useLogoutMutation } from "@/lib/auth/hooks";
import { useAuthStore } from "@/lib/auth-store";

/**
 * Bare-bones dashboard placeholder for P2.9b.
 *
 * The real protected layout (sidebar, route guard, top nav, etc.)
 * lands in P2.9c. This file exists only because:
 *   - The auth hooks push to `/dashboard` on success
 *   - `typedRoutes: true` rejects pushes to non-existent routes
 *
 * P2.9c will repath this under `app/(protected)/dashboard/page.tsx`
 * once the route-group structure goes in.
 */
export default function DashboardPlaceholder() {
  const accessToken = useAuthStore((s) => s.accessToken);
  const logout = useLogoutMutation();

  return (
    <main className="container flex min-h-screen flex-col items-center justify-center gap-6 py-12 text-center">
      <h1 className="text-3xl font-bold">Signed in</h1>
      <p className="max-w-md text-muted-foreground">
        Auth works. The real protected layout — sidebar, nav, /me display,
        route guard — lands in P2.9c.
      </p>
      <p className="font-mono text-xs text-muted-foreground">
        access_token: {accessToken ? `${accessToken.slice(0, 24)}…` : "(none)"}
      </p>
      <Button onClick={() => logout.mutate()} disabled={logout.isPending}>
        {logout.isPending ? "Signing out…" : "Sign out"}
      </Button>
    </main>
  );
}
