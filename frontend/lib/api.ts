/**
 * Typed API client wrapper around openapi-fetch.
 *
 * Schema generation (`pnpm gen:api`) downloads the live OpenAPI spec
 * from the deployed backend and writes it to `types/api.d.ts`. Until
 * the backend is live, a hand-stubbed `paths` type lives there and
 * gets replaced on first gen.
 *
 * The client always sends `credentials: 'include'` so the httpOnly
 * refresh cookie flows on cross-origin requests once Amplify + App
 * Runner are wired. A 401 interceptor (P2.9b) will call
 * `/auth/refresh` and retry the original request once before bouncing
 * the user to /login.
 */

import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "@/types/api";

const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

/**
 * Attach the in-memory access token to every request. Reads from the
 * Zustand auth store at request time so token rotation is picked up
 * automatically.
 */
const authMiddleware: Middleware = {
  async onRequest({ request }) {
    if (typeof window !== "undefined") {
      // Dynamic import avoids SSR pulling Zustand into the server bundle.
      const { useAuthStore } = await import("@/lib/auth-store");
      const token = useAuthStore.getState().accessToken;
      if (token) {
        request.headers.set("authorization", `Bearer ${token}`);
      }
    }
    return request;
  },
};

export const api = createClient<paths>({
  baseUrl,
  credentials: "include",
});

api.use(authMiddleware);

// 401 → refresh + retry interceptor lands in P2.9b together with the
// /auth/refresh client call. For now the client just returns the 401
// and the caller surfaces it as "please sign in again".
