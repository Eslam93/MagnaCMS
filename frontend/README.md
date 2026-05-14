# Frontend — Next.js 15 (App Router)

TypeScript, Tailwind v3, shadcn/ui, TanStack Query, Zustand for client state, openapi-fetch for the typed API client. Tooling: pnpm, ESLint (via package.json), Prettier (via package.json), Vitest. Playwright E2E lands in P10.8.

## Status

| Surface                                       | PR        | Status     |
| --------------------------------------------- | --------- | ---------- |
| Scaffold (this directory, tooling, providers) | **P2.9a** | 🚧 current |
| Login + register pages, API client            | P2.9b     | 📋 not yet |
| Protected layout, sidebar, logout, /me        | P2.9c     | 📋 not yet |
| Sentry init                                   | P2.10     | 📋 not yet |

## Local commands

```bash
cd frontend
pnpm install
pnpm dev          # next dev → http://localhost:3000
pnpm build        # production build
pnpm test         # vitest run
pnpm lint         # next lint (ESLint config in package.json)
pnpm format       # prettier --write .
pnpm typecheck    # tsc --noEmit
```

## Environment

Single env var so far:

```bash
# .env.local
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
```

Defaults to `http://localhost:8000/api/v1` if unset. In production the value is set by Amplify environment configuration to point at the App Runner URL.

## Auth model

In-memory access token (Zustand store) + httpOnly refresh cookie (set by backend, unreadable by JS). The refresh flow happens transparently via a 401 interceptor on the API client — that interceptor lands in P2.9b.

## Layout

```
frontend/
├── app/                       # App Router
│   ├── layout.tsx             # root layout with providers
│   ├── page.tsx               # landing
│   └── globals.css            # Tailwind base + CSS variables
├── components/
│   ├── providers.tsx          # TanStack Query
│   └── ui/                    # shadcn/ui components
│       └── button.tsx
├── lib/
│   ├── api.ts                 # openapi-fetch wrapper + auth middleware
│   ├── auth-store.ts          # Zustand: in-memory access token
│   └── utils.ts               # `cn` helper
├── types/
│   └── api.d.ts               # hand-stubbed OpenAPI types
├── tests/
│   ├── setup.ts
│   └── auth-store.test.ts
├── amplify.yml                # Amplify build spec
├── package.json
├── tsconfig.json
├── next.config.ts
├── postcss.config.mjs
└── tailwind.config.ts
```
