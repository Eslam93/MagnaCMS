# AI Content Marketing Suite

A production-grade SaaS that helps marketers generate, manage, and improve marketing content using AI. Every generated piece can be paired with an AI-generated image in one flow.

> **Status:** Phase 0 (Bootstrap) — repo skeleton ready. Sections marked _(pending P_X_)_ will fill in as the corresponding phase ships. See [`PHASES.md`](./PHASES.md) for the full task list.

![CI – Backend](https://img.shields.io/badge/backend--ci-pending-lightgrey) ![CI – Frontend](https://img.shields.io/badge/frontend--ci-pending-lightgrey) ![Deploy](https://img.shields.io/badge/deploy-pending-lightgrey) ![License](https://img.shields.io/badge/license-MIT-blue)

---

## 1. Live demo

- **Live URL:** _(pending P2.7 — App Runner + Amplify go live on Day 5–6)_
- **Demo credentials:** _(pending P12.4 — seeded reviewer account)_
- **Screenshot / GIF:** _(pending P12.1)_

## 2. What it does

Five core flows:

1. **Generate** — pick a content type (blog, LinkedIn, ad copy, email), describe topic/tone/audience, get polished output.
2. **Pair with image** — one click to auto-generate a matching image from the content.
3. **Improve** — paste existing text, pick a goal, get a refined version with an explanation of what changed.
4. **Manage** — dashboard of all past generations with search, filter, export, soft delete with undo.
5. **Brand voice** — saved profiles that pre-fill style across generations.

## 3. Tech stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 15 + TypeScript + Tailwind + shadcn/ui + TanStack Query + Zod + React Hook Form |
| Backend | FastAPI + Python 3.12 + Pydantic v2 + async SQLAlchemy 2.0 + Alembic |
| Database | PostgreSQL 16 |
| Cache / rate limit / idempotency | Redis 7 (in-memory fallback when `USE_REDIS=false`) |
| AI — text | OpenAI `gpt-5.4-mini-2026-03-17` |
| AI — image | OpenAI `gpt-image-1` |
| Object storage | S3 (private, served via CloudFront with Origin Access Control) |
| Auth | Custom JWT (httpOnly refresh cookie + rotation) |
| Hosting | AWS App Runner (backend) + Amplify Hosting (frontend) + RDS Postgres + ElastiCache Serverless Redis |
| Infra-as-code | AWS CDK in TypeScript |
| Observability | structlog + CloudWatch + Sentry |
| CI/CD | GitHub Actions |

The full rationale lives in [`PROJECT_BRIEF.md`](./PROJECT_BRIEF.md) §2.

## 4. Quick start (local)

```bash
git clone <repo> && cd MagnaCMS
cp .env.example .env
# Fill in OPENAI_API_KEY and JWT_SECRET. Everything else has sane defaults.
docker-compose up --build
```

Services come up on:

| Service | URL |
|---|---|
| Frontend (stub until P4.1) | http://localhost:3000 |
| Backend (stub until P1.1) | http://localhost:8000 |
| Postgres | `localhost:5432` (user/pass: `app` / `app`) |
| Redis | `localhost:6379` |

Once Phase 1 lands, you'll additionally run:

```bash
docker-compose exec backend alembic upgrade head
docker-compose exec backend python -m app.scripts.seed
```

## 5. Architecture

```
Browser
  │
  ├─── app.<domain> ────────→ Amplify Hosting (Next.js SSR + static assets)
  │                              │
  │                              ▼
  │                          api calls to api.<domain>
  │
  └─── images.<domain> ────→ CloudFront ──→ S3 (private generated images)

api.<domain>
  │
  ▼
App Runner — FastAPI containers (auto-scale, PUBLIC egress, no VPC connector)
  │
  ├──→ RDS Postgres (strict SG)
  ├──→ ElastiCache Redis (rate limit, cache, idempotency, refresh-token blocklist)
  ├──→ OpenAI API (gpt-5.4-mini text, gpt-image-1 image)
  └──→ S3 (persist generated images)
```

Full diagram + rationale in [`PROJECT_BRIEF.md`](./PROJECT_BRIEF.md) §3 and [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## 6. API documentation

OpenAPI 3.1 spec auto-published once the backend is live:

- **Swagger UI:** `<live-api-url>/docs` _(pending P2.7)_
- **ReDoc:** `<live-api-url>/redoc` _(pending P2.7)_
- **Raw spec:** `<live-api-url>/openapi.json`

Endpoint summary (target shape — see brief §6 for full contract):

| Group | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` |
| Content | `POST /content/generate`, `GET /content`, `GET /content/:id`, `DELETE /content/:id`, `POST /content/:id/restore` |
| Images | `POST /content/:id/image`, `GET /content/:id/images` |
| Improver | `POST /improve`, `GET /improvements`, `GET /improvements/:id`, `DELETE /improvements/:id` |
| Brand voices | `GET /brand-voices`, `POST /brand-voices`, `GET /brand-voices/:id`, `PATCH /brand-voices/:id`, `DELETE /brand-voices/:id` |
| Usage | `GET /usage/summary` |
| Exports | `GET /content/:id/export?format=pdf\|docx\|markdown` |
| System | `GET /health`, `GET /openapi.json`, `GET /docs`, `GET /redoc` |

## 7. Project structure

```
MagnaCMS/
├── README.md                  # this file
├── PROJECT_BRIEF.md           # source of truth for architecture/contract
├── PHASES.md                  # task-level breakdown across 13 phases
├── ARCHITECTURE.md            # one-page key trade-offs + cost estimate
├── KICKOFF_PROMPT.md          # working agreement (historical)
├── docker-compose.yml         # local-dev orchestration
├── .env.example               # environment template
├── .github/workflows/         # CI pipelines
├── backend/                   # FastAPI service (Phase 1+)
├── frontend/                  # Next.js App Router (Phase 4+)
└── infra/                     # AWS CDK in TypeScript (Phase 2+)
```

Annotated tree with internal layout per service: [`PROJECT_BRIEF.md`](./PROJECT_BRIEF.md) §4.

## 8. Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `AI_PROVIDER_MODE` | yes | `openai` | `openai` / `bedrock` / `mock` |
| `OPENAI_API_KEY` | yes (unless mode=mock) | — | OpenAI key, prepaid |
| `OPENAI_TEXT_MODEL` | no | `gpt-5.4-mini-2026-03-17` | Pinned model ID |
| `OPENAI_IMAGE_MODEL` | no | `gpt-image-1` | Image gen model |
| `OPENAI_IMAGE_QUALITY` | no | `medium` | `low` / `medium` / `high` |
| `DATABASE_URL` | yes | local compose default | asyncpg connection string |
| `USE_REDIS` | no | `true` | Toggle in-memory fallback |
| `REDIS_URL` | yes if `USE_REDIS=true` | local compose default | Redis URL |
| `JWT_SECRET` | yes | — | `openssl rand -hex 32` |
| `JWT_ACCESS_TOKEN_TTL_SECONDS` | no | `900` | 15 min |
| `JWT_REFRESH_TOKEN_TTL_SECONDS` | no | `2592000` | 30 days |
| `S3_BUCKET_IMAGES` | yes in prod | dev default | Image bucket |
| `IMAGES_CDN_BASE_URL` | yes in prod | local fallback | CloudFront base URL |
| `NEXT_PUBLIC_API_BASE_URL` | yes (frontend) | `http://localhost:8000/api/v1` | API base URL |
| `SENTRY_DSN` | optional | — | If unset, Sentry silently no-ops |
| `LOG_LEVEL` | no | `INFO` | structlog level |
| `AWS_REGION` | yes for deploy | `us-east-1` | AWS region |

Full annotated set in [`.env.example`](./.env.example).

## 9. Running tests

_(pending P1.8 / P3.9 / P10.8)_

```bash
# Backend
cd backend && uv run pytest --cov=app --cov-fail-under=80

# Frontend
cd frontend && pnpm test --run

# E2E (Playwright)
cd frontend && pnpm playwright test
```

## 10. Deployment

_(pending P2.7 / P2.8)_

Single command tears it up:

```bash
cd infra && npm install && npx cdk deploy --all
```

CI/CD deploys automatically on push to `main` via `.github/workflows/deploy.yml`.

Teardown: `npx cdk destroy --all` (plus separate Amplify app deletion).

## 11. Architecture decisions

Key trade-offs are documented in [`ARCHITECTURE.md`](./ARCHITECTURE.md). Headline calls:

- **OpenAI direct over AWS Bedrock** — eliminated model-access friction (Anthropic use-case form, Nova Canvas LEGACY status); single key covers text + image. Bedrock retained as documented alternative.
- **No VPC connector on App Runner** — keeps Bedrock/S3/Secrets-Manager APIs reachable without NAT Gateway cost.
- **Public RDS with strict SG** — explicit allowlist beats the complexity of VPC connector + VPC endpoints for a short-lived demo.
- **Custom JWT over Cognito** — full control over refresh rotation + token blocklist; fewer moving parts in the IAM story.
- **Non-streaming content generation** — structured JSON outputs don't stream cleanly; staged loading UI gives the perceived-performance benefit without the bug surface.

## 12. What I'd build next

_(pending P12.1)_

Priority extras if time permits: password reset, A/B prompt testing, content calendar, Nova Image v2 migration plan (Nova Canvas EOL 2026-09-30).

## 13. Claude Code workflow

_(pending P12.6 — video shows real Claude Code segments from development)_

This project was built primarily with Claude Code. Working agreement: one task = one branch = one PR; conventional commits; draft PRs early; brief is source of truth and updated in the same PR as any contract-changing code.

## 14. License

[MIT](./LICENSE).
