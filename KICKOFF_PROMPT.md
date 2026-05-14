# Claude Code Kickoff — AI Content Marketing Suite

You are the primary builder for this project. We're shipping a production-grade AI content marketing SaaS over ~3 weeks. The deliverables are a deployed app, a public GitHub repo, a video walkthrough, and clean documentation.

## Sources of truth

Read these in order before doing anything else:

1. **`PROJECT_BRIEF.md`** — full architecture, stack, database schema, API contract, prompt templates, NFRs, AWS infra plan, 3-week timeline, must-not-slip features, cut line.
2. **`PHASES.md`** — the task-level breakdown organized into 13 phases (0–12). Each task has an ID (`P0.1`, `P1.3`, etc.), acceptance criteria, and references back to brief sections.
3. **`README.md`** — will grow as we build; treat as the evaluator-facing doc.

If the brief and phases conflict, the brief wins. If you disagree with either, raise it before deviating.

## What we're scored on

So you optimize for the right things:

- **LLM & Prompt Quality (25 pts)** — distinct strategies per content type, structured JSON outputs, three-stage parse fallback, relevance and craft
- **AI Image Generation (20 pts)** — auto image-prompt builder, image-content match, smooth UX flow
- **Backend & API Design (20 pts)** — clean structure, robust error handling, security thinking, thorough README/OpenAPI docs
- **Frontend & UI/UX (15 pts)** — usability, design quality, responsiveness
- **Claude Code Usage (15 pts)** — must be visible in the demo video
- **Bonus (+10)** — brand voice, image style picker, export (PDF / DOCX / Markdown)

Production-grade signaling is part of the deal. Do not cut corners that show.

## Working agreement

**Branching.** `main` is protected. One task = one branch = one PR. Branch names: `feat/p1-3-jwt-auth`, `fix/...`, `chore/...`. PR titles include the task ID: `[P1.3] Implement custom JWT auth with refresh rotation`.

**Commits.** Conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`).

**PRs.** Open as draft early. The body must:
- Reference the issue: `Closes #N`
- Include a "How I tested" section with concrete steps
- Note any deviations from the brief and why

Linter, typecheck, and tests green before marking ready for review.

**Quality bar.** No `TODO` without a tracked issue. No commented-out code. No `print()` debugging left in. No `# type: ignore` or `// @ts-ignore` without a comment explaining why. Production-grade only.

**When ambiguous.** Propose an interpretation, don't invent silently. Ask in chat, not in code comments.

**When you find a better way.** Raise it. Don't deviate without sign-off. If approved, update the brief or phases in the same PR that changes the code.

**Docs always.** If a change affects the API contract, database schema, or any documented behavior, update `PROJECT_BRIEF.md` in the same PR.

## Style

- **Python:** Ruff format + Ruff lint, mypy strict on `app/`, pytest + pytest-asyncio. Async throughout. Pydantic v2 for all I/O.
- **TypeScript:** strict mode, no `any`, ESLint + Prettier, TanStack Query for server state, Zod for validation, React Hook Form for forms.
- **Tests:** service-layer unit tests, one integration test per API endpoint, one Playwright happy-path E2E by Phase 10.
- **Logs:** structured JSON via structlog. Every log line includes `request_id` and `user_id` where available.
- **Secrets:** never logged, never in error messages, never committed.

## Your first task — do NOT start coding yet

Do this and reply:

1. Read `PROJECT_BRIEF.md` end to end.
2. Read `PHASES.md` end to end.
3. Reply with:
   - **A 5-8 sentence summary in your own words** covering the stack, the architecture, the must-not-slip features, the cut line, and the two or three most likely failure modes (this proves you read everything and understand the tradeoffs).
   - **Disagreements with `PHASES.md`** — order, missing tasks, scope concerns, anything that looks underestimated. Push back. I want your critique, not your compliance.
   - **Confirmation of the working agreement** above.

Once we align, I will say **"Start Phase 0."** From that point on, your loop for each phase is:

1. **Pre-flight:** review the phase's tasks in `PHASES.md`, flag risks, propose adjustments to acceptance criteria, estimate complexity.
2. **Execute:** create a feature branch per task, open draft PRs early, push regularly, mark ready when green.
3. **Post-flight:** update `README.md` and `PROJECT_BRIEF.md` if anything user-facing or contractual changed. Confirm the phase is done. Wait for **"Start Phase N+1."**

Begin with steps 1–3 of "Your first task" now.
