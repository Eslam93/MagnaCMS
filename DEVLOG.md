# Development log

A running journal of decisions, trade-offs, and progress on MagnaCMS. Newest entries first. Each entry is written when something interesting happens — not on a schedule — so the cadence reflects the actual pace of work.

---

## 2026-05-14 — Backend foundation: skeleton, DB, schema, migration

Four PRs landed in one stretch — the boring-but-load-bearing layer the rest of the app sits on. ([#104](https://github.com/Eslam93/MagnaCMS/pull/104), [#105](https://github.com/Eslam93/MagnaCMS/pull/105), [#106](https://github.com/Eslam93/MagnaCMS/pull/106), [#107](https://github.com/Eslam93/MagnaCMS/pull/107).) The shape of each was determined more by infra correctness than by feature design — small things that ruin a week if you get them wrong on Day 5.

### FastAPI skeleton: middleware order matters

Starlette stacks middleware in reverse-add order. So if you write `app.add_middleware(CORS); app.add_middleware(AccessLog); app.add_middleware(RequestID)`, the request flows `Request → CORS → AccessLog → RequestID → handler`. We want CORS first (preflights short-circuit) and request-ID innermost (bound _before_ any handler runs, captured by access-log on the way out). That dictates the add order — and a comment in the source so the next reader doesn't reverse it on a "cleanup."

### The error envelope is a contract, not a convenience

Every failure path now produces the same shape:

```json
{
  "error":  { "code": "MACHINE_READABLE", "message": "human", "details": {...} },
  "meta":   { "request_id": "uuid" }
}
```

This means clients have exactly one shape to handle. `AppException` is the base, with subclasses for `NotFound`, `Unauthorized`, `Forbidden`, `Conflict`, `RateLimit`, `Provider`. Four handlers cover the universe: app exceptions, Starlette HTTP exceptions, Pydantic validation errors, and a catch-all for anything that escapes. The `request_id` flows through every envelope on handled paths (everything except bare uncaught exceptions, where FastAPI's per-route exception machinery runs the handler in a context our middleware can't yet reach — logs still carry the id; envelope on those paths may not. Tracked as a future hardening pass).

### Async Alembic is a copy-paste recipe — but mostly

The default `alembic init` template assumes sync engines. The async edition lives in the SQLAlchemy 2.0 docs — `run_async_migrations` opens an `AsyncEngine`, calls `connection.run_sync(do_run_migrations)` to hand the synchronous Alembic core a real connection. We also set `compare_type=True` + `compare_server_default=True` so autogenerate notices type drift (otherwise a `String(120) -> String(200)` change is invisible).

One non-obvious bit: importing `app.db` from `alembic/env.py` is what registers every model on `Base.metadata`. Without that side-effect import, autogenerate compares the live DB against an _empty_ metadata and thinks every table needs to be dropped. The `# noqa: F401` keeps lint quiet about the "unused" import.

### Two things `alembic --autogenerate` cannot do

1. **`CREATE EXTENSION citext`** — Postgres extension creation isn't a `Table` op. Has to be hand-added with `op.execute("CREATE EXTENSION IF NOT EXISTS citext")` at the top of `upgrade()`, before any `CITEXT` column is referenced.
2. **GIN expression indexes for full-text search** — `to_tsvector('english', rendered_text)` isn't a column reference; it's a SQL expression.

We added _both_ — and learned a trap on the GIN index. Initial approach used `op.execute("CREATE INDEX ... USING GIN ...")` and was satisfied. But `alembic check` then flagged the index as "removed" every time it ran, because the model didn't declare it. Fix: declare the expression index on `ContentPiece.__table_args__` using `Index(name, text("to_tsvector(...)"), postgresql_using="gin")`. Now the model and the live DB agree, and `alembic check` stays clean.

### Production-grade signaling: the small details

- **Refresh tokens** are stored as SHA-256 hashes, never as plaintext. Single-use rotation lands in P1.6 via a conditional `UPDATE ... WHERE revoked_at IS NULL` so concurrent reuse cannot mint two new pairs.
- **`metadata` is reserved on the SQLAlchemy `Base`**, so `UsageEvent` aliases the column attribute to `meta` while keeping the Postgres column name `metadata` — caught only by trying to declare it the obvious way.
- **`is_current` on `generated_images`** is enforced by a partial UNIQUE index — `(content_piece_id) WHERE is_current IS TRUE`. At most one current image per content piece, guaranteed at the DB layer, no app-side coordination needed.
- **The `users` table is intentionally not soft-deletable.** Soft delete + unique email = email-reuse-after-soft-delete collision. The brief calls this out; we honored it.

### What's next

Phase 1 has five tasks left: register/login (P1.5), refresh + logout + rotation (P1.6), provider abstractions with OpenAI primary + Mock fully implemented (P1.7a + P1.7b), security headers + auth rate limit (P1.9), and the test-fixture + coverage-gate consolidation pass (P1.8). The DB and the `User` / `RefreshToken` models are now ready — auth is the next thing that needs them.

---

## 2026-05-14 — Bootstrap day

### Pre-flight: choosing the AI provider

The original stack plan called for AWS Bedrock — Claude Sonnet 4.5 for text, Amazon Nova Canvas for image — all running inside AWS. The smoke calls before any code was written changed that.

Two findings stopped the Bedrock path:

1. **Claude Sonnet 4.5 on Bedrock requires submitting an "Anthropic use case details" form per AWS account.** Without it, every `bedrock-runtime:InvokeModel` call returns `ResourceNotFoundException`. The error message says "try again in 15 minutes," but the form review can take longer. For a project that wants to start building immediately, that's an unbounded blocker.
2. **Nova Canvas is `LEGACY` in `us-east-1` with EOL 2026-09-30.** It still works today, but writing the architecture around a model with a known end-of-life four months out felt wrong.

We considered Anthropic direct API as the alternative — same Claude family, no Bedrock wrapper. But Anthropic doesn't do image generation, so image still needed a separate provider (Replicate, fal.ai, or OpenAI). At that point the cleanest answer was to use OpenAI for both: one prepaid key covers text + image, no AWS-side enablement gates, and the underlying app architecture (provider abstractions, IAM role, AWS hosting) doesn't change.

Smoke tests confirmed:
- **Text:** a chat completion against `gpt-5.4-mini-2026-03-17` returns 200, tokens accounted, billing active.
- **Image:** `gpt-image-1` returns a 1.1 MB PNG at 1024×1024 `low` quality, ~$0.011 spent.

The Bedrock path stays alive as a documented alternative — `ILLMProvider` and `IImageProvider` are designed so swapping providers is a one-class change. If a future requirement makes Bedrock the right call again, no app code outside `app/providers/` is affected.

### Model-name humility

When the conversation suggested `gpt-5.4-mini` for text, we initially didn't recognize it — our knowledge of the OpenAI lineup was a few months behind. The right move was to list `/v1/models` against the live key and look at what's actually available rather than guess. `gpt-5.4-mini-2026-03-17` is real, current, and a strong fit. We pinned the dated variant for reproducibility — when OpenAI ships `gpt-5.4-mini-2026-XX-XX` next, our app won't silently re-route to it.

Lesson: when an external API surface is involved, _list, don't recall._

### Provider abstractions — the plan (not yet in code)

When the AI provider layer lands (next phase), `ILLMProvider` and `IImageProvider` will each have three implementations:

1. **OpenAI** — primary, real implementation.
2. **Mock** — fully built; returns canned valid JSON per content type (text) and a deterministic placeholder PNG (image). The point is to be able to run the full app end-to-end with zero API keys — useful for CI, useful for anyone who wants to see how the UI flows without spending a cent.
3. **Bedrock** — stubbed (`NotImplementedError`). Selectable via `AI_PROVIDER_MODE=bedrock` but the actual implementation only lands when there's a real reason to switch.

We rejected the `AnthropicDirectProvider` we'd originally considered. Keeping a half-built stub would advertise a fallback mode that doesn't actually work — worst of both worlds. If we want it later, we'll build it then.

_(As of this entry, `app/providers/` doesn't exist yet. The design above is what the next provider PR will implement; this paragraph is the spec, not a status report.)_

### Phase 0: the boring but load-bearing layer

Phase 0 was the unglamorous stuff: repo scaffold, Docker Compose with healthchecks, CI skeletons, `.env.example`, top-level docs, LICENSE. The principle behind making this a discrete phase: if the local-dev story doesn't work on day one, every later phase pays the tax.

Verified the bootstrap end-to-end — `docker-compose up` brings Postgres + Redis + service stubs to healthy in under 30 seconds, no warnings in logs beyond Redis's standard "no config file" notice.

The CI skeletons are intentionally pass-through today: each workflow checks whether `pyproject.toml` / `package.json` exists and runs the real pipeline only if so. That way the pipeline activates automatically the moment application code arrives — no one has to remember to wire it up.

### Going public

The repo is at https://github.com/Eslam93/MagnaCMS. Before pushing, a five-check secret audit:

1. `.env` is not tracked
2. `OpenAIKey.txt` never appeared in any commit
3. No `sk-proj-*` prefix in any tracked file
4. No `sk-proj-*` anywhere in git history (all branches, all reflogs)
5. No AWS access-key patterns in tracked files

All clean. Then the push, then branch protection: `main` requires PRs, linear history, no force-push, no deletion. Admin can bypass for emergencies (it's a solo project; required reviews would block self-merge).

### Externalizing the planning docs

The original brief, the phased task breakdown, and the GitHub-board bootstrap script were valuable as development scaffolding but didn't belong in a public-facing repo. They moved into a local-only `.private/` directory, gitignored. The README and `ARCHITECTURE.md` now stand on their own — anyone reading them gets the product, the stack, the trade-offs, and how to run it locally. Anyone curious about _how_ decisions were made reads this file.

### What's next

The next chunk of work is the backend foundations: FastAPI app skeleton with structured logging, async SQLAlchemy 2.0 + the full database schema, Alembic baseline migration, custom JWT auth with refresh-cookie rotation, the provider abstractions sketched above. A few footguns to watch for:

- **Alembic + async SQLAlchemy 2.0** — `env.py` needs to be wired carefully; the common copy-paste templates assume sync engines.
- **`MockLLMProvider` JSON shapes** — each content type's canned response needs to match the Pydantic schema we haven't written yet. Sequencing the schema before the mock keeps this honest.
- **CORS + httpOnly refresh cookie** between Amplify and App Runner — fiddly enough that we explicitly want to surface it on day one of the cloud deploy, not on day three when the frontend goes up. That's why the cloud deploy will wire real auth (not mocked) end-to-end the moment it lands.
