# MagnaCMS — AI Content Marketing Suite

A production-grade SaaS that helps marketers generate, manage, and improve marketing content using AI. Every generated piece can be paired with an AI-generated image in one flow.

> **Status:** in active development. The repo is functional from day one — see the dev log for what works today vs. what's next.

[![Backend CI](https://github.com/Eslam93/MagnaCMS/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/Eslam93/MagnaCMS/actions/workflows/backend-ci.yml) [![Frontend CI](https://github.com/Eslam93/MagnaCMS/actions/workflows/frontend-ci.yml/badge.svg)](https://github.com/Eslam93/MagnaCMS/actions/workflows/frontend-ci.yml) [![Infra CI](https://github.com/Eslam93/MagnaCMS/actions/workflows/infra-ci.yml/badge.svg)](https://github.com/Eslam93/MagnaCMS/actions/workflows/infra-ci.yml) ![License](https://img.shields.io/badge/license-MIT-blue)

---

## 1. Live demo

| | |
|---|---|
| Backend API | <https://grsv8u4uit.us-east-1.awsapprunner.com> (health: `/api/v1/health`) |
| API docs | <https://grsv8u4uit.us-east-1.awsapprunner.com/docs> (Swagger UI — exposed in `local` and `dev` envs only; `staging`/`production` hide `/docs`, `/redoc`, and `/openapi.json`) |
| Frontend | _Coming up — Amplify zip awaiting one-click upload._ Until then, run locally and point it at the deployed API via `NEXT_PUBLIC_API_BASE_URL`. |
| Demo credentials | `demo@magnacms.dev` / `DemoPass123` |

The demo account is seeded with one brand voice, three content pieces (blog / LinkedIn / email), one image per piece, and one improvement so the dashboard and detail views render real rows immediately. Seed it from scratch with `python -m app.scripts.seed` from `backend/`.

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
| Cache / rate limit / idempotency | Redis 7 _(plumbed in `.env.example`; backend runs with the in-memory fallback today — `USE_REDIS=false`. ElastiCache provisioning is deferred until the VPC-connector + refresh-token-blocklist work in Phase 11.)_ |
| AI — text | OpenAI `gpt-5.4-mini-2026-03-17` |
| AI — image | OpenAI `gpt-image-1` |
| Object storage | S3 bucket provisioned (BlockPublic + SSE) _(generated images currently live on the App Runner local disk via `IImageStorage` → `LocalImageStorage`; the S3 + CloudFront adapter swap lands with the next deploy batch — see [`SLICE_PLAN.md`](./SLICE_PLAN.md) §4.)_ |
| Auth | Custom JWT (httpOnly refresh cookie + rotation + Origin-based CSRF guard) |
| Hosting | AWS App Runner (backend) + Amplify Hosting (frontend) + RDS Postgres _(ElastiCache Serverless Redis lights up with Phase 11 — wired in NetworkStack, not yet provisioned.)_ |
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

First-time database setup + a seeded demo account:

```bash
docker-compose exec backend alembic upgrade head
docker-compose exec backend python -m app.scripts.seed
```

## 5. Architecture

Target architecture (CloudFront + Redis are the next-batch additions — see the caveats in §3):

```
Browser
  │
  ├─── app.<domain> ────────→ Amplify Hosting (Next.js SSR + static assets)
  │                              │
  │                              ▼
  │                          api calls to api.<domain>
  │
  └─── images.<domain> ────→ CloudFront ──→ S3 (private generated images)
                              (today: images served by App Runner's
                               `/local-images` static mount until the
                               S3 adapter ships in the deploy batch)

api.<domain>
  │
  ▼
App Runner — FastAPI containers (auto-scale, PUBLIC egress, no VPC connector)
  │
  ├──→ RDS Postgres (public endpoint; SG open on 5432, gated by `rds.force_ssl=1` + strong auto-generated password — App Runner's egress prefix list isn't stable enough to allowlist)
  ├──→ ElastiCache Redis (rate limit, cache, idempotency, refresh-token blocklist)
  │       (today: in-memory fallback — USE_REDIS=false until Phase 11)
  ├──→ OpenAI API (gpt-5.4-mini text, gpt-image-1 image)
  └──→ S3 (target; today: local-disk via IImageStorage protocol)
```

Full rationale and key trade-offs: [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## 6. API documentation

FastAPI generates an OpenAPI 3.1 spec from the route signatures. The
live UI is **only exposed in `local` and `dev`** environments — the
`staging` and `production` builds hide `/docs`, `/redoc`, and
`/openapi.json` so the API surface isn't enumerable from the public
internet (see [`app/main.py`](./backend/app/main.py)).

- **Local / dev only:**
  - Swagger UI: `<api-url>/docs`
  - ReDoc: `<api-url>/redoc`
  - Raw spec: `<api-url>/openapi.json`
- **Staging / production:** live docs are disabled. Dump the spec from
  the source tree instead:

  ```bash
  uv run python -c "import json; from app.main import app; \
    print(json.dumps(app.openapi(), indent=2))" > openapi.json
  ```

  Load the resulting `openapi.json` into a local Swagger viewer or any
  OpenAPI tool.

### Available today

| Group | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me` |
| Content | `POST /content/generate` (blog post, LinkedIn post, email, ad copy), `GET /content`, `GET /content/:id`, `DELETE /content/:id` (soft delete), `POST /content/:id/restore` (24-hour window) |
| Images | `POST /content/:id/image` (generate or regenerate), `GET /content/:id/images` (every version, newest first) |
| Improver | `POST /improve` (analyze → rewrite), `GET /improvements`, `GET /improvements/:id`, `DELETE /improvements/:id` |
| Brand voices | `GET /brand-voices`, `POST /brand-voices`, `GET /brand-voices/:id`, `PATCH /brand-voices/:id`, `DELETE /brand-voices/:id` |
| System | `GET /health` (always on); `GET /openapi.json`, `GET /docs`, `GET /redoc` (local/dev only — gated in `app/main.py`) |

### Planned

| Group | Endpoints |
|---|---|
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

## 9. Running tests & local CI parity

The CI workflows (`.github/workflows/backend-ci.yml`, `frontend-ci.yml`,
`infra-ci.yml`) run more than just the test suites — they also gate on
**formatting** (`ruff format --check`, `prettier --check`), **type-checks**,
**coverage thresholds**, and the **production build**. Run the full set
locally before pushing to avoid the "tests passed locally but CI failed
on prettier" trap:

```bash
# Backend — mirrors backend-ci.yml exactly
cd backend
uv run ruff check .
uv run ruff format --check .            # format gate (CI fails if dirty)
uv run mypy app
uv run pytest --cov=app --cov-fail-under=80   # 80% coverage gate
# OpenAPI spec must be consumable by the frontend's codegen:
uv run python -c "import json; from app.main import app; \
  json.dump(app.openapi(), open('openapi-tmp.json', 'w'))"
npx openapi-typescript@7.4 openapi-tmp.json -o /dev/null
rm openapi-tmp.json

# Frontend — mirrors frontend-ci.yml exactly
cd frontend
pnpm install --frozen-lockfile
pnpm lint
pnpm format:check                       # format gate (CI fails if dirty)
pnpm typecheck
pnpm test
pnpm build                              # next build must succeed

# Infra — mirrors infra-ci.yml exactly
cd infra
npm ci
npm run build
npm test
```

Fix surfaces:

| If this fails | Run |
|---|---|
| `ruff format --check` | `uv run ruff format .` |
| `pnpm format:check` | `pnpm format` |
| `pnpm lint` (auto-fixable) | `pnpm lint --fix` |

Playwright E2E (`@playwright/test` + a happy-path spec) is on the backlog
but not wired yet — see [the open backlog](https://github.com/Eslam93/MagnaCMS/issues/86).

## 10. Deployment

Infrastructure is defined in [`infra/`](./infra/) using AWS CDK in TypeScript. Five stacks compose linearly:

| Stack | Owns |
|---|---|
| `magnacms-dev-network` | VPC + 2 AZs (public subnets only) + RDS/Redis security groups |
| `magnacms-dev-data` | RDS Postgres, S3 images bucket, Secrets Manager (JWT + OpenAI key). ElastiCache Serverless Redis was previously here but is currently dropped pending the Phase-11 VPC-connector work. |
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
- **Public RDS, SG open on 5432, gated by TLS + strong password** — App Runner has no stable egress prefix list to allowlist, so security relies on `rds.force_ssl=1` + the auto-generated Secrets-Manager-managed password.
- **Custom JWT over Cognito** — full control over refresh rotation + Redis blocklist; smaller IAM surface.
- **Non-streaming content generation** — structured JSON outputs don't stream cleanly; staged loading UI gives the perceived-performance benefit without the bug surface.

## 12. Development log

See [`DEVLOG.md`](./DEVLOG.md) — an ongoing journal of decisions, trade-offs, and progress (newest entries first). Includes actual elapsed time per phase as the project moves forward.

## 13. License

[MIT](./LICENSE).
