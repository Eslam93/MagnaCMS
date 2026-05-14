# AI Content Marketing Suite

A production-grade SaaS web app that helps marketers generate, manage, and improve marketing content using AI — every generated piece can be paired with an AI-generated image in one flow.

> **Status:** Phase 0 (Bootstrap) — repo skeleton ready, application code arrives in Phase 1.

![CI – Backend](https://img.shields.io/badge/backend--ci-pending-lightgrey) ![CI – Frontend](https://img.shields.io/badge/frontend--ci-pending-lightgrey) ![Deploy](https://img.shields.io/badge/deploy-pending-lightgrey) ![License](https://img.shields.io/badge/license-MIT-blue)

This README will expand to the full 14-section evaluator-facing document in P0.5 and again in P12.1. For now it documents the minimum needed to bootstrap local development. The source of truth for architecture, API contract, database schema, prompts, and the 3-week build plan is [`PROJECT_BRIEF.md`](./PROJECT_BRIEF.md); the task-level breakdown lives in [`PHASES.md`](./PHASES.md).

## Quick start (local)

```bash
git clone <repo> && cd MagnaCMS
cp .env.example .env
# Fill in OPENAI_API_KEY and JWT_SECRET. Everything else has sane defaults.
docker-compose up --build
```

Postgres comes up on `:5432`, Redis on `:6379`, backend stub on `:8000`, frontend stub on `:3000`.

## Repository layout

```
MagnaCMS/
├── backend/        # FastAPI service (Python 3.12, async SQLAlchemy 2.0, Pydantic v2)
├── frontend/       # Next.js 15 App Router (TypeScript, Tailwind, shadcn/ui)
├── infra/          # AWS CDK in TypeScript (App Runner, RDS, S3, CloudFront, Amplify)
├── PROJECT_BRIEF.md
├── PHASES.md
└── docker-compose.yml
```

## License

MIT. See [LICENSE](./LICENSE).
