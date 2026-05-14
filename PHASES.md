# Phases — AI Content Marketing Suite

This document breaks the work in `PROJECT_BRIEF.md` into 13 phases (0–12) plus a **Prerequisites** section that must be completed before Day 1. Each phase contains atomic tasks sized to be completed in a single PR.

**Conventions:**
- Task IDs follow `P<phase>.<n>` (e.g. `P3.5`). Prerequisites use `P-1.<n>`.
- Every task has acceptance criteria. A task is **done** when all criteria are met AND the brief's section §15 "Definition of Done per feature" is satisfied.
- References point back to `PROJECT_BRIEF.md` sections.
- Dependencies are noted where a task must wait on another.

**Status legend (for the GitHub Project board):**
- 📋 Todo · 🚧 In Progress · 👀 In Review · ✅ Done · ❌ Cut (per cut line)

---

## Prerequisites — Before Day 1

**Goal:** eliminate the AI-provider dependencies that can silently delay the build.

### P-1.1 — Verify OpenAI API access (✅ done 2026-05-14)
- [x] OpenAI API key funded ($8+ on account)
- [x] $25/month hard usage cap set in OpenAI console (recommended; prevents runaway loops in dev)
- [x] Text smoke call against `gpt-5.4-mini-2026-03-17` returns 200
- [x] Image smoke call against `gpt-image-1` (quality `low`, 1024×1024) returns a valid PNG
- [x] Verified model IDs recorded in `.env.example` (P0.3 also captures this)
- **Why first:** an unfunded key, a missing model, or an unverified billing setup would stall the entire week on Day 1. Five-minute task that prevents a multi-day risk.
- **Alternative provider path (documented, not required):** if `AI_PROVIDER_MODE=bedrock` is ever activated, the team must enable Bedrock model access in `us-east-1` for Claude Sonnet 4.5 via the `us.anthropic.claude-sonnet-4-5-20250929-v1:0` inference profile (not the bare ON_DEMAND model ID, which is unsupported) plus Nova Canvas (`amazon.nova-canvas-v1:0`, `LEGACY`, EOL 2026-09-30). Anthropic-model access also requires submitting the "Anthropic use case details" form.
- **Ref:** brief §2 AI text/image, §11 IAM

---

## Phase 0 — Bootstrap (Day 1)

**Goal:** repo and local-dev skeleton ready. No app code yet.

### P0.1 — Monorepo structure
- [ ] `backend/`, `frontend/`, `infra/` top-level directories created
- [ ] Top-level `README.md` with project name + status badge placeholders
- [ ] `.gitignore` covering Python, Node, CDK
- [ ] LICENSE file (MIT or similar)
- **Ref:** brief §4

### P0.2 — Docker Compose for local dev
- [ ] `docker-compose.yml` with services: `postgres:16`, `redis:7-alpine`, `backend` (stub), `frontend` (stub)
- [ ] Postgres seeded with empty `app` database on first run
- [ ] Health checks on postgres and redis
- [ ] `docker-compose up` succeeds without app code
- **Ref:** brief §9

### P0.3 — Environment variable scaffold
- [ ] `.env.example` at repo root with the complete variable set from brief §9
- [ ] Documented in README's quickstart section
- [ ] `.env` gitignored
- **Ref:** brief §9

### P0.4 — GitHub Actions CI skeletons
- [ ] `.github/workflows/backend-ci.yml` runs on PR + push to main, currently just lints a placeholder file
- [ ] `.github/workflows/frontend-ci.yml` same
- [ ] Both pass on first push
- **Ref:** brief §10

### P0.5 — Documentation seeds
- [ ] `README.md` outline with all 14 sections from brief §16 stubbed
- [ ] `PROJECT_BRIEF.md` committed to repo
- [ ] `PHASES.md` committed to repo
- [ ] `ARCHITECTURE.md` stub created
- **Ref:** brief §16

### P0.6 — Branch protection
- [ ] `main` branch protected: requires PR, requires CI green, no direct push
- [ ] Configured in GitHub repo settings
- **Ref:** working agreement in `KICKOFF_PROMPT.md`

### P0.7 — Verify local-dev one-command bootstrap
- [ ] After P0.1–P0.6 are merged, a fresh clone + `cp .env.example .env` (with `OPENAI_API_KEY` + `JWT_SECRET` filled — AWS creds optional for local) + `docker-compose up` brings everything up without error
- [ ] Document the exact 5 commands in README "Quick start"
- [ ] No silent failures in service logs (Postgres healthy, Redis healthy, backend stub responds to `/health`, frontend stub serves)
- **Ref:** brief §9

---

## Phase 1 — Backend Foundations (Days 2–4)

**Goal:** FastAPI app skeleton, full database schema, auth working end-to-end, provider abstractions stubbed.

### P1.1 — FastAPI application skeleton
- [ ] `backend/app/main.py` with FastAPI app, routers v1 mount at `/api/v1`
- [ ] **CORS middleware: explicit allowlist for frontend origins (local + Amplify domain), `allow_credentials=True`, no wildcard, OPTIONS handled, exposed headers include `X-Request-ID`**
- [ ] `app/core/config.py` with `pydantic-settings`, fail-fast env validation
- [ ] `app/core/logging.py` with structlog, JSON output, includes request_id + user_id
- [ ] `app/core/exceptions.py` with `AppException` hierarchy + FastAPI handlers, consistent error envelope
- [ ] `app/middleware/request_id.py` generates/propagates X-Request-ID header
- [ ] `pyproject.toml` with uv, Ruff, mypy, pytest configured
- [ ] `Dockerfile` multi-stage, non-root user
- [ ] `GET /api/v1/health` returns `{ status: "ok", version, dependencies }`
- **Ref:** brief §4, §8 (NFRs)

### P1.2 — SQLAlchemy + Alembic setup
- [ ] Async SQLAlchemy 2.0 engine with `asyncpg`
- [ ] `app/db/session.py` with session factory + dependency
- [ ] `app/db/base.py` with declarative base + common mixin (id UUID, timestamps)
- [ ] Alembic initialized, env.py wired to async engine
- [ ] Connection pool configured (pool_size=5, max_overflow=10)
- **Ref:** brief §5

### P1.3 — Database models
- [ ] `User`, `RefreshToken`, `BrandVoice`, `ContentPiece` (incl. `rendered_text` NOT NULL + `result_parse_status` enum), `GeneratedImage`, `Improvement`, `UsageEvent` per brief §5
- [ ] Soft-delete mixin (`deleted_at`) on appropriate tables
- [ ] All indexes per brief §5
- [ ] GIN full-text index on `content_pieces.rendered_text`
- **Ref:** brief §5

### P1.4 — Initial migration
- [ ] `alembic revision --autogenerate -m "baseline"` produces a clean migration
- [ ] `alembic upgrade head` runs cleanly on empty DB
- [ ] Migration reviewed line-by-line (autogenerate is not perfect)
- **Ref:** brief §5

### P1.5 — Auth: registration, login, password handling
- [ ] `POST /auth/register` — validates email + password strength, hashes with bcrypt (cost 12), creates user
- [ ] `POST /auth/login` — verifies password, issues access JWT + refresh token (set as httpOnly Secure SameSite=Lax cookie)
- [ ] `GET /auth/me` — returns current user
- [ ] Tests: register success, register duplicate email, login success, login wrong password
- **Ref:** brief §6 Auth section

### P1.6 — Auth: refresh + logout + rotation
- [ ] `POST /auth/refresh` — single-use rotation, old token marked `revoked_at` in DB, new pair issued
- [ ] `POST /auth/logout` — revokes refresh, clears cookie
- [ ] Refresh tokens stored as SHA-256 hash, never as plaintext
- [ ] Tests: refresh success, refresh with revoked token fails, logout invalidates token
- [ ] *Note: Redis blocklist deferred to Phase 11. DB `revoked_at` is sufficient for MVP.*
- **Ref:** brief §6 Auth

### P1.7 — Provider abstractions
- [ ] `app/providers/llm/base.py` with `ILLMProvider` protocol (generate + generate_with_retry methods)
- [ ] `app/providers/image/base.py` with `IImageProvider` protocol
- [ ] **`OpenAIChatProvider` — full `openai` SDK implementation** using `gpt-5.4-mini-2026-03-17`, `response_format: { type: "json_schema", strict: true }` per content type, retry with exponential backoff on 5xx/429, structured logging of model + input/output tokens + cost
- [ ] **`OpenAIImageProvider` — full implementation** for `gpt-image-1`, configurable quality (low/medium/high), 1024×1024 default, returns base64 bytes for downstream S3 upload
- [ ] **`MockLLMProvider` — fully implemented**, returns canned valid JSON per content type (blog/linkedin/ad/email/image-prompt/improver), used in tests and demoable to reviewers without any API key
- [ ] **`MockImageProvider` — fully implemented**, returns a deterministic placeholder PNG (rendered from text), used in tests and the `mock` provider mode
- [ ] `BedrockClaudeProvider`, `BedrockNovaCanvasProvider` — stubbed (raise `NotImplementedError`) as documented alternatives; full impl deferred unless `AI_PROVIDER_MODE=bedrock` is activated
- [ ] `AnthropicDirectProvider` — not implemented; remove `anthropic_direct` from `AI_PROVIDER_MODE` documentation (the brief now documents only `openai | bedrock | mock`)
- [ ] Factory selects provider based on `AI_PROVIDER_MODE` env var (default `openai`)
- [ ] Retry with exponential backoff (max 3 attempts) on 5xx and 429
- **Ref:** brief §2, §9 fallback modes

### P1.8 — Auth unit + integration tests
- [ ] pytest fixtures: test DB (transactional rollback), test client, factory for users
- [ ] Coverage on auth_service ≥ 85%
- [ ] One integration test per auth endpoint
- **Ref:** brief §8 Reliability

### P1.9 — Security headers + basic auth rate limit
- [ ] Security headers middleware applies: `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, baseline `Content-Security-Policy`
- [ ] Basic in-memory rate limit on `/auth/login` and `/auth/register` (10/min by IP) — full Redis-backed sliding window arrives in P11.3
- [ ] 429 responses include `Retry-After` header
- [ ] Rationale: app will be publicly live ~15+ days before P11 hardening; auth endpoints must not be unprotected during that window.
- **Ref:** brief §8 Security, §14

---

## Phase 2 — Thin Vertical Slice Deployed to AWS (Days 5–6)

**Goal:** production is online and responding before any business logic ships. This is the line in the sand. **Split across two days because 9 CDK-heavy tasks plus first-deploy plus Amplify in one day is wishful thinking.**

**Day 5 target:** Network + Data + Compute stacks deployed, App Runner serving `/health` from a public URL, one successful OpenAI invocation from production (logged with model + tokens + cost).

**Day 6 target:** Edge stack (Amplify + CloudFront) live, deploy workflow automated, frontend on Amplify with **real auth wired end-to-end** to the App Runner API (this surfaces CORS/cookie issues immediately, which is the entire point of deploying early).

### P2.1 — CDK project bootstrap
- [ ] `infra/` with CDK in TypeScript initialized
- [ ] `cdk.json`, `bin/`, `lib/`, `package.json` configured
- [ ] CDK app entry exports stacks for env-aware deployment (dev, prod)
- **Ref:** brief §11

### P2.2 — `NetworkStack`
- [ ] VPC with 2 AZs, public subnets only (no private subnets, no NAT)
- [ ] Security group for RDS (inbound 5432 from App Runner outbound IP prefix list + dev IP)
- [ ] Security group for ElastiCache (similar)
- **Ref:** brief §11 networking decision

### P2.3 — `DataStack`
- [ ] RDS Postgres `db.t4g.micro`, publicly accessible, encrypted at rest, automated backups (prod only)
- [ ] ElastiCache Serverless Redis cluster
- [ ] S3 bucket `ai-content-images-{env}` with blocked public access + Origin Access Control prep
- [ ] Secrets Manager: `jwt-secret`, `db-password`, `app-runner-env`
- **Ref:** brief §11 DataStack

### P2.4 — `ComputeStack`
- [ ] ECR repository for backend
- [ ] App Runner service — **no VPC connector**, public egress, min 1 / max 3 instances
- [ ] IAM role: scoped permissions per brief §11 ComputeStack
- [ ] Health check `/api/v1/health`
- [ ] Env vars injected from Secrets Manager
- **Ref:** brief §11 ComputeStack

### P2.5 — `EdgeStack`
- [ ] Amplify Hosting app connected to GitHub repo, auto-deploy on push to `main`
- [ ] `amplify.yml` build settings
- [ ] CloudFront distribution for images S3 bucket with Origin Access Control
- [ ] (Optional, skip if no domain) ACM cert + Route53 alias
- **Ref:** brief §11 EdgeStack

### P2.6 — `ObservabilityStack`
- [ ] CloudWatch log groups for App Runner, retention 14 days (dev) / 30 days (prod)
- **Ref:** brief §11 ObservabilityStack

### P2.7 — First production deployment (Day 5 target)
- [ ] `cdk deploy --all` succeeds
- [ ] App Runner serving FastAPI behind HTTPS
- [ ] `/health` returns 200 from public URL
- [ ] One test OpenAI invocation succeeds from App Runner (`gpt-5.4-mini-2026-03-17` chat completion, logged with model + tokens + cost) — API key already verified in P-1.1, injected via Secrets Manager
- [ ] Alembic migration runs as one-off task
- [ ] Live URL recorded in README
- **Ref:** brief §11, §12 Day 5

### P2.8 — Deploy workflow
- [ ] `.github/workflows/deploy.yml` triggered on push to `main`
- [ ] Builds backend Docker image, pushes to ECR with `latest` + SHA tags
- [ ] Triggers App Runner deployment, waits for healthy
- [ ] Runs Alembic migration as a one-off Fargate task or App Runner pre-deploy hook
- [ ] Smoke-tests `/health` after deploy
- **Ref:** brief §10

### P2.9 — Frontend on Amplify with real auth wired end-to-end
- [ ] Next.js 15 + Tailwind + shadcn/ui scaffolded
- [ ] Connects to deployed API for `/health`
- [ ] **Real auth flow:** login page → API call → access token + httpOnly refresh cookie set → protected page redirects unauth users → logout works
- [ ] CORS verified working between Amplify domain and App Runner domain with credentials (this is the explicit goal — surface cookie/SameSite/CORS bugs on Day 6 not Day 8)
- [ ] Amplify auto-deploys on push to main
- [ ] Live frontend URL recorded in README
- **Ref:** brief §12 Day 5–6, brief §8 Security

### P2.10 — Sentry basic SDK init (backend + frontend)
- [ ] Backend: `sentry-sdk[fastapi]` installed, init in `main.py`, DSN from env var (`SENTRY_DSN`), captures unhandled exceptions
- [ ] Frontend: `@sentry/nextjs` installed, init in instrumentation file
- [ ] Both behind `SENTRY_DSN` env var — silently noop if unset (for local dev)
- [ ] PII scrubbing minimal here; full polish (source maps, custom scrubbing) lands in P11.5
- [ ] Smoke test: throw a test error in dev, verify it lands in Sentry
- **Rationale:** moved from P11.5 — the app is live ~15+ days before Phase 11; flying blind on errors that long is unacceptable.
- **Ref:** brief §8 Observability

---

## Phase 3 — Core Content Generation (Days 7–8)

**Goal:** the heart of the product. All 4 content types generating cleanly.

### P3.1 — Prompt module infrastructure
- [ ] `app/prompts/` with module per content type
- [ ] Each module exports `build(context) -> (system_prompt, user_prompt)`, `PROMPT_VERSION` constant, `parse(raw) -> ResultSchema`, `render(result) -> rendered_text`
- [ ] Loader looks up the right module by `content_type`
- **Ref:** brief §7

### P3.2 — Blog post: prompt + schema + renderer
- [ ] Prompt verbatim from brief §7.1
- [ ] Pydantic `BlogPostResult` schema matching the JSON contract
- [ ] Markdown renderer producing the H1/H2 structure
- [ ] Unit tests on parser (good JSON, malformed JSON, missing fields)
- **Ref:** brief §7.1

### P3.3 — OpenAI chat provider full implementation
- [ ] `OpenAIChatProvider.generate()` uses the official `openai` Python SDK against `gpt-5.4-mini-2026-03-17`
- [ ] Stage-1 calls use `response_format: { type: "json_schema", json_schema: {...}, strict: true }` per content type to guarantee schema-valid output at the API boundary
- [ ] Stage-2 retry call drops the schema constraint and uses a corrective system prompt (per brief §7.0)
- [ ] Logs `model`, `prompt_tokens`, `completion_tokens`, `cost_usd` (computed from a static price table), `latency_ms` per call
- [ ] Retry with exponential backoff on `429` (rate limit) and `5xx`, max 3 attempts, respects `Retry-After` header when present
- [ ] Timeout enforced (default 60s, configurable via `OPENAI_TIMEOUT_SECONDS`)
- **Ref:** brief §2 AI text, §7.0

### P3.4 — Three-stage JSON parse fallback service
- [ ] `ContentGenerationService.generate()` implements the brief §7.0 three-stage fallback
- [ ] Attempt 1: parse, validate
- [ ] Attempt 2: retry with corrective prompt
- [ ] Attempt 3: store raw, set `result_parse_status = failed`
- [ ] On `failed`: structlog warning with `event=parse_failed` + content_id + content_type (auto-flows to Sentry via the FastAPI integration set up in P2.10)
- [ ] Unit tests cover all three paths
- **Ref:** brief §7.0

### P3.5 — `POST /content/generate` endpoint
- [ ] Pydantic request validation
- [ ] Auth required
- [ ] Returns `{ content_id, result, rendered_text, usage, result_parse_status }`
- [ ] Persists to `content_pieces` with prompt snapshot
- [ ] Logs usage (inline on content row in this phase; separate `usage_events` table arrives Phase 9)
- [ ] Integration test: end-to-end with mock provider
- **Note:** idempotency key support arrives uniformly in P11.2 (avoid partial implementation here).
- **Ref:** brief §6 Content, §7.0

### P3.6 — LinkedIn post: prompt + schema + renderer
- Same structure as P3.2, prompt from brief §7.2
- **Ref:** brief §7.2

### P3.7 — Ad copy: prompt + schema + renderer
- Same structure, prompt from brief §7.3
- **Ref:** brief §7.3

### P3.8 — Email: prompt + schema + renderer
- Same structure, prompt from brief §7.4
- **Ref:** brief §7.4

### P3.9 — Integration tests across all 4 types
- [ ] One e2e test per content type with mock provider returning valid JSON
- [ ] One e2e test of the JSON parse fallback path (mock returns invalid JSON twice)
- [ ] One e2e test of full failure (mock returns invalid 3x) — verifies `result_parse_status = failed`
- **Ref:** brief §7

### P3.10 — OpenAPI spec polish for content endpoints
- [ ] All response models typed with Pydantic, present in `/docs`
- [ ] Examples added with `examples` parameter
- [ ] Error responses documented with proper status codes
- **Ref:** brief §6, §8 Documentation

---

## Phase 4 — Frontend Core: Auth + Generation UX (Days 9–10)

**Goal:** the user-facing app can be used end-to-end for content generation against the deployed API.

### P4.1 — Frontend foundations
- [ ] shadcn/ui setup, Tailwind theme tokens, font (Inter or similar)
- [ ] Dark mode via `next-themes`
- [ ] Toast provider (sonner)
- [ ] React Hook Form + Zod resolver wired
- [ ] TanStack Query provider with sensible defaults (`staleTime`, `gcTime`, retry)
- **Ref:** brief §2, §8 UX

### P4.2 — Typed API client from OpenAPI
- [ ] `openapi-typescript` generates types from deployed `/openapi.json`
- [ ] `openapi-fetch` wrapper with auth header injection
- [ ] 401 interceptor triggers refresh flow
- [ ] Script in `package.json`: `pnpm gen:api`
- **Ref:** working agreement

### P4.3 — Auth client + pages
- [ ] Login page with email/password form, validation, error display
- [ ] Register page same
- [ ] Auth context/store holding the access token in memory (no localStorage)
- [ ] Refresh flow: on 401, call `/auth/refresh`, retry original request
- [ ] On refresh failure → redirect to login
- [ ] `credentials: 'include'` configured for cookie flow
- **Ref:** brief §6 Auth

### P4.4 — Protected layout
- [ ] Layout component with sidebar nav (Dashboard, Generate, Improve, Brand voices, Usage, Settings)
- [ ] Guard hook: redirect unauthenticated users
- [ ] User menu with logout
- [ ] Responsive: sidebar collapses to hamburger on mobile
- **Ref:** brief §4, §8 Accessibility

### P4.5 — Generate page: form
- [ ] Content type selector (segmented control: Blog, LinkedIn, Ad copy, Email)
- [ ] Topic input (required)
- [ ] Tone input
- [ ] Audience input
- [ ] Brand voice dropdown (stub — populated in Phase 8)
- [ ] Submit calls `/content/generate`
- **Ref:** brief §6 Content

### P4.6 — Staged loading UI
- [ ] On submit, show staged messages cycling every ~1.5s: "Analyzing topic..." → "Drafting..." → "Polishing..."
- [ ] Use skeleton placeholders for the result area
- [ ] Cancel button (aborts request)
- **Ref:** brief §6 Content note, §8 Performance

### P4.7 — Result rendering per content type
- [ ] Blog: rendered markdown with `react-markdown`, separate cards for sections
- [ ] LinkedIn: post preview as it would look in feed
- [ ] Ad copy: 3 variant cards side-by-side
- [ ] Email: subject + preview text + body in a faux email shell
- [ ] All views show: copy-to-clipboard button, "Generate image" button (Phase 5)
- **Ref:** brief §7 renderers

### P4.8 — Fallback-mode banner
- [ ] If response includes `result_parse_status: "failed"`, show a small non-blocking banner: "Generated in fallback mode — formatting may be inconsistent"
- **Ref:** brief §7.0

### P4.9 — Error states + retry
- [ ] Network errors caught, toast shown with retry action
- [ ] Rate limit (429) response shows "Slow down — try again in N seconds" toast
- [ ] Server errors (5xx) show "Something went wrong, we've been notified" with Sentry capture
- **Ref:** brief §8 UX

---

## Phase 5 — Image Generation (Days 11–13)

**Goal:** every generated piece can be paired with a relevant AI image; user can regenerate with different styles. **3 days, not 2 — image gen is the highest-variance work in the build (latency 8–15s, provider quirks, S3/CDN plumbing).**

### P5.1 — Image prompt builder
- [ ] Separate OpenAI chat call (`gpt-5.4-mini-2026-03-17`) using prompt from brief §7.5
- [ ] Takes content excerpt + style + content_type
- [ ] Returns `{ prompt, negative_prompt, style_summary }` (negative_prompt may be empty for `gpt-image-1`; folded into positive prompt as constraints)
- [ ] Validated as JSON with same three-stage fallback (graceful degrade = use a generic prompt template)
- **Ref:** brief §7.5

### P5.2 — OpenAI gpt-image-1 provider
- [ ] `OpenAIImageProvider.generate()` calls OpenAI `/v1/images/generations` for `gpt-image-1`
- [ ] Request body: `prompt`, `n=1`, `size=1024x1024`, `quality` from `OPENAI_IMAGE_QUALITY` (default `medium`; `low` in dev; `high` for hero shots)
- [ ] Decodes base64 image bytes from `data[0].b64_json` for downstream S3 upload
- [ ] Logs `model`, `prompt_hash`, `quality`, `cost_usd` (computed from a static price table — low $0.011, medium $0.042, high $0.167), `latency_ms`
- [ ] `gpt-image-1` does not expose a seed; reproducibility tracked via prompt hash + model + quality only
- [ ] Retry with exponential backoff on 429/5xx (max 3)
- **Ref:** brief §2 AI image

### P5.3 — S3 upload + CloudFront URL
- [ ] `ImageStorageService.upload(bytes, content_type) -> { s3_key, cdn_url }`
- [ ] UUID key under `images/{user_id}/{uuid}.png`
- [ ] Returns CloudFront URL using `IMAGES_CDN_BASE_URL`
- [ ] Local dev fallback: save to `/tmp/local-images/`, serve via FastAPI
- **Ref:** brief §11 S3, §9 local

### P5.4 — `POST /content/:id/image` endpoint
- [ ] Auth required, ownership check
- [ ] Calls image prompt builder, then image provider
- [ ] Persists row to `generated_images`, sets `is_current = true`, flips previous to `false`
- [ ] Returns the new image record
- [ ] Idempotency key supported
- **Ref:** brief §6 Images

### P5.5 — Frontend: image display on result
- [ ] "Generate image" button on result view
- [ ] Loading state while generating (`gpt-image-1` typical latency 5–10s)
- [ ] Image displayed alongside text in a responsive layout
- [ ] Click to enlarge (lightbox)
- **Ref:** brief §12 Day 11

### P5.6 — Alternative image provider (cut candidate)
- [ ] If retained: `BedrockNovaCanvasProvider` wired as a real impl (already stubbed in P1.7) and selectable via `provider` parameter on regenerate endpoint
- [ ] *Cut candidate (per cut line item #3) — `gpt-image-1` covers all 6 styles via prompt + quality tier alone. Default is to drop unless time permits.*
- **Ref:** brief §14 cut line

### P5.7 — Style picker
- [ ] 6 preset styles: `photorealistic`, `illustration`, `minimalist`, `3d_render`, `watercolor`, `cinematic`
- [ ] Frontend control on the result view (only visible after first image)
- [ ] Backend passes style into image prompt builder + provider config
- **Ref:** brief §7.5

### P5.8 — Regeneration flow
- [ ] Click regenerate → new `generated_images` row created
- [ ] Previous current image's `is_current` flipped to false
- [ ] UI optimistically shows loading, then swaps in new image
- **Ref:** brief §5

### P5.9 — Thumbnail strip of previous versions
- [ ] Simple horizontal row of small thumbnails below the current image (no lightbox, no expand-on-click)
- [ ] Endpoint `GET /content/:id/images` returns all versions
- [ ] Click a thumbnail → swaps it in as the displayed image (no modal)
- [ ] *Cut candidate (per cut line item #4) — keep it minimal, do not over-invest*
- **Ref:** brief §6 Images, §14

---

## Phase 6 — Dashboard & Content Management (Day 14)

**Goal:** all past generations browsable, searchable, deletable.

### P6.1 — List endpoint
- [ ] `GET /content` with pagination (`page`, `page_size`, default 20, max 100)
- [ ] Filter by `content_type`
- [ ] Full-text search via `q` parameter against `rendered_text`
- [ ] Returns `data`, `meta.pagination`
- **Ref:** brief §6 Content

### P6.2 — Detail endpoint
- [ ] `GET /content/:id` returns content + current image
- [ ] 404 on not found, 403 on wrong owner
- **Ref:** brief §6

### P6.3 — Soft delete + restore
- [ ] `DELETE /content/:id` sets `deleted_at`
- [ ] `POST /content/:id/restore` clears `deleted_at` if within 24h, 410 Gone otherwise
- **Ref:** brief §6

### P6.4 — Dashboard list page
- [ ] Card grid showing each content piece: type badge, title/topic, snippet from `rendered_text`, thumbnail of current image, date
- [ ] Search bar (debounced)
- [ ] Filter chips per content type
- [ ] Pagination controls
- [ ] Empty state with CTA: "Generate your first piece"
- [ ] Loading skeletons
- **Ref:** brief §8 UX, §12 Day 12

### P6.5 — Detail view
- [ ] Full rendered content
- [ ] Current image with regenerate + style picker
- [ ] Copy button, export buttons (Phase 9 functional, scaffold here), delete button
- [ ] Back to dashboard
- **Ref:** brief §6

### P6.6 — Delete with undo toast
- [ ] Delete triggers optimistic removal from UI + toast with "Undo" action (10s timer)
- [ ] Undo calls restore endpoint, content reappears
- **Ref:** brief §8 UX

---

## Phase 7 — Improver (Day 15)

**Goal:** users can paste text, pick a goal, get a refined version with explanation.

### P7.1 — Improver service (two-call chain)
- [ ] Call 1: analysis prompt from brief §7.6, returns `{ issues, planned_changes }`
- [ ] Call 2: rewrite prompt, returns `{ improved_text, explanation, changes_summary }`
- [ ] Same three-stage JSON fallback on both calls
- [ ] Goal-specific instructions injected per brief §7.6
- **Ref:** brief §7.6

### P7.2 — `POST /improve` endpoint
- [ ] Auth required
- [ ] **Non-streaming JSON response** — returns `{ improved_text, explanation, changes_summary }`. (SSE option dropped: optional complexity is a future bug; "Rewriting..." spinner is sufficient.)
- [ ] Persists to `improvements` table
- **Ref:** brief §6 Improver

### P7.3 — Improver list + detail + delete
- [ ] `GET /improvements` paginated, `GET /improvements/:id`, soft delete
- **Ref:** brief §6 Improver

### P7.4 — Improver frontend page
- [ ] Textarea for original text (with word count)
- [ ] Goal selector (radio: shorter / persuasive / formal / seo / audience_rewrite)
- [ ] "New audience" input that appears only for `audience_rewrite`
- [ ] Submit button
- **Ref:** brief §12 Day 13

### P7.5 — Side-by-side diff view
- [ ] Original and improved shown side-by-side on desktop, stacked on mobile
- [ ] Highlighted diff (use `diff-match-patch` or `react-diff-viewer`)
- [ ] Explanation bullets shown below
- [ ] Changes summary stats (length change %, tone shift)
- [ ] Copy button on the improved text
- **Ref:** brief §7.6

### P7.6 — Improver history
- [ ] Sidebar or section listing recent improvements
- [ ] Click to view past improvement
- **Ref:** brief §6

---

## Phase 8 — Brand Voice (Day 16)

**Goal:** users can save and reuse brand voice profiles across generations.

### P8.1 — CRUD endpoints
- [ ] `GET /brand-voices`, `POST /brand-voices`, `GET /brand-voices/:id`, `PATCH /brand-voices/:id`, `DELETE /brand-voices/:id`
- [ ] Ownership enforced
- **Ref:** brief §6 Brand voices

### P8.2 — Brand voices page
- [ ] List + create + edit + delete UI
- [ ] Form fields: name, description, tone descriptors (multi-input), banned words, sample text, target audience
- **Ref:** brief §5, §12 Day 14

### P8.3 — Integration into generate form
- [ ] Brand voice dropdown populated from API
- [ ] Selected voice's `id` sent in `/content/generate` body
- [ ] Optional preview chip showing the selected voice's name + tone
- **Ref:** brief §6, §7.7

### P8.4 — Brand voice block injection
- [ ] Backend service fetches selected brand voice and injects the block per brief §7.7 into the prompt
- [ ] Snapshot persisted with the content piece
- **Ref:** brief §7.7

### P8.5 — Seed script updated
- [ ] Default brand voice created in seed script
- [ ] Example content pieces use the brand voice
- **Ref:** brief §9 seed

---

## Phase 9 — Exports & Usage (Days 17–18)

**Goal:** users can export their content; usage is tracked and visible.

### P9.1 — PDF export
- [ ] `GET /content/:id/export?format=pdf` using WeasyPrint
- [ ] HTML template per content type
- [ ] Returns binary PDF or presigned S3 URL
- [ ] Frontend download button
- **Ref:** brief §6 Exports

### P9.2 — DOCX export
- [ ] Same endpoint with `format=docx`, using `python-docx`
- [ ] Style approximates the rendered HTML
- [ ] *Cut candidate #1 — drop first if behind*
- **Ref:** brief §6, §14

### P9.3 — Markdown export
- [ ] `format=markdown` returns `rendered_text` as a `.md` file download
- **Ref:** brief §6

### P9.4 — `usage_events` table + recording
- [ ] Split out from inline tracking on content/improvement rows
- [ ] Service writes a `UsageEvent` for every text_gen, image_gen, improve, image_regen, export
- [ ] Backfill script for existing rows (optional)
- **Ref:** brief §5

### P9.5 — `GET /usage/summary` endpoint
- [ ] Returns totals + by-type breakdown + last 30 days time series
- **Ref:** brief §6 Usage

### P9.6 — Usage page (frontend)
- [ ] One-page view with totals cards (total generations, total images, total tokens, total cost)
- [ ] By-type breakdown (small table or stacked bar)
- [ ] *Cut candidate #2 — drop the page, keep the endpoint, if behind*
- **Ref:** brief §12 Day 16, §14

---

## Phase 10 — Polish (Days 19)

**Goal:** the product feels finished.

### P10.1 — Error boundaries
- [ ] Global error boundary in Next.js app
- [ ] Section-level boundaries for risky areas (result rendering)
- [ ] Captured to Sentry (Phase 11) — for now, console
- **Ref:** brief §8 UX

### P10.2 — Toast notifications consistency
- [ ] Every mutation has a success or error toast
- [ ] Error toasts include actionable retry where possible
- **Ref:** brief §8 UX

### P10.3 — Empty states
- [ ] Dashboard empty → "Generate your first piece" with example button
- [ ] Brand voices empty → "Create your first brand voice"
- [ ] Improvements empty → "Improve your first piece"
- [ ] All have illustrations or icons
- **Ref:** brief §8 UX

### P10.4 — 404 and 500 pages
- [ ] Custom Next.js error pages with consistent design + back-to-home CTA
- **Ref:** brief §8 UX

### P10.5 — Dark mode polish
- [ ] All custom components tested in both themes
- [ ] Theme toggle in user menu
- [ ] Persists across sessions
- **Ref:** brief §8 UX

### P10.6 — Mobile responsive audit
- [ ] Every page tested at 375px width
- [ ] No horizontal scroll
- [ ] Tap targets ≥ 44px
- [ ] Sidebar collapses appropriately
- **Ref:** brief §8 UX

### P10.7 — Accessibility pass
- [ ] All interactive elements keyboard-accessible
- [ ] Focus indicators visible
- [ ] ARIA labels on icon-only buttons
- [ ] Contrast checked with axe DevTools
- [ ] One full keyboard-only walkthrough recorded
- **Ref:** brief §8 Accessibility

### P10.8 — Playwright E2E
- [ ] Happy path: register → generate blog post → generate image → see in dashboard → delete with undo
- [ ] Runs in CI on main
- [ ] *Cut candidate #8 — manual test if cutting*
- **Ref:** brief §8, §14

### P10.9 — Loading skeletons
- [ ] Replace remaining spinners with skeleton placeholders
- [ ] Match shape of the eventual content
- **Ref:** brief §8 UX

---

## Phase 11 — Production Hardening (Day 20)

**Goal:** Redis-backed rate limiting, idempotency, security headers, Sentry — all the "show I take this seriously" extras.

### P11.1 — Redis blocklist for refresh tokens
- [ ] Move from DB-only `revoked_at` to Redis SET with TTL = remaining refresh lifetime
- [ ] On refresh: check both DB and Redis
- [ ] Fallback: if `USE_REDIS=false`, DB-only behavior
- [ ] *Cut candidate #5 — DB-only is acceptable*
- **Ref:** brief §8 Security, §14

### P11.2 — Idempotency middleware
- [ ] FastAPI middleware reads `Idempotency-Key` header on `POST /content/generate`, `POST /content/:id/image`, `POST /improve`
- [ ] Stores response in Redis with key under namespace `idem:{user_id}:{key}`, 24h TTL
- [ ] Returns cached response on duplicate
- **Ref:** brief §6, §14

### P11.3 — Rate limiting tuned per endpoint
- [ ] Redis sliding window per user per endpoint
- [ ] Limits per brief §6
- [ ] 429 responses include `Retry-After` header
- [ ] *In-memory fallback when `USE_REDIS=false`*
- **Ref:** brief §6

### P11.4 — Circuit breaker on OpenAI provider
- [ ] Provider opens for 30s after 5 consecutive failures (429 + 5xx + timeout count toward the threshold)
- [ ] In open state, returns 503 with descriptive error and a `Retry-After: 30` header
- [ ] *Cut candidate #7 — keep retry+timeout only if cutting*
- **Ref:** brief §8 Reliability, §14

### P11.5 — Sentry polish (source maps + PII scrubbing)
- [ ] Basic SDK init already exists from P2.10 — this task is the polish layer
- [ ] Source maps uploaded on frontend build (via `@sentry/nextjs` webpack plugin)
- [ ] PII scrubbing rules added (email, IPs, custom user data)
- [ ] Performance monitoring enabled with conservative sample rate (~10%)
- [ ] Custom error fingerprinting for parse-failure events
- **Ref:** brief §2, §8 Observability

### P11.6 — CloudWatch alarm
- [ ] App Runner 5xx rate > 5% over 5 min triggers alarm
- [ ] Optional SNS topic with email subscription
- [ ] *Cut candidate #9*
- **Ref:** brief §11 ObservabilityStack, §14

### P11.7 — Security headers hardening
- [ ] Baseline security headers already applied in P1.9
- [ ] Tighten the Content-Security-Policy to a strict allowlist (script-src, style-src, img-src, connect-src)
- [ ] Test in production with Mozilla Observatory; target B+ or better
- [ ] Add `Permissions-Policy` to restrict unused browser features
- **Ref:** brief §8 Security

---

## Phase 12 — Finalization (Day 21)

**Goal:** ship the submission.

### P12.1 — README full polish
- [ ] All 14 sections from brief §16 present and complete
- [ ] Live URL, demo credentials prominently
- [ ] Screenshots or GIF
- [ ] Architecture diagram (ASCII or PNG)
- [ ] API docs link
- [ ] Environment variables table
- [ ] Deploy instructions
- **Ref:** brief §16

### P12.2 — ARCHITECTURE.md
- [ ] One page: stack decisions, key trade-offs (OpenAI direct vs Bedrock — chose OpenAI for zero model-access friction and a single key for text+image; App Runner vs Fargate; custom JWT vs Cognito; public RDS vs VPC connector), AWS cost estimate for the 7-day live window, what I'd build next
- **Ref:** brief §16

### P12.3 — OpenAPI doc review
- [ ] All endpoints documented with examples
- [ ] Error responses documented
- [ ] Tags grouped logically
- **Ref:** brief §6

### P12.4 — Demo seed quality
- [ ] Seed creates a polished demo: 1 user, 1 brand voice, 3-5 content pieces of varying types with images, 1 improvement
- [ ] All content reads well — not lorem ipsum
- [ ] First-60-seconds-feels-finished check
- **Ref:** brief §9

### P12.5 — Video script
- [ ] Follow brief §18 outline
- [ ] Rehearse twice
- **Ref:** brief §18

### P12.6 — Video recording + editing
- [ ] Screen recording of full demo per script
- [ ] Edit in 3-4 Claude Code workflow clips captured during development
- [ ] Aim for 7-8 minutes (within 5-10 min window)
- [ ] Upload, share link, add to README
- **Ref:** brief §18

### P12.7 — Final smoke test
- [ ] Live URL accessible
- [ ] Register a fresh account works
- [ ] Generate works end-to-end with image
- [ ] Improver works
- [ ] Export works
- [ ] No console errors
- **Ref:** brief §13

### P12.8 — Submission
- [ ] Live URL, GitHub repo URL, video URL all in one place
- [ ] Confirm 7-day live commitment
- [ ] Submit
- **Ref:** challenge brief

---

## Cut order reminder

When behind schedule, cut in this exact order (mirrors brief §14):

1. DOCX export (P9.2)
2. Usage page UI (P9.6 — keep endpoint)
3. Alternative image provider (P5.6 — Bedrock Nova Canvas wiring; keep `gpt-image-1` only)
4. Image version-history strip (P5.9)
5. Redis blocklist for refresh tokens (P11.1)
6. Idempotency middleware globally (keep on AI endpoints only — P11.2 partial)
7. Circuit breaker (P11.4)
8. Playwright E2E (P10.8)
9. CloudWatch custom alarms (P11.6)
10. One content type (drop ad copy: cut P3.7 + frontend for ad)
11. Brand voice (P8 — last to cut)

Never cut: auth, content generation, image generation, dashboard, improver, README, video.
