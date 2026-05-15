# MagnaCMS — Slice Execution Plan (Active)

> **This file is the operating manual for the current Claude Code session and any successor sessions (compaction, dispatcher pattern, fresh context).** Read this top-to-bottom before editing code. When state changes (a slice merges, a deploy fact shifts, a known issue is resolved), update this file in the same commit.

**Last updated:** 2026-05-15 (after Slice 4 merge — dashboard with list/detail/soft delete + undo).

---

## 1. Current state (one screen)

| | Status |
|---|---|
| Slice 0 — Deploy fix gate (P2.11 + P2.12 + P2.13) | ✅ shipped, merged into main |
| Slice 1 — Text gen, blog only, mock + OpenAI | ✅ shipped in [#135](https://github.com/Eslam93/MagnaCMS/pull/135), merged into main |
| Slice 2 — Text gen widened (LinkedIn + email + ad copy) | ✅ shipped in [#137](https://github.com/Eslam93/MagnaCMS/pull/137), merged into main |
| Slice 4 — Dashboard (list + detail + soft delete) | ✅ shipped in [#138](https://github.com/Eslam93/MagnaCMS/pull/138), merged into main |
| Live AWS deploy | ✅ partial — backend RUNNING, DB migrated, **frontend zip built but not yet uploaded** |
| Deploy-time fixes (em-dash, NoDecode, migration env, Fargate SG) | em-dash + NoDecode: code in repo. Migration env + SG: documented in §4 as deploy-time TODOs (band-aided live, CDK code unchanged). |
| Remaining slices | 3, 5, 6 (in that order — see §3 for rationale) |
| Time budget | **12 hours of local-first feature work, then 1-2h batch deploy + polish at the end of 24h.** |

### Live deploy snapshot (preserve — do NOT redeploy in this 12h window)

| | Value |
|---|---|
| AWS account | `383158157541` |
| Region | `us-east-1` |
| Backend (App Runner) | `https://grsv8u4uit.us-east-1.awsapprunner.com` |
| App Runner service ARN | `arn:aws:apprunner:us-east-1:383158157541:service/magnacms-dev-backend/f583fd15bb454462acf6e5c69562d9b1` |
| Amplify app ID | `dew27gk9z09jh` (frontend zip awaiting one-click upload at `frontend/magnacms-frontend.zip`) |
| Amplify branch URL (post-upload) | `https://main.dew27gk9z09jh.amplifyapp.com` |
| RDS endpoint | `magnacms-dev-data-postgres9dc8bb04-ux1ipoo5aqsk.cs1yoi4ygnyc.us-east-1.rds.amazonaws.com` |
| Demo user already registered | `demo@magnacms.dev` / `DemoPass123` |
| Verified end-to-end | register + `/auth/login` + `/content/generate` (blog post) against real OpenAI `gpt-5.4-mini-2026-03-17`, $0.000988 / generation. Content row exists with id `a16bd28f-362e-420b-a742-0e365dbc7f5d`. |

**Approx idle burn: ~$70-80/mo if left running.** Tear down with `cd infra && npx cdk destroy --all -c env=dev` when demo is done.

---

## 2. Slice 1 — what shipped (reference for pattern-matching)

PR [#135](https://github.com/Eslam93/MagnaCMS/pull/135). Files:

- `backend/app/schemas/content.py` — `GenerateRequest` (open to all `ContentType`s), `BlogPostResult`, `GenerateResponse`, `GenerateUsage`
- `backend/app/prompts/blog_post.py` — `PROMPT_VERSION="blog_post.v1"`, `SYSTEM_PROMPT`, `JSON_SCHEMA`, `build_prompt(...)`, `CORRECTIVE_RETRY_INSTRUCTION`
- `backend/app/services/renderers/blog_post.py` — pure `render_blog_post(result) -> str` + `word_count(text) -> int`
- `backend/app/services/content_service.py` — `ContentService.generate_blog_post(user, request)` with three-stage fallback (parse → corrective retry → graceful degrade)
- `backend/app/repositories/content_repository.py` — `create`, `get_for_user`
- `backend/app/api/v1/routers/content.py` — `POST /content/generate`, slice-1 gate rejecting non-blog content types with 422 `UNSUPPORTED_CONTENT_TYPE`
- `backend/app/main.py` — rate-limit row added: `/api/v1/content/generate` at 20/min
- `frontend/types/api.d.ts` — paths + components (ContentType, BlogPostResult, GenerateRequest/Response, GenerateUsage)
- `frontend/lib/validation/generate.ts` — Zod schema + `CONTENT_TYPE_OPTIONS` (blog enabled; others disabled with tooltip)
- `frontend/lib/content/hooks.ts` — `useGenerateMutation`, `generateErrorMessage`
- `frontend/components/features/generate-form.tsx` — RHF + Zod, content-type tabs, error+dismiss
- `frontend/components/features/staged-loader.tsx` — three-phase cycling label
- `frontend/components/features/generate-result.tsx` — `react-markdown` render + copy + fallback-mode banner
- `frontend/app/(protected)/generate/page.tsx` — page hosting the form
- Backend tests: `tests/test_blog_post_renderer.py`, `tests/test_content_service.py`, `tests/integration/test_content_routes.py`
- Frontend tests: `tests/generate-form.test.tsx` (6 tests, mocks the mutation hook)

**Test totals:** Backend 162 pass, 24 integration skip without local Postgres. Frontend 9 pass.

---

## 3. Remaining slices (ordered, with done-when criteria)

Order: **2 → 4 → 3 → 5 → 6**. Rationale: Slice 4 (dashboard) before Slice 3 (image gen) because the dashboard is what makes Slice 2's three new content types feel real (without a list, generated content vanishes from the UI). Slice 3 is the highest-risk; placing it in the middle prevents a wrinkle from killing the final hours.

### Slice 2 — Text gen widened (LinkedIn + email + ad copy)

✅ **Shipped in [#137](https://github.com/Eslam93/MagnaCMS/pull/137).** Registry-based dispatch in `content_service.py` pairs each content type with its prompt module + Pydantic result model + renderer; three-stage parse fallback stays shared. Router projects stored JSONB back through the right per-type model. Frontend flips the three disabled tabs and widens `api.d.ts` to a `ContentResult` union. Tests: 204 backend pass (28 integration skip locally), 10 frontend pass, 36 infra jest pass, all stacks synth. Prettier `--check` warns locally on Windows CRLF; clean with `endOfLine=auto`, CI on Linux sees LF.

### Slice 4 — Dashboard (list + detail + soft delete)

✅ **Shipped in [#138](https://github.com/Eslam93/MagnaCMS/pull/138).** `ContentRepository` got `list_for_user` (pagination + filter + `plainto_tsquery` against the GIN index on `rendered_text`), `soft_delete`, `restore` (24-hour window). New endpoints: `GET /content` (paginated envelope), `GET /content/:id`, `DELETE /content/:id` (soft delete), `POST /content/:id/restore`. Frontend replaced the welcome stub with `ContentList` + `ContentCard` + `ContentDetailDialog` + sonner Undo toast; added `components/ui/modal.tsx` (no Radix dialog dep). Tests: 204 backend pass + 13 integration skip locally for the new dashboard, 14 frontend pass (+4), 36 infra jest pass, all stacks synth.

### Slice 3 — Image generation

**Branch:** `slice-3/image-gen`. **Budget:** ~2.5h. **Highest risk slice.**

Done when:
- [ ] Backend:
  - `backend/app/prompts/image_prompt_builder.py` — per §7.5 of brief; runs as a separate OpenAI chat call AFTER content is generated. Output: `{ prompt, negative_prompt, style_summary }`.
  - `backend/app/providers/image/openai_provider.py` — already stubbed; flesh out `OpenAIImageProvider` to call `gpt-image-1` and return bytes + cost.
  - `backend/app/services/image_service.py` — orchestrates: load content piece → build image prompt (via LLM call) → generate image (via image provider) → upload bytes to S3 with UUID key → mark previous current=false → insert new `generated_images` row with `is_current=true` → return.
  - `backend/app/repositories/image_repository.py` — `create`, `mark_others_not_current`, `list_for_content`.
  - `POST /api/v1/content/:id/image` — body `{ style?, provider? }`. Returns `{ image }` with full `generated_images` row including `cdn_url`.
  - `GET /api/v1/content/:id/images` — list all versions for a content piece.
  - S3 upload: use `app.core.aws_secrets` infra OR a new `app/services/s3_service.py`. For Slice 3 local-first: write to local disk and serve via `GET /local-images/...` when `IMAGES_CDN_BASE_URL=http://localhost:8000/local-images` (already the default).
  - For deployed mode: use `boto3` to put object into `s3_bucket_images`, generate a presigned URL (no CloudFront yet — that's Phase 5 per brief).
- [ ] Frontend:
  - Extend `frontend/types/api.d.ts` with `GeneratedImage` and image endpoints.
  - On the `generate-result.tsx` panel: add a "Generate image" button (only enabled when `result_parse_status === 'ok'`).
  - New `components/features/image-panel.tsx` — shows current image, style picker (six styles: photorealistic, illustration, minimalist, 3d_render, watercolor, cinematic), "Regenerate" button. Versions: simple flat thumbnail strip showing previous versions (no lightbox).
- [ ] Tests:
  - Backend: mock provider tests for image generation (existing `MockImageProvider` returns a placeholder PNG). Integration test: POST `/content/:id/image` → row inserted, `is_current=true`, old rows flipped.
  - Frontend: vitest covering the image panel — generate button calls mutation, regenerate flips the displayed image.
- [ ] DEVLOG; README §6 update; brief §17 cut-line note that CloudFront is still deferred.
- [ ] PR title: `[Slice 3] Image generation: gpt-image-1 + S3 + regenerate`

**Risk callouts:**
- `gpt-image-1` returns base64 PNG by default — handle the encoding in the provider.
- Local dev needs a path that doesn't require S3 — `IMAGES_CDN_BASE_URL=http://localhost:8000/local-images` + a local-file fallback. Document this in `.env.example`.
- Cost: `gpt-image-1` at `medium` quality is ~$0.042/image. Multiply by demo count — set `OPENAI_IMAGE_QUALITY=low` by default for dev to keep bills sane.

### Slice 5 — Improver

**Branch:** `slice-5/improver`. **Budget:** ~2h.

Done when:
- [ ] Backend:
  - `backend/app/prompts/improver.py` — two prompts (analyze + rewrite) per §7.6 of brief; `ImproverGoal` enum already exists in `db/enums.py`.
  - `backend/app/schemas/improvement.py` — `ImproveRequest`, `ImproveResponse` (mirrors §7.6 JSON shape: `improved_text`, `explanation`, `changes_summary`).
  - `backend/app/services/improver_service.py` — two-call chain. Call 1 returns `{issues, planned_changes}`; Call 2 receives the planned changes and returns the final `ImproveResponse` JSON. Same three-stage fallback as content service.
  - `backend/app/repositories/improvement_repository.py` — `create`, `list_for_user`, `get_for_user`, `soft_delete`.
  - `POST /api/v1/improve` — non-streaming (brief explicitly allows non-streaming).
  - `GET /api/v1/improvements`, `GET /api/v1/improvements/:id`, `DELETE /api/v1/improvements/:id`.
- [ ] Frontend `app/(protected)/improve/page.tsx`:
  - Replace stub with full form: textarea for `original_text`, goal selector (5 options), conditional `new_audience` field for `audience_rewrite`.
  - Result panel: side-by-side diff view of original vs improved. Use a tiny diff lib (e.g., `diff` from npm) OR a simpler two-pane "before / after" view. Cuttable: skip the diff and just show two panels.
  - Show `explanation` bullets below the diff. Show `changes_summary` as a small metadata block (length change %, tone shift, etc.).
- [ ] Tests:
  - Backend: unit tests for both calls in the chain (mocked LLM with canned responses already in `MockLLMProvider`'s `improver_analysis` + `improver_rewrite` keys). Integration test for the endpoint.
  - Frontend: 1 vitest covering form submission + result render.
- [ ] DEVLOG; README §6 update.
- [ ] PR title: `[Slice 5] Improver: analyze → rewrite chain with side-by-side diff`

### Slice 6 — Brand voice (mini)

**Branch:** `slice-6/brand-voice-mini`. **Budget:** ~1.5h.

Done when:
- [ ] Backend:
  - `backend/app/schemas/brand_voice.py` — `BrandVoiceCreate`, `BrandVoiceUpdate`, `BrandVoiceResponse`.
  - `backend/app/services/brand_voice_service.py` + `repositories/brand_voice_repository.py`.
  - `GET /api/v1/brand-voices`, `POST /api/v1/brand-voices`, `GET /:id`, `PATCH /:id`, `DELETE /:id`.
  - Prompt injection: when `GenerateRequest.brand_voice_id` is present, fetch the voice and pass `brand_voice_block` to each prompt's `build_prompt()` per §7.7 of brief. All four prompt modules already accept `brand_voice_block: str | None = None`.
- [ ] Frontend `app/(protected)/brand-voices/page.tsx`:
  - List of own voices with create/edit/delete affordances.
  - `BrandVoiceForm` component (name, description, tone_descriptors as comma-separated input, banned_words, sample_text, target_audience).
- [ ] `generate-form.tsx`: add an optional brand-voice dropdown (fetched via TanStack Query). Selected voice id flows into the generate request.
- [ ] Tests: backend integration tests for CRUD; frontend smoke covering form + injection.
- [ ] DEVLOG; README §6 update.
- [ ] PR title: `[Slice 6] Brand voice mini: CRUD + inject into generate`

### Polish + Slice 7 (combined into final pass)

**Branch:** `polish/demo-readiness`. **Budget:** ~1.5h.

Done when:
- [ ] `backend/app/scripts/seed.py` — creates demo user (email + password printed), one brand voice, three example content pieces with images, one improvement.
- [ ] README §1: paste live URLs (`https://main.dew27gk9z09jh.amplifyapp.com` once frontend is up, `https://grsv8u4uit.us-east-1.awsapprunner.com/api/v1/health` for backend) and demo credentials.
- [ ] Skim each protected page for empty/error/loading states. Toast notifications on every mutation.
- [ ] Mobile width sanity pass at 375px.
- [ ] DEVLOG final entry.

---

## 4. Known deploy-time issues (fix at hour 22, NOT now)

These were discovered during today's first deploy. Workarounds applied at runtime; durable fixes need code changes when we prep to redeploy.

| # | Issue | Symptom | Live workaround | Permanent fix needed |
|---|---|---|---|---|
| 1 | Em-dash (U+2014) in SG ingress rule description | EC2 rejects with "Invalid rule description" | Fixed in working tree (network-stack.ts, data-stack.ts, edge-stack.ts) | Commit with this PR |
| 2 | `CORS_ORIGINS` pydantic-settings JSON-decode error | App Runner container exits at startup | Fixed in working tree (`config.py` — `NoDecode` annotation) | Commit with this PR |
| 3 | Migration Fargate task missing JWT_SECRET + OPENAI_API_KEY secret refs | `alembic upgrade head` crashes at config validator | Manually passed via `aws ecs run-task --overrides` JSON | Add `secrets:` block to `compute-stack.ts` migration task definition |
| 4 | Fargate task gets default VPC SG with no egress rules (CDK's VpcRestrictDefaultSGCustomResource strips them) | Task can't reach ECR → `ResourceInitializationError` | Manually created `sg-0ce94d55ce2078fc8` (magnacms-dev-fargate-egress) | Add a dedicated `sgFargateEgress` SG to `network-stack.ts`, attach in `compute-stack.ts` migration task's `awsvpcConfiguration` (CDK reads via task-definition + service network config), and document the manual `run-task` call to pass `--network-configuration ...securityGroups=[sgId]...` |
| 5 | App Runner `CORS_ORIGINS` doesn't include Amplify URL | Frontend cross-origin fetches blocked | Manually updated via `aws apprunner update-service` to `https://main.dew27gk9z09jh.amplifyapp.com,http://localhost:3000` | Update `compute-stack.ts` value + document in `infra/DEPLOY.md` post-deploy step |
| 6 | App Runner CFN `--no-rollback` leaves stack in CREATE_FAILED if first deploy fails | Subsequent deploys need `--no-rollback` flag too (TTY prompt otherwise) | Used `--no-rollback` consistently | Document in `infra/DEPLOY.md` |
| 7 | Stale `cdk.out/*.lock` files block subsequent deploys when a cdk process is killed | Deploys silently no-op | `rm -f infra/cdk.out/*.lock` | Document in `infra/DEPLOY.md` troubleshooting section |
| 8 | Static export via `NEXT_OUTPUT=export` env var added to `next.config.ts` | One-off manual Amplify zip upload | Already in repo (conditional, off by default) | Either keep (it's harmless) or remove once GitHub auto-deploy is wired |

---

## 5. Working agreement (carryover from kickoff doc)

- **Branch naming:** `slice-N/short-noun-phrase`. Branch off latest `main`. Rebase before pushing if main moved.
- **Commit style:** conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`). Small commits, not one mega-blob. **NO Co-Authored-By trailers** (the user's global git config disables attribution).
- **PR title:** `[Slice N] <one-line outcome>`. Body must include 3-bullet summary, "How I tested" with concrete commands, and any deviation from this plan with a one-line reason.
- **PR scope:** one slice per PR. Auto-merge with `--auto` once CI is green (user reviews via diff, not running locally).
- **Quality bar:** No `TODO` without a tracked issue. No commented-out code. No `print()` debugging. No `# type: ignore` / `@ts-ignore` without an inline reason. New backend endpoints have an integration test. New frontend pages have at least one component test.
- **Test commands:**
  - Backend: `cd backend && python -m uv run ruff check . && python -m uv run ruff format --check . && python -m uv run mypy app && python -m uv run pytest tests/ -q`
  - Frontend: `cd frontend && pnpm tsc --noEmit && pnpm lint && pnpm prettier --check . && pnpm test --run && pnpm build`
  - Infra: `cd infra && npm test && npx cdk synth --all -c env=dev`
- **Docs:** Update `README.md` if user-facing behavior changes. Update `.private/PROJECT_BRIEF.md` (gitignored — local only) if a contract changes. DEVLOG entry per slice.
- **When ambiguous:** propose, don't invent silently. Pick a default and call it out in the PR body.
- **When you find a better way:** raise it. Don't deviate without sign-off.
- **No live AWS deploys in this 12h window.** Every minute on App Runner has been double-cost in deploy time + token budget. Defer all deploy work to a single batch in the final 1-2h.

---

## 6. How to resume from a fresh session / dispatcher

A dispatcher session starting on this repo should:

1. Read this `SLICE_PLAN.md` top-to-bottom.
2. Run `git log --oneline -10` and `git branch --show-current` to confirm state.
3. Check open PRs: `gh pr list --state open`.
4. Identify the next slice from §3 by finding the highest `[ ]` un-checked done-when block.
5. Branch off `main`: `git checkout main && git pull && git checkout -b slice-N/...`.
6. Follow the slice's done-when checklist. Run the test commands from §5 before pushing.
7. Open the PR, auto-merge it when CI is green.
8. **Update this file** when the slice merges — flip the slice row in §3 from done-when checklist to a one-line "✅ shipped in #PR-NUMBER", mark §1 status row complete, push to main as a docs commit (no PR needed for handoff doc updates).
9. Begin the next slice. Repeat.

For deploy-related questions: `infra/DEPLOY.md` is the runbook. The §4 known issues here supersede the runbook until the durable fixes ship.

For brief / scope questions: `.private/PROJECT_BRIEF.md` (gitignored, only present in the user's local checkout) is the canonical source. If you don't have it, ask the user before assuming.

---

## 7. Slice-1 "PROJECT_BRIEF" gitignored note

The user updated `.private/PROJECT_BRIEF.md` locally during Slice 1 to footnote the blog-only Slice 1 scope on §6's content row. That edit didn't ship in PR #135 because `.private/` is gitignored. The README's §6 carries the same caveat publicly. When future slices change the public contract, update both files in the same session.
