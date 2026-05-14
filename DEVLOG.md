# Development log

A running journal of decisions, trade-offs, and progress on MagnaCMS. Newest entries first. Each entry is written when something interesting happens — not on a schedule — so the cadence reflects the actual pace of work.

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

### Provider abstractions, but not too many

`ILLMProvider` and `IImageProvider` have three implementations each:

1. **OpenAI** — primary, full implementation.
2. **Mock** — fully built; returns canned valid JSON per content type (text) and a deterministic placeholder PNG (image). The point is to be able to run the full app end-to-end with zero API keys — useful for CI, useful for anyone who wants to see how the UI flows without spending a cent.
3. **Bedrock** — stubbed (`NotImplementedError`). Selectable via `AI_PROVIDER_MODE=bedrock` but the actual implementation only lands when there's a real reason to switch.

We rejected the `AnthropicDirectProvider` we'd originally considered. Keeping a half-built stub felt like the worst of both worlds — it would advertise a fallback mode that doesn't actually work. If we want it later, we'll build it then.

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
