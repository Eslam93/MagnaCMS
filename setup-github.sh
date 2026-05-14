#!/usr/bin/env bash
#
# setup-github.sh — bootstrap the GitHub Project board for AI Content Marketing Suite
#
# Prerequisites:
#   - `gh` CLI installed and authenticated (`gh auth status` to verify)
#   - Run from inside the repo directory after `git init && git remote add origin ...`
#   - The remote repo must already exist on GitHub (private or public)
#
# What this does:
#   1. Creates ~15 labels (type, priority, size)
#   2. Creates 13 milestones (Phase 0 → Phase 12)
#   3. Creates ~80 issues, each assigned to its milestone with proper labels
#
# Idempotency:
#   - Labels: `--force` overwrites existing
#   - Milestones: skipped if same title exists
#   - Issues: NOT deduplicated. Re-running creates duplicates. Delete and re-run if needed.
#
# Project board setup (manual, takes ~2 minutes):
#   After this script completes:
#   1. Go to repo → Projects → New project → Board
#   2. Add a field "Phase" of type Single select with options Phase 0..Phase 12
#   3. Click "+ Add item" → search by milestone, bulk-add all issues
#   4. Group by Milestone or by Status — your call
#
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────
# Pre-flight
# ─────────────────────────────────────────────────────────────────────
if ! command -v gh &> /dev/null; then
  echo "❌ gh CLI not installed. https://cli.github.com/"
  exit 1
fi

if ! gh auth status &> /dev/null; then
  echo "❌ gh not authenticated. Run: gh auth login"
  exit 1
fi

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "")
if [ -z "$REPO" ]; then
  echo "❌ Not inside a GitHub repo, or repo has no remote. Run from inside the repo directory."
  exit 1
fi

echo "🎯 Target repo: $REPO"
read -p "Proceed? [y/N] " -n 1 -r
echo
[[ ! $REPLY =~ ^[Yy]$ ]] && exit 0

# ─────────────────────────────────────────────────────────────────────
# 1. Labels
# ─────────────────────────────────────────────────────────────────────
echo
echo "📌 Creating labels..."

create_label() {
  local name="$1"
  local color="$2"
  local desc="$3"
  gh label create "$name" --color "$color" --description "$desc" --force >/dev/null
  echo "   ✓ $name"
}

# Type labels
create_label "type:backend"  "0E7490" "Backend / FastAPI / Python work"
create_label "type:frontend" "0891B2" "Frontend / Next.js / TypeScript work"
create_label "type:infra"    "374151" "AWS / CDK / Docker / CI work"
create_label "type:ai"       "7C3AED" "Prompts / LLM / image gen"
create_label "type:docs"     "6B7280" "Documentation"
create_label "type:tests"    "A16207" "Tests"

# Priority labels
create_label "priority:critical" "DC2626" "Must not slip (brief §13)"
create_label "priority:high"     "F59E0B" "Important, not on cut line"
create_label "priority:medium"   "10B981" "Nice to have"
create_label "priority:cut-candidate" "9CA3AF" "On the cut line (brief §14)"

# Size labels (rough complexity)
create_label "size:S" "84CC16" "Small: <2h"
create_label "size:M" "EAB308" "Medium: half day"
create_label "size:L" "EF4444" "Large: full day or more"

# ─────────────────────────────────────────────────────────────────────
# 2. Milestones
# ─────────────────────────────────────────────────────────────────────
echo
echo "🎯 Creating milestones..."

create_milestone() {
  local title="$1"
  local desc="$2"
  # check if exists
  local existing
  existing=$(gh api "repos/$REPO/milestones?state=all" --jq ".[] | select(.title==\"$title\") | .number" 2>/dev/null || echo "")
  if [ -n "$existing" ]; then
    echo "   ↻ $title (exists, skipping)"
    return
  fi
  gh api "repos/$REPO/milestones" \
    -f title="$title" \
    -f description="$desc" \
    >/dev/null
  echo "   ✓ $title"
}

create_milestone "Prerequisites"                 "OpenAI API key funded + smoke calls verified. Before Day 1."
create_milestone "Phase 0: Bootstrap"            "Repo + docker-compose + CI skeleton. Day 1."
create_milestone "Phase 1: Backend Foundations"  "FastAPI app, DB models, auth, provider abstractions, sec headers + auth rate limit. Days 2-4."
create_milestone "Phase 2: Production Online"    "Thin vertical slice deployed to AWS (compute + edge). Days 5-6. Line in the sand."
create_milestone "Phase 3: Core AI Generation"   "All 4 content types generating cleanly. Days 7-8."
create_milestone "Phase 4: Frontend Core"        "Auth + generation UX end-to-end. Days 8-9."
create_milestone "Phase 5: Image Generation"     "OpenAI gpt-image-1, style picker, regen. Days 11-13."
create_milestone "Phase 6: Dashboard"            "List, search, filter, soft delete with undo. Day 12."
create_milestone "Phase 7: Improver"             "Two-call chain + diff UI. Day 13."
create_milestone "Phase 8: Brand Voice"          "CRUD + integration into generation. Day 14."
create_milestone "Phase 9: Exports & Usage"      "PDF/DOCX/MD exports, usage tracking. Days 15-16."
create_milestone "Phase 10: Polish"              "Errors, empty states, a11y, E2E. Days 17-18."
create_milestone "Phase 11: Hardening"           "Redis blocklist, idempotency, Sentry. Day 19."
create_milestone "Phase 12: Finalization"        "README, video, submission. Days 20-21."

# ─────────────────────────────────────────────────────────────────────
# 3. Issues
# ─────────────────────────────────────────────────────────────────────
echo
echo "📝 Creating issues..."

# Helper. Args: id, title, milestone, labels (comma-separated), body
create_issue() {
  local id="$1"
  local title="$2"
  local milestone="$3"
  local labels="$4"
  local body="$5"

  gh issue create \
    --title "[$id] $title" \
    --milestone "$milestone" \
    --label "$labels" \
    --body "$body" \
    >/dev/null
  echo "   ✓ [$id] $title"
}

# A standard body template — Claude Code knows to consult PHASES.md for full acceptance criteria
ac() {
  local id="$1"
  cat <<EOF
See **PHASES.md** → task **$id** for full acceptance criteria and references.

**Definition of Done:** see PROJECT_BRIEF.md §15.
EOF
}

# ─── Prerequisites ────────────────────────────────────────────────────
M="Prerequisites"
create_issue "P-1.1" "Verify OpenAI API access (text + image smoke calls)" "$M" "type:infra,type:ai,priority:critical,size:S" "$(ac P-1.1)"

# ─── Phase 0 ──────────────────────────────────────────────────────────
M="Phase 0: Bootstrap"
create_issue "P0.1" "Monorepo structure"        "$M" "type:infra,priority:critical,size:S" "$(ac P0.1)"
create_issue "P0.2" "Docker Compose for local dev" "$M" "type:infra,priority:critical,size:S" "$(ac P0.2)"
create_issue "P0.3" "Environment variable scaffold" "$M" "type:infra,priority:critical,size:S" "$(ac P0.3)"
create_issue "P0.4" "GitHub Actions CI skeletons" "$M" "type:infra,priority:high,size:S" "$(ac P0.4)"
create_issue "P0.5" "Documentation seeds" "$M" "type:docs,priority:critical,size:S" "$(ac P0.5)"
create_issue "P0.6" "Branch protection" "$M" "type:infra,priority:high,size:S" "$(ac P0.6)"
create_issue "P0.7" "Verify local-dev one-command bootstrap" "$M" "type:infra,priority:critical,size:S" "$(ac P0.7)"

# ─── Phase 1 ──────────────────────────────────────────────────────────
M="Phase 1: Backend Foundations"
create_issue "P1.1" "FastAPI application skeleton" "$M" "type:backend,priority:critical,size:M" "$(ac P1.1)"
create_issue "P1.2" "SQLAlchemy + Alembic setup" "$M" "type:backend,priority:critical,size:S" "$(ac P1.2)"
create_issue "P1.3" "Database models" "$M" "type:backend,priority:critical,size:M" "$(ac P1.3)"
create_issue "P1.4" "Initial migration" "$M" "type:backend,priority:critical,size:S" "$(ac P1.4)"
create_issue "P1.5" "Auth: registration, login, password handling" "$M" "type:backend,priority:critical,size:M" "$(ac P1.5)"
create_issue "P1.6" "Auth: refresh, logout, rotation" "$M" "type:backend,priority:critical,size:M" "$(ac P1.6)"
create_issue "P1.7" "Provider abstractions" "$M" "type:backend,type:ai,priority:critical,size:M" "$(ac P1.7)"
create_issue "P1.8" "Auth unit + integration tests" "$M" "type:tests,priority:high,size:S" "$(ac P1.8)"
create_issue "P1.9" "Security headers + basic auth rate limit" "$M" "type:backend,priority:high,size:S" "$(ac P1.9)"

# ─── Phase 2 ──────────────────────────────────────────────────────────
M="Phase 2: Production Online"
create_issue "P2.1" "CDK project bootstrap" "$M" "type:infra,priority:critical,size:S" "$(ac P2.1)"
create_issue "P2.2" "NetworkStack" "$M" "type:infra,priority:critical,size:S" "$(ac P2.2)"
create_issue "P2.3" "DataStack" "$M" "type:infra,priority:critical,size:M" "$(ac P2.3)"
create_issue "P2.4" "ComputeStack" "$M" "type:infra,priority:critical,size:M" "$(ac P2.4)"
create_issue "P2.5" "EdgeStack" "$M" "type:infra,priority:critical,size:M" "$(ac P2.5)"
create_issue "P2.6" "ObservabilityStack" "$M" "type:infra,priority:high,size:S" "$(ac P2.6)"
create_issue "P2.7" "First production deployment" "$M" "type:infra,priority:critical,size:M" "$(ac P2.7)"
create_issue "P2.8" "Deploy workflow" "$M" "type:infra,priority:critical,size:M" "$(ac P2.8)"
create_issue "P2.9" "Frontend on Amplify with real auth wired end-to-end" "$M" "type:frontend,priority:critical,size:M" "$(ac P2.9)"
create_issue "P2.10" "Sentry basic SDK init (backend + frontend)" "$M" "type:backend,type:frontend,priority:high,size:S" "$(ac P2.10)"

# ─── Phase 3 ──────────────────────────────────────────────────────────
M="Phase 3: Core AI Generation"
create_issue "P3.1" "Prompt module infrastructure" "$M" "type:backend,type:ai,priority:critical,size:S" "$(ac P3.1)"
create_issue "P3.2" "Blog post: prompt + schema + renderer" "$M" "type:ai,priority:critical,size:M" "$(ac P3.2)"
create_issue "P3.3" "OpenAI chat provider full implementation" "$M" "type:backend,type:ai,priority:critical,size:M" "$(ac P3.3)"
create_issue "P3.4" "Three-stage JSON parse fallback service" "$M" "type:backend,type:ai,priority:critical,size:M" "$(ac P3.4)"
create_issue "P3.5" "POST /content/generate endpoint" "$M" "type:backend,priority:critical,size:M" "$(ac P3.5)"
create_issue "P3.6" "LinkedIn post: prompt + schema + renderer" "$M" "type:ai,priority:critical,size:S" "$(ac P3.6)"
create_issue "P3.7" "Ad copy: prompt + schema + renderer" "$M" "type:ai,priority:cut-candidate,size:S" "$(ac P3.7)"
create_issue "P3.8" "Email: prompt + schema + renderer" "$M" "type:ai,priority:critical,size:S" "$(ac P3.8)"
create_issue "P3.9" "Integration tests across all 4 types" "$M" "type:tests,priority:high,size:M" "$(ac P3.9)"
create_issue "P3.10" "OpenAPI spec polish for content endpoints" "$M" "type:backend,type:docs,priority:high,size:S" "$(ac P3.10)"

# ─── Phase 4 ──────────────────────────────────────────────────────────
M="Phase 4: Frontend Core"
create_issue "P4.1" "Frontend foundations" "$M" "type:frontend,priority:critical,size:M" "$(ac P4.1)"
create_issue "P4.2" "Typed API client from OpenAPI" "$M" "type:frontend,priority:critical,size:S" "$(ac P4.2)"
create_issue "P4.3" "Auth client + pages" "$M" "type:frontend,priority:critical,size:M" "$(ac P4.3)"
create_issue "P4.4" "Protected layout" "$M" "type:frontend,priority:critical,size:M" "$(ac P4.4)"
create_issue "P4.5" "Generate page: form" "$M" "type:frontend,priority:critical,size:M" "$(ac P4.5)"
create_issue "P4.6" "Staged loading UI" "$M" "type:frontend,priority:high,size:S" "$(ac P4.6)"
create_issue "P4.7" "Result rendering per content type" "$M" "type:frontend,priority:critical,size:M" "$(ac P4.7)"
create_issue "P4.8" "Fallback-mode banner" "$M" "type:frontend,priority:high,size:S" "$(ac P4.8)"
create_issue "P4.9" "Error states + retry" "$M" "type:frontend,priority:high,size:S" "$(ac P4.9)"

# ─── Phase 5 ──────────────────────────────────────────────────────────
M="Phase 5: Image Generation"
create_issue "P5.1" "Image prompt builder" "$M" "type:backend,type:ai,priority:critical,size:M" "$(ac P5.1)"
create_issue "P5.2" "OpenAI gpt-image-1 provider" "$M" "type:backend,type:ai,priority:critical,size:M" "$(ac P5.2)"
create_issue "P5.3" "S3 upload + CloudFront URL" "$M" "type:backend,type:infra,priority:critical,size:M" "$(ac P5.3)"
create_issue "P5.4" "POST /content/:id/image endpoint" "$M" "type:backend,priority:critical,size:M" "$(ac P5.4)"
create_issue "P5.5" "Frontend: image display on result" "$M" "type:frontend,priority:critical,size:M" "$(ac P5.5)"
create_issue "P5.6" "Alternative image provider (Bedrock Nova Canvas)" "$M" "type:backend,type:ai,priority:cut-candidate,size:S" "$(ac P5.6)"
create_issue "P5.7" "Style picker" "$M" "type:frontend,type:ai,priority:high,size:S" "$(ac P5.7)"
create_issue "P5.8" "Regeneration flow" "$M" "type:frontend,type:backend,priority:critical,size:S" "$(ac P5.8)"
create_issue "P5.9" "Thumbnail strip of previous versions" "$M" "type:frontend,priority:cut-candidate,size:S" "$(ac P5.9)"

# ─── Phase 6 ──────────────────────────────────────────────────────────
M="Phase 6: Dashboard"
create_issue "P6.1" "List endpoint" "$M" "type:backend,priority:critical,size:S" "$(ac P6.1)"
create_issue "P6.2" "Detail endpoint" "$M" "type:backend,priority:critical,size:S" "$(ac P6.2)"
create_issue "P6.3" "Soft delete + restore" "$M" "type:backend,priority:critical,size:S" "$(ac P6.3)"
create_issue "P6.4" "Dashboard list page" "$M" "type:frontend,priority:critical,size:M" "$(ac P6.4)"
create_issue "P6.5" "Detail view" "$M" "type:frontend,priority:critical,size:M" "$(ac P6.5)"
create_issue "P6.6" "Delete with undo toast" "$M" "type:frontend,priority:high,size:S" "$(ac P6.6)"

# ─── Phase 7 ──────────────────────────────────────────────────────────
M="Phase 7: Improver"
create_issue "P7.1" "Improver service (two-call chain)" "$M" "type:backend,type:ai,priority:critical,size:M" "$(ac P7.1)"
create_issue "P7.2" "POST /improve endpoint" "$M" "type:backend,priority:critical,size:S" "$(ac P7.2)"
create_issue "P7.3" "Improver list + detail + delete" "$M" "type:backend,priority:high,size:S" "$(ac P7.3)"
create_issue "P7.4" "Improver frontend page" "$M" "type:frontend,priority:critical,size:M" "$(ac P7.4)"
create_issue "P7.5" "Side-by-side diff view" "$M" "type:frontend,priority:critical,size:M" "$(ac P7.5)"
create_issue "P7.6" "Improver history" "$M" "type:frontend,priority:medium,size:S" "$(ac P7.6)"

# ─── Phase 8 ──────────────────────────────────────────────────────────
M="Phase 8: Brand Voice"
create_issue "P8.1" "CRUD endpoints" "$M" "type:backend,priority:high,size:S" "$(ac P8.1)"
create_issue "P8.2" "Brand voices page" "$M" "type:frontend,priority:high,size:M" "$(ac P8.2)"
create_issue "P8.3" "Integration into generate form" "$M" "type:frontend,priority:high,size:S" "$(ac P8.3)"
create_issue "P8.4" "Brand voice block injection" "$M" "type:backend,type:ai,priority:high,size:S" "$(ac P8.4)"
create_issue "P8.5" "Seed script updated" "$M" "type:backend,priority:medium,size:S" "$(ac P8.5)"

# ─── Phase 9 ──────────────────────────────────────────────────────────
M="Phase 9: Exports & Usage"
create_issue "P9.1" "PDF export" "$M" "type:backend,priority:high,size:M" "$(ac P9.1)"
create_issue "P9.2" "DOCX export" "$M" "type:backend,priority:cut-candidate,size:M" "$(ac P9.2)"
create_issue "P9.3" "Markdown export" "$M" "type:backend,priority:high,size:S" "$(ac P9.3)"
create_issue "P9.4" "usage_events table + recording" "$M" "type:backend,priority:medium,size:S" "$(ac P9.4)"
create_issue "P9.5" "GET /usage/summary endpoint" "$M" "type:backend,priority:medium,size:S" "$(ac P9.5)"
create_issue "P9.6" "Usage page" "$M" "type:frontend,priority:cut-candidate,size:M" "$(ac P9.6)"

# ─── Phase 10 ─────────────────────────────────────────────────────────
M="Phase 10: Polish"
create_issue "P10.1" "Error boundaries" "$M" "type:frontend,priority:high,size:S" "$(ac P10.1)"
create_issue "P10.2" "Toast notifications consistency" "$M" "type:frontend,priority:high,size:S" "$(ac P10.2)"
create_issue "P10.3" "Empty states" "$M" "type:frontend,priority:high,size:S" "$(ac P10.3)"
create_issue "P10.4" "404 and 500 pages" "$M" "type:frontend,priority:high,size:S" "$(ac P10.4)"
create_issue "P10.5" "Dark mode polish" "$M" "type:frontend,priority:medium,size:S" "$(ac P10.5)"
create_issue "P10.6" "Mobile responsive audit" "$M" "type:frontend,priority:high,size:M" "$(ac P10.6)"
create_issue "P10.7" "Accessibility pass" "$M" "type:frontend,priority:high,size:M" "$(ac P10.7)"
create_issue "P10.8" "Playwright E2E" "$M" "type:tests,priority:cut-candidate,size:M" "$(ac P10.8)"
create_issue "P10.9" "Loading skeletons" "$M" "type:frontend,priority:medium,size:S" "$(ac P10.9)"

# ─── Phase 11 ─────────────────────────────────────────────────────────
M="Phase 11: Hardening"
create_issue "P11.1" "Redis blocklist for refresh tokens" "$M" "type:backend,priority:cut-candidate,size:S" "$(ac P11.1)"
create_issue "P11.2" "Idempotency middleware" "$M" "type:backend,priority:high,size:M" "$(ac P11.2)"
create_issue "P11.3" "Rate limiting tuned per endpoint" "$M" "type:backend,priority:high,size:M" "$(ac P11.3)"
create_issue "P11.4" "Circuit breaker on OpenAI provider" "$M" "type:backend,priority:cut-candidate,size:S" "$(ac P11.4)"
create_issue "P11.5" "Sentry integration" "$M" "type:backend,type:frontend,priority:high,size:S" "$(ac P11.5)"
create_issue "P11.6" "CloudWatch alarm" "$M" "type:infra,priority:cut-candidate,size:S" "$(ac P11.6)"
create_issue "P11.7" "Security headers middleware" "$M" "type:backend,priority:high,size:S" "$(ac P11.7)"

# ─── Phase 12 ─────────────────────────────────────────────────────────
M="Phase 12: Finalization"
create_issue "P12.1" "README full polish" "$M" "type:docs,priority:critical,size:M" "$(ac P12.1)"
create_issue "P12.2" "ARCHITECTURE.md" "$M" "type:docs,priority:critical,size:S" "$(ac P12.2)"
create_issue "P12.3" "OpenAPI doc review" "$M" "type:docs,priority:high,size:S" "$(ac P12.3)"
create_issue "P12.4" "Demo seed quality" "$M" "type:backend,priority:critical,size:S" "$(ac P12.4)"
create_issue "P12.5" "Video script" "$M" "type:docs,priority:critical,size:S" "$(ac P12.5)"
create_issue "P12.6" "Video recording + editing" "$M" "type:docs,priority:critical,size:M" "$(ac P12.6)"
create_issue "P12.7" "Final smoke test" "$M" "type:tests,priority:critical,size:S" "$(ac P12.7)"
create_issue "P12.8" "Submission" "$M" "type:docs,priority:critical,size:S" "$(ac P12.8)"

echo
echo "✅ Done. Created labels, 13 milestones, and ~80 issues."
echo
echo "Next steps:"
echo "  1. Go to https://github.com/$REPO/projects and create a new Project (Board view)."
echo "  2. Add a 'Status' field (Todo, In Progress, In Review, Done) — usually default."
echo "  3. Bulk-add issues to the project: 'Add item' → search → multi-select."
echo "  4. Group by Milestone in the board view for a phase-organized Kanban."
echo "  5. Paste KICKOFF_PROMPT.md into Claude Code to begin."
