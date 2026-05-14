# Architecture decisions

One-page summary of the load-bearing choices and the trade-offs behind them.

## Stack snapshot

| Concern | Choice | Alternatives rejected |
|---|---|---|
| Text generation | OpenAI `gpt-5.4-mini-2026-03-17` | AWS Bedrock Claude Sonnet 4.5 (Anthropic use-case form is a multi-hour gate); Anthropic direct (no image gen, would need a second provider) |
| Image generation | OpenAI `gpt-image-1` | AWS Bedrock Nova Canvas (`LEGACY`, EOL 2026-09-30); Replicate / fal.ai (additional account, additional billing surface) |
| Backend host | AWS App Runner (no VPC connector) | Fargate (more CDK wiring); Lambda (cold start + 15-min cap); Vercel (mismatched runtime for async Python + SQLAlchemy 2.0) |
| Frontend host | AWS Amplify Hosting | Vercel (great DX but adds a second cloud and a separate DNS story); App Runner static (no Next.js SSR/middleware) |
| Database | RDS Postgres `db.t4g.micro`, public subnet, strict SG | RDS in private subnet (requires VPC connector + complications); Aurora (overkill at this scale); Supabase (third cloud) |
| Auth | Custom JWT + httpOnly refresh cookie + rotation | Cognito (more moving parts, less control over rotation lifecycle); Auth0 (cost + vendor lock-in) |
| Streaming | Non-streaming for content generation | SSE everywhere (structured JSON does not stream cleanly; a partial parse is broken UX) |

## Load-bearing decisions

### 1. OpenAI direct over AWS Bedrock
Bedrock's Claude Sonnet 4.5 requires submitting an Anthropic use-case form per AWS account, and the bare model ID does not support `ON_DEMAND` inference (you must use the `us.` cross-region inference profile). Nova Canvas is `LEGACY` with EOL **2026-09-30**. OpenAI bypasses both: one prepaid key covers text + image, smoke calls verify in seconds. Provider abstractions in `app/providers/llm` and `app/providers/image` keep Bedrock as a one-class swap if requirements ever change.

### 2. No VPC connector on App Runner
With a VPC connector, App Runner loses public internet egress unless we add NAT Gateway (~$32/mo) or VPC endpoints for every AWS service we call (S3, Secrets Manager) plus the public OpenAI API. The cleaner trade is to keep App Runner public, lock RDS down with a strict SG keyed to App Runner's outbound IP prefix, and rely on TLS everywhere. Reversible if long-term hardening requirements emerge.

### 3. Public RDS with App-Runner-prefix security group
Pairs with #2. The exposure surface is bounded by the SG, not by the network topology. Connection is TLS. Production-grade for the current scope; the call would be different for a long-lived multi-tenant SaaS handling regulated data.

### 4. Custom JWT, not Cognito
Two reasons: (a) refresh-token rotation + Redis blocklist is easier to express in app code than in Cognito's lifecycle hooks; (b) the IAM story stays simple — App Runner role gets S3 + Secrets Manager + CloudWatch, nothing else. Cognito would add User Pools, Identity Pools, and three more IAM scopes for a feature we control well in ~200 lines of Python.

### 5. Three-stage JSON parse fallback
Live demos must never surface model-misbehavior errors. Stage 1 uses OpenAI structured outputs (`response_format: json_schema, strict: true`). Stage 2 retries with a corrective system message. Stage 3 stores the raw output as `rendered_text`, sets `result_parse_status = failed`, and shows a small non-blocking banner. The user always gets usable content; structured logs flag the warning for follow-up.

### 6. Non-streaming content generation, staged loading UI
Structured JSON output doesn't stream cleanly. A partial JSON parse is broken UX. The endpoint stays non-streaming; the UI cycles "Analyzing topic..." → "Drafting..." → "Polishing..." across the 3–8s latency. The improver also stays non-streaming — every line of optional complexity is a future bug.

## AWS cost estimate

_Filled in once the infrastructure lands and we have a few days of real traffic data to anchor on._

| Service | Estimate (per week) |
|---|---|
| App Runner (0.25 vCPU / 0.5 GB, min 1) | — |
| RDS `db.t4g.micro` + 20 GB gp3 | — |
| ElastiCache Serverless Redis | — |
| S3 + CloudFront (low traffic) | — |
| Amplify Hosting | — |
| Secrets Manager (3 secrets) | — |
| CloudWatch Logs (30-day retention) | — |
| **OpenAI (separate budget)** | ~$3–8 per active week |
| **Total AWS** | _TBD_ |

## What's next

_Filled in once the core flows are shipping. Priority extras under consideration: password reset, A/B prompt testing, content calendar, Nova Image v2 migration plan (Nova Canvas EOL 2026-09-30)._
