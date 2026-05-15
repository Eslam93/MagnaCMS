# MagnaCMS — AI Content Marketing Suite

A production-grade SaaS that helps marketers generate, manage, and improve marketing content using AI. Every generated piece can be paired with an AI-generated image in one flow.

> **Status:** in active development. The repo is functional from day one — see the dev log for what works today vs. what's next.

![CI – Backend](https://img.shields.io/badge/backend--ci-pending-lightgrey) ![CI – Frontend](https://img.shields.io/badge/frontend--ci-pending-lightgrey) ![Deploy](https://img.shields.io/badge/deploy-pending-lightgrey) ![License](https://img.shields.io/badge/license-MIT-blue)

---

## 1. Live demo

_Coming soon._ The deployed URL and a seeded demo account will appear here once the backend lands on AWS.

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

Rationale for each pick is in [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## 4. Quick start (local)

```bash
git clone https://github.com/Eslam93/MagnaCMS.git
cd MagnaCMS
cp .env.example .env
# Fill in OPENAI_API_KEY and JWT_SECRET. Everything else has sane defaults.
docker-compose up --build
```

Services come up on:

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend | http://localhost:8000 |
| Postgres | `localhost:5432` (user/pass: `app` / `app`) |
| Redis | `localhost:6379` |

Once the backend application code lands you'll additionally run:

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
  ├──→ RDS Postgres (strict SG, public endpoint with App-Runner-IP allowlist)
  ├──→ ElastiCache Redis (rate limit, cache, idempotency, refresh-token blocklist)
  ├──→ OpenAI API (gpt-5.4-mini text, gpt-image-1 image)
  └──→ S3 (persist generated images)
```

Full rationale and key trade-offs: [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## 6. API documentation

Once deployed, the OpenAPI 3.1 spec is auto-published:

- **Swagger UI:** `<api-url>/docs`
- **ReDoc:** `<api-url>/redoc`
- **Raw spec:** `<api-url>/openapi.json`

### Available today

| Group | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` |
| Content | `POST /content/generate` (blog post, LinkedIn post, email, ad copy), `GET /content`, `GET /content/:id`, `DELETE /content/:id` (soft delete), `POST /content/:id/restore` (24-hour window) |
| Images | `POST /content/:id/image` (generate or regenerate), `GET /content/:id/images` (every version, newest first) |
| System | `GET /health`, `GET /openapi.json`, `GET /docs`, `GET /redoc` |

### Planned

| Group | Endpoints |
|---|---|
| Improver | `POST /improve`, `GET /improvements`, `GET /improvements/:id`, `DELETE /improvements/:id` |
| Brand voices | full CRUD at `/brand-voices` |
| Usage | `GET /usage/summary` |
| Exports | `GET /content/:id/export?format=pdf\|docx\|markdown` |

## 7. Repository layout

```
MagnaCMS/
├── README.md                  # this file
├── ARCHITECTURE.md            # key trade-offs + cost estimate
├── DEVLOG.md                  # running journal of decisions and progress
├── docker-compose.yml         # local-dev orchestration
├── .env.example               # environment template
├── .github/workflows/         # CI pipelines
├── backend/                   # FastAPI service
├── frontend/                  # Next.js App Router
└── infra/                     # AWS CDK in TypeScript
```

## 8. Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `AI_PROVIDER_MODE` | yes | `openai` | `openai` / `bedrock` / `mock` |
| `OPENAI_API_KEY` | yes (unless mode=mock) | — | OpenAI key, prepaid |
| `OPENAI_TEXT_MODEL` | no | `gpt-5.4-mini-2026-03-17` | Pinned text model |
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

```bash
# Backend
cd backend && uv run pytest --cov=app --cov-fail-under=80

# Frontend
cd frontend && pnpm test --run

# E2E (Playwright)
cd frontend && pnpm playwright test
```

## 10. Deployment

Infrastructure is defined in [`infra/`](./infra/) using AWS CDK in TypeScript. Five stacks compose linearly:

| Stack | Owns |
|---|---|
| `magnacms-dev-network` | VPC + 2 AZs (public subnets only) + RDS/Redis security groups |
| `magnacms-dev-data` | RDS Postgres, ElastiCache Serverless Redis, S3 images bucket, Secrets Manager (JWT + OpenAI key) |
| `magnacms-dev-compute` | ECR repo, App Runner backend service, IAM roles, Fargate task definition for migrations |
| `magnacms-dev-edge` | Amplify hosting app (CloudFront-for-images deferred to Phase 5; see [DEVLOG.md](./DEVLOG.md)) |
| `magnacms-dev-observability` | CloudWatch log groups with 14-day retention |

### First deploy (manual)

See [`infra/DEPLOY.md`](./infra/DEPLOY.md) for the 11-step runbook. Highlights:

```bash
aws configure
cd infra && npm ci
npx cdk bootstrap aws://<account>/us-east-1
npx cdk deploy --all -c env=dev
# Paste OpenAI API key into Secrets Manager
# Run migrations as one-off Fargate task
# Smoke-test /api/v1/health
# IP-identity preflight (DEPLOY.md step 8 — critical)
```

### Subsequent deploys (automatic)

`.github/workflows/deploy.yml` is `workflow_dispatch`-only until the first manual deploy + IP-identity preflight pass. After that, flip the trigger to `on: push: main` for auto-deploy on backend changes. The workflow uses OIDC-assumed roles (no long-lived AWS keys in GitHub Secrets).

### CI gates (no AWS touch)

| Workflow | Triggers on | Runs |
|---|---|---|
| [`backend-ci`](./.github/workflows/backend-ci.yml) | `backend/**` changes | uv sync, ruff, mypy, alembic upgrade, pytest |
| [`frontend-ci`](./.github/workflows/frontend-ci.yml) | `frontend/**` changes | pnpm install, lint, prettier, tsc, vitest, next build |
| [`infra-ci`](./.github/workflows/infra-ci.yml) | `infra/**` changes | npm ci, jest snapshots, `cdk synth --all -c env=dev` |

### Teardown

```bash
cd infra && npx cdk destroy --all -c env=dev
# Plus delete the Amplify app manually from console (CDK has trouble with
# Amplify apps connected to GitHub)
```

## 11. Architecture decisions

Detailed in [`ARCHITECTURE.md`](./ARCHITECTURE.md). Headlines:

- **OpenAI direct over AWS Bedrock** — one key covers text + image, no Anthropic use-case form, no Nova Canvas LEGACY/EOL story.
- **No VPC connector on App Runner** — keeps AWS APIs and OpenAI reachable without NAT Gateway.
- **Public RDS with strict SG** — explicit IP allowlist beats VPC complexity for the current scope.
- **Custom JWT over Cognito** — full control over refresh rotation + Redis blocklist; smaller IAM surface.
- **Non-streaming content generation** — structured JSON outputs don't stream cleanly; staged loading UI gives the perceived-performance benefit without the bug surface.

## 12. Development log

See [`DEVLOG.md`](./DEVLOG.md) — an ongoing journal of decisions, trade-offs, and progress (newest entries first). Includes actual elapsed time per phase as the project moves forward.

## 13. License

[MIT](./LICENSE).
