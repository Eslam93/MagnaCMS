# Frontend — Next.js 15 (App Router)

TypeScript, Tailwind, shadcn/ui, TanStack Query, React Hook Form + Zod. Tooling: pnpm, ESLint, Prettier, Vitest, Playwright.

Application code lands here as the UI comes together. See the top-level [`README.md`](../README.md) for the stack overview and [`ARCHITECTURE.md`](../ARCHITECTURE.md) for the load-bearing decisions.

## Layout (target)

```
frontend/
├── app/                       # App Router
│   ├── (marketing)/           # public landing
│   ├── (auth)/                # login, register
│   └── (app)/                 # protected
│       ├── dashboard/
│       ├── generate/
│       ├── improve/
│       ├── brand-voices/
│       └── settings/
├── components/
│   ├── ui/                    # shadcn/ui
│   ├── features/
│   └── layouts/
├── lib/
│   ├── api/                   # OpenAPI-generated client + wrappers
│   ├── auth/
│   ├── hooks/
│   ├── utils/
│   └── validation/
├── public/
├── tests/
└── package.json
```
