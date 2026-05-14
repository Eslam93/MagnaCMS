# Architecture decisions

> One-page summary of the load-bearing choices and the trade-offs behind them. Companion to [`PROJECT_BRIEF.md`](./PROJECT_BRIEF.md), which has the full architecture, schema, and API contract.
>
> **Status:** Phase 0 stub. Final pass in P12.2 will add the AWS cost estimate for the 7-day live window and the post-Phase-12 "what I'd build next" paragraph.

## Stack snapshot

| Concern | Choice | Alternatives rejected |
|---|---|---|
| Text generation | OpenAI `gpt-5.4-mini-2026-03-17` | AWS Bedrock Claude Sonnet 4.5 (Anthropic use-case form is a multi-hour gate); Anthropic direct (no image gen) |
| Image generation | OpenAI `gpt-image-1` | AWS Bedrock Nova Canvas (LEGACY, EOL 2026-09-30); Replicate / fal.ai (additional account) |
| Backend host | AWS App Runner (no VPC connector) | Fargate (more wiring); Lambda (cold start + 15-min cap); Vercel (mismatched runtime for async Python) |
| Frontend host | AWS Amplify Hosting | Vercel (great DX, but introduces second cloud and DNS story); App Runner static (lacks Next.js SSR/middleware) |
| Database | RDS Postgres `db.t4g.micro`, public subnet, strict SG | RDS in private subnet (requires VPC connector + complications); Aurora (overkill for demo); Supabase (third cloud) |
| Auth | Custom JWT + httpOnly refresh cookie + rotation | Cognito (more moving parts, less control over rotation); Auth0 (cost + vendor lock-in) |
| Streaming | Non-streaming for content generation | SSE everywhere (structured JSON does not stream cleanly; partial parses surface broken UX) |

## Load-bearing decisions

### 1. OpenAI direct over AWS Bedrock
Bedrock's Claude Sonnet 4.5 requires submitting an Anthropic use-case form per AWS account, and the bare model ID does not support ON_DEMAND inference (must use the `us.` cross-region inference profile). Nova Canvas is `LEGACY` with EOL **2026-09-30**. OpenAI bypasses both: one prepaid key covers text + image, smoke calls verify in seconds. Provider abstractions in `app/providers/llm` and `app/providers/image` keep Bedrock as a one-class swap if requirements change.

### 2. No VPC connector on App Runner
With a VPC connector, App Runner loses public internet egress unless we add NAT Gateway (~$32/mo) or VPC endpoints for every AWS service we call (S3, Secrets Manager) plus the public OpenAI API. For a 3-week build with a 7-day live window, the cleaner trade is: keep App Runner public, lock RDS down with a strict SG keyed to App Runner's outbound IP prefix, encrypt in transit. Reversible if long-term hardening is needed.

### 3. Public RDS with App-Runner-prefix security group
Pairs with #2. The exposure surface is bounded by the SG, not by the network topology. Connection is TLS. Production-grade enough for the demo; not the choice for a long-lived multi-tenant SaaS.

### 4. Custom JWT, not Cognito
Two reasons: (a) refresh token rotation + Redis blocklist is easier to express in app code than in Cognito's lifecycle hooks; (b) the IAM story stays simple — App Runner role gets S3 + Secrets Manager + CloudWatch, nothing else. Cognito would add User Pools, Identity Pools, and three more IAM scopes for a feature we control well in 200 lines of Python.

### 5. Three-stage JSON parse fallback
Live demos cannot surface model-misbehavior errors. Stage 1 uses OpenAI structured outputs (`response_format: json_schema, strict: true`). Stage 2 retries with a corrective system message. Stage 3 stores the raw output as `rendered_text`, sets `result_parse_status = failed`, and shows a small non-blocking banner. The user always gets usable content; Sentry sees the warning.

### 6. Non-streaming content generation, staged loading UI
Structured JSON output doesn't stream cleanly. A partial JSON parse is broken UX. We use a non-streaming endpoint with a UI that cycles "Analyzing topic..." → "Drafting..." → "Polishing..." across the 3–8s latency. The improver also stays non-streaming — optional complexity is a future bug.

## AWS cost estimate (7-day live window)

_(filled in during P12.2)_

| Service | Estimate |
|---|---|
| App Runner (0.25 vCPU / 0.5 GB, min 1) | — |
| RDS `db.t4g.micro` + 20 GB gp3 | — |
| ElastiCache Serverless Redis | — |
| S3 + CloudFront (low traffic, small images) | — |
| Amplify Hosting (light SSR traffic) | — |
| Secrets Manager (3 secrets) | — |
| CloudWatch Logs (30-day retention) | — |
| **OpenAI (separate budget)** | ~$8 covers full dev + demo |
| **Total AWS / 7 days** | _TBD_ |

## What I'd build next

_(filled in during P12.2 alongside the cost table)_
