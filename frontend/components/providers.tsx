"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

/**
 * Client-side providers wrapper.
 *
 * TanStack Query is the only provider for now — Zustand's auth store
 * doesn't need a provider (it's a global hook), and shadcn/ui's
 * theme provider lives in the root layout. Sentry wraps this in P2.10.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30 * 1000, // 30s; auth-sensitive data is short-lived
            gcTime: 5 * 60 * 1000, // 5min
            retry: (failureCount, error) => {
              // Don't retry on auth failures or schema errors.
              const status = (error as { status?: number })?.status;
              if (status === 401 || status === 403 || status === 422) {
                return false;
              }
              return failureCount < 2;
            },
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
