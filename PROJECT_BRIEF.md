# AI Content Marketing Suite — Project Brief

> **Purpose:** This is the source of truth for development. Claude Code should reference this throughout the build. When in doubt, follow what's here. When something is ambiguous, ask the user before deviating.

---

## 1. Product summary

A production-grade SaaS web app that helps marketers generate, manage, and improve marketing content using AI. Every generated piece can be paired with an AI-generated image in one flow.

Core flows:
1. **Generate** — pick a content type (blog, LinkedIn, ad, email), describe topic/tone/audience, get polished output
2. **Pair with image** — one click to auto-generate a matching image from the content
3. **Improve** — paste existing text, pick a goal, get a refined version with explanation
4. **Manage** — dashboard of all past generations with search, filter, export, delete
5. **Brand voice** — saved profiles that pre-fill style across generations

---

## 2. Tech stack (locked)

| Layer | Choice |
|---|---|
| Frontend | Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui + TanStack Query + Zod + React Hook Form |
| Backend | FastAPI + Python 3.12 + Pydantic v2 + SQLAlchemy 2.0 (async) + Alembic |
| Database | PostgreSQL 16 |
| Cache / rate limiting / idempotency | Redis 7 (production) with in-memory fallback (`USE_REDIS=false` for local/dev resilience) |
| AI — text (primary) | **OpenAI** — `gpt-5.4-mini-2026-03-17` (pinned for reproducibility), configured via `OPENAI_TEXT_MODEL`. Image-prompt-builder reuses this model (cheap, structured task). |
| AI — image (primary) | **OpenAI** — `gpt-image-1`, configured via `OPENAI_IMAGE_MODEL`. Default quality `medium` (~$0.042/image); `low` for dev, `high` for hero shots. |
| AI — alternative providers (documented, not active) | AWS Bedrock (Claude Sonnet 4.5 via inference profile `us.anthropic.claude-sonnet-4-5-20250929-v1:0` + Nova Canvas `amazon.nova-canvas-v1:0` in `us-east-1`) and Anthropic direct. Selected via `AI_PROVIDER_MODE`. Swap is a one-class change via `ILLMProvider`/`IImageProvider`. |
| Object storage | S3 (private bucket, served via CloudFront with Origin Access Control + unguessable UUID keys) |
| CDN | CloudFront (for generated images) |
| Auth | Custom JWT (access + refresh tokens, refresh stored as httpOnly cookie) |
| Backend tooling | uv (package mgr), Ruff (lint+format), mypy (type check), pytest + pytest-asyncio + httpx |
| Frontend tooling | pnpm, ESLint, Prettier, Vitest, Playwright (one happy-path E2E) |
| Infra-as-code | AWS CDK in TypeScript |
| Backend hosting | AWS App Runner (auto-scaling, 0.25 vCPU / 0.5 GB minimum) — **no VPC connector** (see §11 networking decision) |
| Frontend hosting | **AWS Amplify Hosting** (preferred — full Next.js SSR/middleware support) |
| Database hosting | RDS PostgreSQL `db.t4g.micro` in a **public subnet** with strict security group (App Runner IP allowlist + IAM auth optional) |
| Redis hosting | ElastiCache Serverless (production) |
| Secrets | AWS Secrets Manager (production), `.env` (local) |
| Observability | structlog + CloudWatch Logs + Sentry (free tier) |
| CI/CD | GitHub Actions |

---

## 3. High-level architecture

```
Browser
  │
  ├─── app.<domain> ────────→ Amplify Hosting (Next.js SSR + static assets)
  │                              │  (handles auth pages, dashboard, etc.)
  │                              ▼
  │                          api calls to api.<domain>
  │
  └─── images.<domain> ────→ CloudFront ──→ S3 (private generated images)
                                            (Origin Access Control,
                                             unguessable UUID keys)

api.<domain>
  │
  ▼
App Runner — FastAPI containers (auto-scale, PUBLIC egress, no VPC connector)
  │
  ├──→ RDS Postgres (public endpoint, strict SG: only App Runner egress IPs + dev IP)
  ├──→ ElastiCache Redis (rate limit, cache, idempotency, refresh-token blocklist)
  │       └── fallback: in-memory if USE_REDIS=false
  ├──→ OpenAI API (gpt-5.4-mini for text, gpt-image-1 for image) — direct HTTPS
  └──→ S3 (persist generated images) — direct public API

Cross-cutting:
  - CloudWatch Logs (all stdout from FastAPI in structured JSON)
  - Sentry (errors + performance)
  - Secrets Manager → injected env vars into App Runner service
```

**Why no VPC connector on App Runner:** when App Runner uses a VPC connector for outbound traffic, the service loses public internet access — including AWS APIs like Bedrock — unless you provision NAT Gateway or VPC endpoints for every service you call. For a short-lived demo, the cleaner trade is: keep App Runner public, expose RDS publicly with a strict security group locked to App Runner's outbound IP ranges (or use IAM database auth), and skip the VPC complexity entirely.

---

## 4. Repository layout (monorepo)

```
ai-content-suite/
├── README.md                    # rubric-facing: setup, API docs, architecture notes
├── PROJECT_BRIEF.md             # this file
├── ARCHITECTURE.md              # 1-page architecture-decisions doc (bonus)
├── docker-compose.yml           # one-command local bootstrap
├── .github/workflows/
│   ├── backend-ci.yml
│   ├── frontend-ci.yml
│   └── deploy.yml
├── .env.example
├── infra/                       # AWS CDK in TypeScript
│   ├── bin/
│   ├── lib/
│   │   ├── network-stack.ts     # VPC, subnets, SGs
│   │   ├── data-stack.ts        # RDS, ElastiCache, S3 buckets, Secrets Manager
│   │   ├── compute-stack.ts     # App Runner service + ECR repo
│   │   ├── edge-stack.ts        # CloudFront, ACM, Route53 (if domain)
│   │   └── observability-stack.ts
│   ├── package.json
│   └── cdk.json
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── deps.py          # FastAPI dependencies (auth, db, rate limit)
│   │   │   └── v1/
│   │   │       ├── routers/
│   │   │       │   ├── auth.py
│   │   │       │   ├── content.py
│   │   │       │   ├── images.py
│   │   │       │   ├── improver.py
│   │   │       │   ├── brand_voices.py
│   │   │       │   ├── usage.py
│   │   │       │   └── exports.py
│   │   │       └── router.py
│   │   ├── core/
│   │   │   ├── config.py        # pydantic-settings, env validation
│   │   │   ├── security.py      # JWT, password hashing
│   │   │   ├── logging.py       # structlog setup
│   │   │   ├── exceptions.py    # AppException hierarchy + handlers
│   │   │   └── request_context.py
│   │   ├── db/
│   │   │   ├── session.py       # async engine, session factory
│   │   │   ├── base.py
│   │   │   └── models/          # one file per aggregate
│   │   │       ├── user.py
│   │   │       ├── refresh_token.py
│   │   │       ├── brand_voice.py
│   │   │       ├── content_piece.py
│   │   │       ├── generated_image.py
│   │   │       ├── improvement.py
│   │   │       └── usage_event.py
│   │   ├── repositories/        # data access layer (no business logic)
│   │   ├── services/            # business logic, called by routers
│   │   │   ├── auth_service.py
│   │   │   ├── content_service.py
│   │   │   ├── image_service.py
│   │   │   ├── improver_service.py
│   │   │   ├── brand_voice_service.py
│   │   │   └── export_service.py
│   │   ├── providers/
│   │   │   ├── llm/
│   │   │   │   ├── base.py            # ILLMProvider protocol
│   │   │   │   ├── openai_chat.py     # primary
│   │   │   │   ├── mock.py            # canned JSON per content type (reviewer fallback)
│   │   │   │   └── bedrock_claude.py  # documented alternative
│   │   │   └── image/
│   │   │       ├── base.py            # IImageProvider protocol
│   │   │       ├── openai_image.py    # primary (gpt-image-1)
│   │   │       ├── mock.py            # deterministic placeholder PNG
│   │   │       └── bedrock_nova.py    # documented alternative
│   │   ├── prompts/             # one file per template
│   │   │   ├── blog_post.py
│   │   │   ├── linkedin_post.py
│   │   │   ├── ad_copy.py
│   │   │   ├── email.py
│   │   │   ├── image_prompt_builder.py
│   │   │   └── improver.py
│   │   ├── schemas/             # Pydantic request/response models
│   │   └── middleware/
│   │       ├── request_id.py
│   │       ├── rate_limit.py
│   │       └── logging.py
│   ├── alembic/                 # migrations
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── conftest.py
│   ├── Dockerfile               # multi-stage, non-root user, distroless-ish
│   ├── pyproject.toml
│   ├── uv.lock
│   └── README.md
└── frontend/
    ├── app/                     # App Router
    │   ├── (marketing)/         # public landing
    │   ├── (auth)/              # login, register
    │   └── (app)/               # protected
    │       ├── dashboard/
    │       ├── generate/
    │       ├── improve/
    │       ├── brand-voices/
    │       └── settings/
    ├── components/
    │   ├── ui/                  # shadcn/ui
    │   ├── features/
    │   └── layouts/
    ├── lib/
    │   ├── api/                 # OpenAPI-generated client + wrappers
    │   ├── auth/
    │   ├── hooks/
    │   ├── utils/
    │   └── validation/
    ├── public/
    ├── tests/
    ├── package.json
    └── README.md
```

---

## 5. Database schema

All tables use `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`, `created_at`, `updated_at`. Soft delete via `deleted_at TIMESTAMPTZ NULL` where noted.

### users
- `id`, `email` (unique, citext), `password_hash`, `full_name`
- `email_verified_at` (nullable)
- `last_login_at`
- `created_at`, `updated_at`

### refresh_tokens
- `id`, `user_id` (FK), `token_hash` (sha256 of the token — never store the raw token), `expires_at`, `revoked_at` (nullable)
- `user_agent`, `ip_address` (for audit)
- Index: `(user_id)`, `(token_hash)` unique

### brand_voices
- `id`, `user_id` (FK), `name`, `description`
- `tone_descriptors` (jsonb array of strings, e.g. `["confident","data-driven","approachable"]`)
- `banned_words` (jsonb array of strings)
- `sample_text` (text, optional)
- `target_audience` (text)
- Soft delete

### content_pieces
- `id`, `user_id` (FK)
- `content_type` enum: `blog_post | linkedin_post | ad_copy | email`
- `topic` (text), `tone` (text), `target_audience` (text)
- `brand_voice_id` (nullable FK)
- `prompt_version` (string — track which template version was used)
- `system_prompt_snapshot` (text) — for reproducibility
- `user_prompt_snapshot` (text)
- `result` (jsonb — structured output per content type)
- `rendered_text` (text, NOT NULL) — server-rendered plain-text/markdown version of `result`, used for search, preview, copy, export, dashboard cards. Generated by a per-type renderer at write time.
- `result_parse_status` enum: `ok | retried | failed` — tracks whether the LLM returned valid JSON on first attempt, after retry, or never. On `failed`, the raw LLM response is stored in `rendered_text` and `result` may be `null`.
- `word_count` (int)
- `model_id` (text), `input_tokens`, `output_tokens`, `cost_usd` (numeric)
- Soft delete
- Indexes: `(user_id, created_at DESC)`, `(user_id, content_type)`, `(user_id) WHERE deleted_at IS NULL`
- Full-text search index on `rendered_text` (GIN with `to_tsvector('english', ...)`) for dashboard search

### generated_images
- `id`, `content_piece_id` (FK)
- `image_prompt` (text), `negative_prompt` (text, nullable)
- `style` (text, e.g. "photorealistic")
- `provider` enum: `openai | nova_canvas`
- `model_id`, `width`, `height`, `seed`
- `s3_key`, `cdn_url`
- `cost_usd`
- `is_current` boolean — only one per content_piece is current; latest regen flips others to false
- Index: `(content_piece_id, is_current)`, `(content_piece_id, created_at DESC)`

### improvements
- `id`, `user_id` (FK)
- `original_text`, `improved_text`
- `goal` enum: `shorter | persuasive | formal | seo | audience_rewrite`
- `new_audience` (text, nullable — only for audience_rewrite)
- `explanation` (jsonb — array of bullet points)
- `changes_summary` (jsonb)
- `original_word_count`, `improved_word_count`
- `model_id`, `input_tokens`, `output_tokens`, `cost_usd`
- Soft delete

### usage_events
- `id`, `user_id` (FK)
- `event_type` enum: `text_gen | image_gen | improve | image_regen | export`
- `reference_id` (UUID — points to content_piece, generated_image, or improvement)
- `tokens_in`, `tokens_out`, `cost_usd`
- `metadata` (jsonb)
- Index: `(user_id, created_at DESC)`

Migrations live in `backend/alembic/versions/`. Every model change goes through `alembic revision --autogenerate -m "..."` then manual review before commit. Run on deploy via App Runner pre-deploy hook (or one-off task) — never auto-migrate on startup.

---

## 6. API contract (v1)

**Conventions:**
- Base path: `/api/v1`
- Auth: `Authorization: Bearer <access_token>` on all protected routes
- Refresh token: httpOnly cookie `refresh_token` (Secure, SameSite=Lax)
- Response envelope: `{ "data": ..., "meta": { "request_id": "..." } }` on success, `{ "error": { "code": "...", "message": "...", "details": {...} }, "meta": { "request_id": "..." } }` on failure
- Standard error codes: `VALIDATION_FAILED`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `RATE_LIMITED`, `LLM_PROVIDER_ERROR`, `IMAGE_PROVIDER_ERROR`, `INTERNAL_ERROR`
- All POST endpoints accept `Idempotency-Key` header (UUID); duplicate keys return cached response within 24h
- Pagination: `?page=1&page_size=20`, max page_size 100; response includes `meta.pagination: { page, page_size, total, total_pages }`

### Auth
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/auth/register` | `{ email, password, full_name }` | `{ user, access_token }` + sets refresh cookie |
| POST | `/auth/login` | `{ email, password }` | same |
| POST | `/auth/refresh` | (uses cookie) | `{ access_token }` + new refresh cookie (rotation) |
| POST | `/auth/logout` | — | revokes refresh token, clears cookie |
| GET | `/auth/me` | — | `{ user }` |

JWT specs: HS256, access token expires 15 min, refresh token expires 30 days, refresh token rotated on every use, old refresh tokens blocklisted in Redis until natural expiry.

### Content
| Method | Path | Notes |
|---|---|---|
| POST | `/content/generate` | Body: `{ content_type, topic, tone, target_audience, brand_voice_id? }`. **Non-streaming** — returns `{ content_id, result, rendered_text, usage, result_parse_status }` on completion. Frontend displays a staged loading UI ("Analyzing topic..." → "Drafting..." → "Polishing...") for the ~3-8 second wait. Rationale: structured JSON outputs do not stream cleanly; per-type renderers need the complete response. Streaming is kept as an option for the improver where output is closer to plain text. |
| GET | `/content` | List own content. Filters: `?content_type=...&q=...&page=...&page_size=...`. `q` runs full-text search against `rendered_text`. |
| GET | `/content/:id` | Detail incl. current image |
| DELETE | `/content/:id` | Soft delete (returns soft-deleted record so the frontend can offer an undo toast) |
| POST | `/content/:id/restore` | Undelete within 24h |

### Images
| Method | Path | Notes |
|---|---|---|
| POST | `/content/:id/image` | Body: `{ style?, provider? }`. Generates new image, marks as current, returns `{ image }`. Style options: `photorealistic | illustration | minimalist | 3d_render | watercolor | cinematic` |
| GET | `/content/:id/images` | All versions |

### Improver
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/improve` | `{ original_text, goal, new_audience? }` | `{ improved_text, explanation, changes_summary }` — **optionally streamed via SSE** (output is closer to plain text and benefits from progressive display). Non-streaming mode also supported via `Accept: application/json`. |
| GET | `/improvements` | List | paginated |
| GET | `/improvements/:id` | Detail | |
| DELETE | `/improvements/:id` | Soft delete | |

### Brand voices
| Method | Path | |
|---|---|---|
| GET | `/brand-voices` | List own |
| POST | `/brand-voices` | Create |
| GET | `/brand-voices/:id` | Detail |
| PATCH | `/brand-voices/:id` | Update |
| DELETE | `/brand-voices/:id` | Soft delete |

### Usage
| Method | Path | |
|---|---|---|
| GET | `/usage/summary` | `{ total_generations, total_images, total_tokens, total_cost, by_type: {...}, last_30_days: [...] }` |

### Exports
| Method | Path | Notes |
|---|---|---|
| GET | `/content/:id/export?format=pdf\|docx\|markdown` | Returns file download (or presigned S3 URL for PDF/DOCX) |

### System
| Method | Path | |
|---|---|---|
| GET | `/health` | `{ status, version, dependencies: { db, redis, openai } }` |
| GET | `/openapi.json` | Auto-generated OpenAPI 3.1 spec |
| GET | `/docs` | Swagger UI |
| GET | `/redoc` | ReDoc UI |

**Rate limits (Redis sliding window, per user):**
- `/auth/login`, `/auth/register`: 10/min by IP
- `/content/generate`: 20/hour
- `/content/:id/image`: 30/hour
- `/improve`: 30/hour
- Everything else: 120/min

---

## 7. Prompt strategy

Every prompt is a typed Python module with a function that takes context and returns `(system_prompt, user_prompt)`. The exact strings are versioned (constant `PROMPT_VERSION = "v1"`) and persisted with each generation for reproducibility.

All content prompts request **JSON output** for reliable parsing. The OpenAI call uses `response_format: { type: "json_schema", json_schema: {...}, strict: true }` (supported on `gpt-5.x` and `gpt-4o-2024-08-06+`) for stage 1, eliminating most malformed responses at the source. The three-stage fallback below still ships as defense in depth — model behavior can drift, structured outputs can occasionally fail validation, and we never want a live demo to surface an error.

### 7.0 JSON parse fallback (three stages — demo safety)

This is non-negotiable. The user must never see an error during a live demo.

1. **Attempt 1 — parse:** call OpenAI with `response_format: { type: "json_schema", strict: true }`, parse the response as JSON, validate against the Pydantic schema for this content type. On success → set `result_parse_status = ok`, render `rendered_text`, persist, return.
2. **Attempt 2 — retry on failure:** if parsing or validation fails, make a follow-up OpenAI call with the original messages plus: *"Your previous response was not valid JSON matching the required schema. Return ONLY valid JSON with no preamble, no markdown fencing, and no explanation."* On success → set `result_parse_status = retried`, render, persist, return.
3. **Attempt 3 — graceful degrade:** if the second attempt also fails, store the raw LLM output as `rendered_text`, set `result = null`, `result_parse_status = failed`, log to Sentry with severity warning. Return success to the user with a small banner in the UI ("Generated in fallback mode — formatting may be inconsistent"). The user still has usable content; the demo continues.

### 7.0.1 Rendered text renderer

Each content type has a server-side renderer that converts `result` (jsonb) into `rendered_text` (plain text or markdown) suitable for full-text search, dashboard preview, copy-to-clipboard, and export:

- `blog_post` → markdown (H1 → `# `, sections → `## `, etc.)
- `linkedin_post` → `{hook}\n\n{body}\n\n{cta}\n\n{hashtags joined}`
- `ad_copy` → grouped variants, one per heading, with format labels
- `email` → `Subject: ...\nPreview: ...\n\n{greeting}\n\n{body}\n\n{cta_text}\n\n{sign_off}`

Renderers live in `app/services/renderers/` and are pure functions. They run once at write time, never at read time.

### 7.1 Blog post

**System:**
> You are an expert content strategist and writer. You produce publication-ready blog posts that rank on search and read like a human wrote them — never AI-generic.

**User template:**
```
Audience: {audience}
Tone: {tone}
Topic: {topic}
{brand_voice_block}

Write a blog post following these requirements:
- H1 title, max 12 words, includes the primary keyword
- Meta description under 160 characters
- Opening hook (1-2 paragraphs) that creates curiosity
- 3-5 H2 sections, each 150-250 words
- At least one bulleted list inside a section
- Closing paragraph with a clear takeaway and CTA
- Total length 800-1200 words
- Suggested tags: 3-5 SEO-relevant tags

Quality rules:
- Short paragraphs. Use "you". Concrete examples over abstractions.
- No clichés: avoid "in today's fast-paced world", "leverage", "synergy", "game-changer", "delve into", "navigate the complexities".
- No em-dashes unless necessary. No emojis.

Return ONLY valid JSON matching this schema, with no preamble or markdown fencing:
{
  "title": string,
  "meta_description": string,
  "intro": string,
  "sections": [{ "heading": string, "body": string }],
  "conclusion": string,
  "suggested_tags": [string]
}
```

### 7.2 LinkedIn post

**System:**
> You are a LinkedIn ghostwriter for senior professionals. Your posts stop the scroll, give one concrete insight, and earn comments.

**User template:**
```
Audience: {audience}
Tone: {tone}
Topic: {topic}
{brand_voice_block}

Write a LinkedIn post:
- Hook in the first line (this is what shows in the feed before "see more")
- Body: 3-6 short paragraphs (1-3 sentences each), generous line breaks
- One concrete insight, story, or data point — not generic advice
- Clear CTA at the end (question, share request, or invitation)
- 3-5 relevant hashtags
- Total 150-300 words

Quality rules:
- The hook must be specific, contrarian, or curiosity-provoking. Never start with "Excited to announce", "I'm thrilled to share", "Today I learned".
- One idea per paragraph. Line breaks are your friend.
- No emojis unless the tone explicitly calls for them.
- Sound like a human in a conversation, not a corporate announcement.

Return JSON:
{
  "hook": string,
  "body": string,
  "cta": string,
  "hashtags": [string]
}
```

### 7.3 Ad copy

**System:**
> You are a direct-response copywriter. You write ad variants that get clicked. You think in terms of headline, body, call-to-action, and the psychological angle each variant tests.

**User template:**
```
Product or topic: {topic}
Audience: {audience}
Tone: {tone}
{brand_voice_block}

Generate three ad copy variants, each at a different length. Each variant should test a different psychological angle (curiosity, FOMO, social proof, transformation, contrarian, urgency).

Return JSON:
{
  "variants": [
    {
      "format": "short",
      "angle": string,
      "headline": string,  // under 40 chars
      "body": string,      // under 90 chars
      "cta": string        // 2-4 words
    },
    {
      "format": "medium",
      "angle": string,
      "headline": string,  // under 60 chars
      "body": string,      // under 200 chars
      "cta": string        // 2-5 words
    },
    {
      "format": "long",
      "angle": string,
      "headline": string,  // under 80 chars
      "body": string,      // under 500 chars
      "cta": string        // 3-7 words
    }
  ]
}

Quality rules:
- Lead with benefit, not feature. Specific numbers beat vague claims. Urgency only when defensible.
- No clichés. No "discover the power of". No fake testimonials.
```

### 7.4 Email

**System:**
> You are an email copywriter writing for {audience}. Your emails get opened (great subject lines), get read (one clear hook), and get clicked (one clear CTA).

**User template:**
```
Topic: {topic}
Tone: {tone}
Audience: {audience}
{brand_voice_block}

Write an email:
- Subject line, under 50 characters, compelling without clickbait
- Preview text, under 90 characters, complements the subject (does not repeat it)
- Greeting
- Hook (1-2 sentences)
- Body: 2-3 short paragraphs
- One clear CTA
- Sign-off

Total body: 100-250 words.

Quality rules:
- Personal pronouns. Short sentences. Write like a human, not a brand.
- Banned: "I hope this email finds you well", "Just checking in", "Per my last email", "Circling back".

Return JSON:
{
  "subject": string,
  "preview_text": string,
  "greeting": string,
  "body": string,
  "cta_text": string,
  "sign_off": string
}
```

### 7.5 Image prompt builder

This runs as a separate OpenAI chat call AFTER the content is generated. Output is sent to `gpt-image-1`. The same module remains compatible with Bedrock Nova Canvas when `AI_PROVIDER_MODE=bedrock` — only the downstream image call changes; the prompt-building stage is provider-agnostic.

**System:**
> You are an art director. Given written marketing content and a style preference, you craft a single rich image-generation prompt suitable for `gpt-image-1` (OpenAI). Your prompts are visually concrete, not literary.

**User template:**
```
Content type: {content_type}
Topic: {topic}
Tone: {tone}
Style preference: {style}  // one of: photorealistic, illustration, minimalist, 3d_render, watercolor, cinematic
Content excerpt: {first_300_chars_of_content}

Craft an image prompt for use with OpenAI `gpt-image-1`.

Describe:
- Subject (concrete, visual, what's in the frame)
- Composition (framing, perspective, layout)
- Style and art direction (consistent with the style preference)
- Lighting and mood (consistent with the content's tone)
- Color palette (3-5 specific colors)
- Specific details that reinforce the topic

Constraints:
- No text overlays, no logos, no real identifiable people, no copyrighted characters or IP.
- The image must be brand-safe and suitable for marketing use.
- Length: 60-120 words for the prompt itself. Be visually specific, not poetic.

Return JSON:
{
  "prompt": string,
  "negative_prompt": string,
  "style_summary": string  // 3-5 words
}
```

The image provider then receives:
- `prompt` (`negative_prompt` ignored for `gpt-image-1`; folded into the positive prompt as constraints)
- `style` mapped to provider-specific config:
  - **OpenAI `gpt-image-1`:** `size: "1024x1024"`, `quality: "medium"` default, `quality: "high"` for hero shots
  - **Bedrock Nova Canvas (alt):** `quality: "premium"` for higher styles, `1024x1024` default, `negative_prompt` passed through
- request metadata (model id, quality tier, prompt hash) logged for reproducibility — `gpt-image-1` does not expose a seed

### 7.6 Improver

Two-call chain:

**Call 1 — Analysis (system):**
> You are an editor. Analyze the given text against the user's improvement goal and identify specific changes to make. Return only your analysis as JSON.

**Call 1 user:**
```
Goal: {goal}
{goal_specific_instructions}
{new_audience_block_if_applicable}

Text to analyze:
---
{original_text}
---

Identify changes:
{
  "issues": [string],          // what's weak in the original
  "planned_changes": [string]  // what you'll change
}
```

**Call 2 — Rewrite (system):**
> You are an editor executing a planned rewrite. Apply the changes precisely and preserve the original meaning.

**Call 2 user:**
```
Goal: {goal}
Planned changes: {planned_changes_from_call_1}
Original: {original_text}

Apply the changes and return JSON:
{
  "improved_text": string,
  "explanation": [string],     // 2-4 bullets of what you changed and why
  "changes_summary": {
    "tone_shift": string | null,
    "length_change_pct": number,
    "key_additions": [string],
    "key_removals": [string]
  }
}
```

Goal-specific instructions injected:
- `shorter`: Cut at least 30% while preserving meaning and impact.
- `persuasive`: Strengthen with concrete benefits, urgency, social proof, sharper claims. Keep claims defensible.
- `formal`: Elevate vocabulary, remove contractions and slang, longer sentences, third person where appropriate.
- `seo`: Improve readability (target Flesch 60+), naturally include the primary keyword 3-5 times, add subheadings where helpful, shorten paragraphs.
- `audience_rewrite`: Rewrite for `{new_audience}`. Adjust vocabulary, references, examples, tone.

### 7.7 Brand voice block (injected into other prompts)

When the user has selected a `brand_voice_id`, the following block is appended to the user prompt:

```
Brand voice:
- Name: {name}
- Tone descriptors: {tone_descriptors}
- Words to avoid: {banned_words}
- Target audience: {target_audience}
- Sample text reflecting this voice: {sample_text or "—"}
Match this voice consistently.
```

---

## 8. Non-functional requirements checklist

Use this as a literal checklist during the build. Every box must be ticked before deployment.

### Security
- [ ] All env vars validated at startup via `pydantic-settings` — service fails fast on missing/invalid
- [ ] Secrets never logged, never in error messages
- [ ] Passwords hashed with `passlib[bcrypt]`, work factor 12
- [ ] JWT access token: 15 min expiry, HS256, secret from Secrets Manager
- [ ] Refresh token: hashed at rest, 30 day expiry, single-use rotation, blocklist in Redis
- [ ] CSRF protection: refresh cookie is SameSite=Lax + Secure + httpOnly
- [ ] CORS: explicit allowlist of frontend origin, no wildcard
- [ ] Rate limiting on every public endpoint (see API contract section)
- [ ] Input validation: Pydantic on backend, Zod on frontend
- [ ] SQL injection: only ORM queries, no string interpolation
- [ ] XSS: React handles by default; sanitize markdown output if rendered
- [ ] Security headers: `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Content-Security-Policy`
- [ ] IAM: App Runner service role has only the permissions it needs (S3 put/get on the images bucket + Secrets Manager read on the two secret ARNs + CloudWatch logs)
- [ ] S3 buckets are private; access via CloudFront with Origin Access Control
- [ ] No `aws_access_key` in code or env — use IAM role for App Runner
- [ ] No raw API keys in env files committed to git — `OPENAI_API_KEY` lives in Secrets Manager (prod) and `.env` locally (gitignored)

### Reliability
- [ ] Retry with exponential backoff on OpenAI 5xx/429 errors (max 3 attempts)
- [ ] Circuit breaker on repeated provider failures (open for 30s after 5 consecutive failures) — *deferred to week 3 hardening*
- [ ] Three-stage JSON parse fallback on content generation (parse → retry → graceful degrade with `result_parse_status = failed`)
- [ ] Idempotency keys on `/content/generate`, `/content/:id/image`, `/improve`, 24h Redis cache (in-memory fallback if `USE_REDIS=false`)
- [ ] Database connection pool sized for App Runner concurrency (start: pool_size=5, max_overflow=10)
- [ ] Graceful shutdown: close DB connections on SIGTERM
- [ ] Health endpoint checks downstream dependencies (db, redis if enabled, openai — last via cached `GET /v1/models` ping, 5 min TTL)
- [ ] All API responses have a `request_id` header and body field

### Performance
- [ ] Staged loading UI for content generation (non-streaming endpoint; the SSE-on-structured-JSON trap is avoided by design)
- [ ] Streaming SSE for the improver only (output is closer to plain text)
- [ ] Optimistic UI updates on delete with rollback on error
- [ ] TanStack Query caching with sensible stale times
- [ ] CloudFront caching for generated images (long TTL — UUID keys mean URLs are immutable)
- [ ] Database indexes per schema spec
- [ ] N+1 query audit before deployment

### Observability
- [ ] Structured JSON logs via structlog — every log line includes `request_id`, `user_id`, `path`, `duration_ms`
- [ ] CloudWatch log groups configured with retention (14 days for dev, 30 days for prod)
- [ ] Sentry capturing unhandled exceptions on both frontend and backend
- [ ] Request ID propagated: frontend → backend → response → logs
- [ ] OpenAI usage logged per call: model, input tokens, output tokens, cost (computed from price table), latency

### Accessibility
- [ ] Semantic HTML throughout
- [ ] All interactive elements keyboard-accessible
- [ ] Focus indicators visible
- [ ] ARIA labels where semantic HTML insufficient
- [ ] Color contrast meets WCAG AA
- [ ] No keyboard traps
- [ ] One Playwright E2E test runs through generate flow with keyboard only

### UX
- [ ] Loading skeletons (not spinners) for all data fetches
- [ ] Empty states with helpful CTAs and example data
- [ ] Error states with recovery actions (retry, contact support, etc.)
- [ ] Toast notifications for all mutations (success and error)
- [ ] Confirmation dialogs for destructive actions (delete)
- [ ] 404 and 500 pages styled and helpful
- [ ] Dark mode via `next-themes`
- [ ] Mobile responsive — tested at 375px width minimum

### Documentation
- [ ] `README.md` covers: what it is, screenshots/GIFs, setup, env vars, running locally, running tests, deploying, API docs link, architecture notes
- [ ] `ARCHITECTURE.md` covers: stack decisions, trade-offs, what would change with more time
- [ ] OpenAPI spec available at `/docs` and `/redoc`
- [ ] Inline docstrings on all service-layer functions

---

## 9. Local development

`docker-compose.yml` brings up:
- `postgres:16` on 5432, seeded by entrypoint script
- `redis:7-alpine` on 6379 (skippable — set `USE_REDIS=false` to use in-memory rate limiting and token blocklist instead)
- `backend` (FastAPI with uvicorn `--reload`) on 8000
- `frontend` (Next.js dev server) on 3000

`.env.example` documents every variable. The full set:

```env
# --- AI provider mode ---
# openai (primary) | bedrock | mock
AI_PROVIDER_MODE=openai

# --- OpenAI (primary provider) ---
OPENAI_API_KEY=sk-proj-...
OPENAI_TEXT_MODEL=gpt-5.4-mini-2026-03-17
OPENAI_IMAGE_MODEL=gpt-image-1
OPENAI_IMAGE_QUALITY=medium     # low | medium | high
OPENAI_TIMEOUT_SECONDS=60
OPENAI_MAX_RETRIES=3

# --- AWS (always required for hosting / S3 / Secrets Manager — not for AI) ---
AWS_REGION=us-east-1
# Local dev typically uses AWS_PROFILE; App Runner uses an IAM role (no keys).
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

# --- Database ---
DATABASE_URL=postgresql+asyncpg://app:app@postgres:5432/app

# --- Redis (optional locally; required in prod) ---
USE_REDIS=true
REDIS_URL=redis://redis:6379/0

# --- Auth ---
JWT_SECRET=replace-with-openssl-rand-hex-32
JWT_ACCESS_TOKEN_TTL_SECONDS=900
JWT_REFRESH_TOKEN_TTL_SECONDS=2592000

# --- S3 / image storage ---
S3_BUCKET_IMAGES=ai-content-images-dev
IMAGES_CDN_BASE_URL=http://localhost:8000/local-images   # local fallback serves from disk
# In prod: https://images.<your-domain>

# --- Frontend ---
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1

# --- Observability ---
SENTRY_DSN=
LOG_LEVEL=INFO

# --- Alternative AI providers (documented only; not required) ---
# Set AI_PROVIDER_MODE=bedrock to use these instead.
# Bedrock Claude Sonnet 4.5 requires an inference profile (not the bare model ID).
# Enable model access at https://us-east-1.console.aws.amazon.com/bedrock/home#/modelaccess
BEDROCK_TEXT_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0
BEDROCK_IMAGE_MODEL_ID=amazon.nova-canvas-v1:0
# Nova Canvas is LEGACY (EOL 2026-09-30) — plan migration if running past that.
```

Bootstrap sequence:
```bash
git clone <repo> && cd ai-content-suite
cp .env.example .env
# Fill in OPENAI_API_KEY + JWT_SECRET (everything else has sane defaults).
# AWS creds are only needed if you want to test S3 uploads locally — without them,
# images are served from local disk by the dev backend.
docker-compose up --build
# In another terminal:
docker-compose exec backend alembic upgrade head
docker-compose exec backend python -m app.scripts.seed
# Open http://localhost:3000
```

Seed script creates:
- One demo user (email/password printed in console)
- One brand voice
- Three example content pieces with images
- One improvement

This makes the reviewer's first 60 seconds feel like a finished product.

**Fallback modes for reviewers:**
- `AI_PROVIDER_MODE=mock` — canned valid JSON per content type + a deterministic placeholder PNG, so the app is fully demoable with **no API keys at all**. Used by CI and any reviewer who cannot or does not want to use an OpenAI key.
- `AI_PROVIDER_MODE=bedrock` — uses AWS Bedrock instead of OpenAI (requires AWS creds + `bedrock:InvokeModel` IAM + model access enabled in `us-east-1` for Claude Sonnet 4.5 via inference profile and Nova Canvas).

Both are documented in the README.

---

## 10. CI/CD

### `.github/workflows/backend-ci.yml`
On every PR + push to main:
- Lint: `ruff check`, `ruff format --check`
- Type check: `mypy app`
- Test: `pytest --cov=app --cov-report=xml`
- Build: docker build, push to ECR on main only

### `.github/workflows/frontend-ci.yml`
On every PR + push to main:
- Lint: `eslint`, `prettier --check`
- Type check: `tsc --noEmit`
- Test: `vitest run`
- Build: `next build`
- E2E (main only): Playwright against deployed preview

### `.github/workflows/deploy.yml`
On push to main:
1. Backend: build & push image to ECR with tag `latest` and SHA, trigger App Runner deployment
2. Run Alembic migrations as a one-off ECS Fargate task (CDK provisions this)
3. Frontend: `next build && next export`, sync to S3, invalidate CloudFront
4. Smoke test: hit `/health` and assert 200

---

## 11. AWS infrastructure (CDK stacks)

### Networking decision (explicit)

**App Runner runs without a VPC connector. RDS is in a public subnet with strict security group rules.**

Rationale: App Runner with a VPC connector loses public AWS API access (Bedrock, S3, Secrets Manager) unless we provision NAT Gateway (~$32/mo) or VPC endpoints for every service (more CDK code). For a short-lived demo with strict SG rules on RDS, public-endpoint RDS is the right trade. Connection is still TLS-encrypted; access is restricted to App Runner's outbound IP ranges + the developer's IP. If long-term hardening is needed later, switch to VPC connector + VPC endpoints for `bedrock-runtime`, `s3`, `secretsmanager`, `logs`.

### `DataStack`
- RDS `db.t4g.micro`, **publicly accessible**, encrypted, 7-day backups in prod (dev: disabled)
- RDS security group inbound: only from App Runner outbound IP ranges (`com.amazonaws.us-east-1.apprunner` managed prefix list) + developer IP for migrations
- ElastiCache Serverless Redis — also reachable from App Runner public egress (or in-VPC if we ever switch; document both)
- S3 bucket: `ai-content-images-{env}` (private, blocked-public-access, Origin Access Control with CloudFront)
- Secrets Manager entries: `openai-api-key`, `jwt-secret`, `db-password`

### `ComputeStack`
- ECR repository for backend image
- App Runner service — **no VPC connector**, public egress
- Auto-scaling: min 1, max 3, concurrency 80
- IAM role with: `s3:PutObject` + `s3:GetObject` on the images bucket only, `secretsmanager:GetSecretValue` on `openai-api-key` + `jwt-secret` + `db-password` ARNs only, `logs:CreateLogStream` + `logs:PutLogEvents`. (No Bedrock permissions unless `AI_PROVIDER_MODE=bedrock` is selected, in which case `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream` are added.)
- Health check: `/health`
- Env vars sourced from Secrets Manager + plain config

### `EdgeStack`
- **Amplify Hosting app** for the frontend, connected to the GitHub repo (auto-deploy on push to main). Build settings in `amplify.yml`. Custom domain optional.
- CloudFront distribution for the images bucket only (private S3 origin via Origin Access Control)
- ACM cert + Route53 alias if custom domain is used

### `ObservabilityStack`
- CloudWatch log groups with retention (14 days dev, 30 days prod)
- CloudWatch alarm on App Runner 5xx rate (>5% over 5 min) → SNS topic (optional email)
- (Sentry is external, configured via env var)

### Teardown
`cdk destroy --all` — single command tears down everything. Amplify app is destroyed separately via `aws amplify delete-app` or console. Useful before the grant runs out.

---

## 12. 3-week execution timeline

The plan assumes Claude Code does most of the implementation with the user reviewing PRs / large changes. Key principle: **deploy a thin vertical slice to AWS by day 5-6, then build features against a working production environment.** Never let AWS plumbing be a week-3 surprise.

**Prerequisite (before Day 1):** OpenAI API key funded ($8+), $25/month hard usage cap set, `gpt-5.4-mini-2026-03-17` text smoke call passes, `gpt-image-1` image smoke call passes. See `PHASES.md` task P-1.1. *(Bedrock kept as documented alternative — if `AI_PROVIDER_MODE=bedrock` is ever needed, enable Claude Sonnet 4.5 via inference profile + Nova Canvas in `us-east-1`.)*

### Week 1 — Foundations + thin vertical slice deployed
| Day | Goal |
|---|---|
| 1 | Repo init, monorepo structure, Docker Compose with Postgres + Redis, GH Actions skeleton, README outline, `.env.example` filled out, **local-dev bootstrap verified** (P0.7) |
| 2 | SQLAlchemy models for all tables (incl. `rendered_text`, `result_parse_status`), Alembic baseline migration, FastAPI app skeleton with config validation, structured logging, exception handlers, request ID middleware, **explicit CORS allowlist** |
| 3 | Auth: register/login/refresh/logout/me, password hashing, JWT with httpOnly refresh cookie, refresh rotation (DB `revoked_at` only — Redis blocklist deferred to week 3) |
| 4 | Provider abstractions (`ILLMProvider`, `IImageProvider`), **OpenAI chat + image impls** with retry + exponential backoff on 5xx/429, **MockLLMProvider fully implemented** (canned JSON per content type for reviewer fallback), env-driven model selection. **Plus: security headers middleware + in-memory rate limit on `/auth/login` + `/auth/register`** |
| 5 | **Production online (part 1):** CDK NetworkStack + DataStack + ComputeStack deployed. App Runner serving FastAPI behind HTTPS. RDS connected. `/health` 200 from public URL. One successful OpenAI call from production (logged with model + tokens + cost). |
| 6 | **Production online (part 2):** EdgeStack (Amplify Hosting + CloudFront for images) + ObservabilityStack. **Amplify frontend wired to App Runner with real auth end-to-end** (login → token → protected page → logout — surfaces CORS/cookie issues immediately, which is the entire point of deploying early). Sentry basic SDK init (backend + frontend). Deploy workflow on push-to-main. |
| 7 | Content generation endpoint for blog post type — non-streaming, prompt template, three-stage JSON parse fallback, renderer to `rendered_text`, persistence, usage tracking inline on the content_pieces row |

### Week 2 — Frontend, image gen, dashboard, improver, brand voice
| Day | Goal |
|---|---|
| 8 | Add LinkedIn, ad copy, email content types — share infrastructure, distinct prompts, per-type result schemas, per-type renderers |
| 9 | Frontend generate page with content-type selector, brand voice selector (stub), tone, audience — staged loading UI driving non-streaming endpoint, deployed |
| 10 | Result rendering per content type (blog, LinkedIn, ad copy, email), copy-to-clipboard, fallback-mode banner, error states + retry |
| 11 | OpenAI `gpt-image-1` provider, image prompt builder (separate OpenAI chat call using `gpt-5.4-mini-2026-03-17`), S3 upload service, CloudFront URL generation |
| 12 | POST /content/:id/image endpoint, frontend "Generate image" button on result view + image display |
| 13 | Image style picker (6 styles drive prompt-builder output + `gpt-image-1` quality tier), regeneration with `is_current` flip, simple flat thumbnail strip showing previous versions (no lightbox) |
| 14 | Dashboard: paginated list with full-text search on `rendered_text`, filter by type, detail view, soft delete with 24h undo via toast + restore endpoint |
| 15 | Improver: backend two-call chain (analyze → rewrite), **non-streaming**, frontend page with goal selector, side-by-side diff view, persistence + history |
| 16 | Brand voices: backend CRUD, frontend page, integration into generation form (dropdown injects voice block into prompt), seed script updated |

### Week 3 — Polish, production hardening, video
| Day | Goal |
|---|---|
| 17 | Exports: PDF (WeasyPrint), DOCX (python-docx) — DOCX is first on the cut line |
| 18 | Markdown direct from `rendered_text`. Usage tracking: split out `usage_events` table, simple `/api/usage/summary` endpoint, one-page Usage view with totals (skip the chart if behind) |
| 19 | Polish pass: error boundaries, toast notifications, empty states, 404/500 pages, fallback-mode banner, accessibility (keyboard, ARIA, contrast, focus), one Playwright E2E happy-path test |
| 20 | Production hardening: Redis blocklist for refresh tokens (move from DB), idempotency middleware on `/content/generate` + `/content/:id/image` + `/improve`, rate limiting tuned per endpoint, circuit breaker on OpenAI provider. CI/CD finalization, Sentry source-map polish, CloudWatch alarm |
| 21 | README polish, ARCHITECTURE.md, OpenAPI doc review, record video walkthrough showing text gen + image gen + Claude Code workflow segments, submit |

### What this rearrangement protects against
- **OpenAI API key / billing surprises** — caught during Prerequisites (P-1.1), before Day 1, not on day 5
- **AWS networking surprises** — caught on day 5, not day 19
- **Cookie/CORS issues between Amplify and App Runner** — caught on day 6 when **real** auth lands end-to-end, not day 8
- **Streaming/JSON conflicts** — entirely avoided by going non-streaming for content generation and the improver
- **Redis as a critical path dependency** — deferred to week 3 hardening; week 1-2 can ship without it
- **Flying blind on production errors** — Sentry basic capture is live from day 6, not day 19

---

## 13. Must not slip (non-negotiable demo features)

If everything else burns down, these must work end-to-end on the live URL:

1. Register, log in, see a dashboard
2. Generate at least 3 content types (blog, LinkedIn, email — ad copy is the safest to drop)
3. Generate a matching image for a piece of content
4. Regenerate that image with a different style
5. See past generations in a dashboard with at least: list view, detail view, copy, delete
6. Improve existing text with an explanation of what changed
7. README with: live URL, demo credentials, setup, API docs link, architecture note
8. Video showing text gen + image gen + a real Claude Code workflow segment

These eight items are the floor. Everything else in this brief is upside.

---

## 14. Cut line (order of things to drop if behind schedule)

Cut from the bottom up. Do not cut from anywhere except this list.

1. DOCX export (keep PDF + Markdown)
2. Usage dashboard UI (keep the endpoint, drop the page)
3. Alternative image provider (Bedrock Nova Canvas wiring; keep OpenAI `gpt-image-1` only)
4. Image version-history thumbnails (keep regenerate button, drop the strip)
5. Redis blocklist for refresh tokens (use DB `revoked_at` only)
6. Idempotency middleware globally (keep on `/content/generate` + `/content/:id/image` only)
7. Circuit breaker on OpenAI provider (keep retry + timeout only)
8. Playwright E2E test (manual test the demo path instead)
9. CloudWatch custom alarms (default App Runner monitoring is enough)
10. One of the four content types (drop ad copy — blog + LinkedIn + email satisfies the rubric's "at least 3 content types" requirement)
11. Brand voice feature (cut last — it's worth bonus points and isn't that much code)

What never gets cut: auth, content generation, image generation, dashboard, improver, README, video.

---

## 15. Definition of Done per feature

A feature is **done** only when:
1. Backend endpoint implemented with input validation, error handling, structured logging, and usage tracking
2. Backend has unit tests for the service layer and one integration test for the endpoint
3. Frontend page/component implemented with loading, empty, and error states
4. Manual end-to-end test passes against the deployed environment (not just local)
5. OpenAPI spec updated and reviewed
6. README updated if user-facing behavior changed
7. No linter or type-checker warnings

---

## 16. README.md (final, evaluator-facing) requirements

The repo's top-level README must contain, in this order:
1. **One-line description + screenshot/GIF** of the app
2. **Live URL** prominently linked
3. **Demo credentials** (email/password for a seeded reviewer account)
4. **Tech stack** bullet list
5. **Quick start** — single-command Docker Compose bootstrap
6. **Architecture diagram** (the ASCII one or a simple PNG)
7. **API documentation** — link to `/docs` on live URL + brief endpoint summary
8. **Project structure** — annotated tree
9. **Environment variables** — table of every env var with description
10. **Running tests**
11. **Deployment** — link to the AWS CDK section, single command `cdk deploy --all`
12. **Architecture decisions** — short bullets or link to `ARCHITECTURE.md`
13. **What I'd build next** (1-2 paragraphs)
14. **Claude Code workflow note** — short paragraph + link to video

---

## 17. Out of scope (explicitly not built)

- Multi-tenancy / team accounts
- Email verification flow (stub only)
- Password reset flow (stub only — note in README as known limitation)
- Stripe billing (free tier only)
- Real-time collaboration
- Mobile app
- Analytics beyond usage events
- A/B prompt testing (intriguing but defer)
- Content calendar / scheduling
- Multi-language UI (English only)

If time remains after Week 3 Day 18, the priority extras are: password reset, A/B prompt testing, content calendar.

**Documented alternatives (not active code paths):** AWS Bedrock (Claude Sonnet 4.5 via `us.` inference profile + Nova Canvas) is documented in `ARCHITECTURE.md` and the README as a swap-in alternative. The `ILLMProvider` / `IImageProvider` abstractions make this a one-class change. Anthropic direct API is mentioned but not implemented — README should not advertise `AI_PROVIDER_MODE=anthropic_direct` unless we ship that provider.

---

## 18. Video walkthrough plan (5-10 minutes)

Capture as you build, edit at the end. Required segments:

1. **(0:00-0:30)** Live URL on screen, register a new account, land on dashboard
2. **(0:30-2:00)** Content generation flow: pick LinkedIn post, fill the form, watch the staged loading UI, see the result
3. **(2:00-3:30)** Image generation flow: click "Generate image", see the auto-built prompt, see the image appear, try regenerating with a different style
4. **(3:30-4:30)** Improver flow: paste text, pick "more persuasive", show the diff and explanation
5. **(4:30-6:00)** Dashboard: list of past generations, filter, export to PDF, soft delete with undo
6. **(6:00-8:00)** Claude Code workflow: 3-4 clips edited together showing real moments — planning a feature, debugging a failing test, refactoring to a provider interface, iterating on a prompt
7. **(8:00-9:00)** Quick code tour: provider interfaces, prompt modules, OpenAPI docs
8. **(9:00-end)** Wrap

---

*End of brief. Update this document as decisions evolve. Treat the API contract and database schema as the contracts of record — if you change them, update this file in the same PR.*
