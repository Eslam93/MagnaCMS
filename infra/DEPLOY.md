# Deploying MagnaCMS to AWS — manual runbook

This document walks through the first `cdk deploy` and the post-deploy bootstrap steps. After that's done once, `deploy.yml` handles every subsequent push to `main`.

## Prerequisites

- AWS account with admin credentials (`aws configure` against the target account)
- Node 20+, Docker, AWS CDK CLI (`npm i -g aws-cdk@^2.180`)
- A funded OpenAI API key (sk-proj-…)
- Optional: a registered domain if you want `app.<your-domain>` / `api.<your-domain>` URLs instead of the AWS default `*.amplifyapp.com` / `*.awsapprunner.com`

## One-time setup

### 1. CDK bootstrap

```bash
cd infra
npm ci
aws configure  # if not already
npx cdk bootstrap aws://<ACCOUNT_ID>/us-east-1
```

This provisions the CDK toolkit stack (S3 bucket for assets, IAM roles) — required once per AWS account + region combination.

### 2. Push a placeholder backend image to ECR

`cdk deploy` of the ComputeStack will fail at App Runner creation if the ECR repo is empty — App Runner needs an image to start the service. Push a placeholder:

```bash
# First, deploy just the data + compute stacks so the ECR repo exists
npx cdk deploy magnacms-dev-network magnacms-dev-data magnacms-dev-compute -c env=dev
# (Compute will fail at App Runner creation — that's OK; the ECR repo
#  is created before App Runner attempts to pull. Continue.)

# Build + push the real backend image
ECR_URI=$(aws cloudformation describe-stacks \
  --stack-name magnacms-dev-compute \
  --query "Stacks[0].Outputs[?ExportName=='magnacms-dev-compute-ecr-uri'].OutputValue" \
  --output text)
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin "$ECR_URI"
docker build -t "$ECR_URI:latest" ../backend/
docker push "$ECR_URI:latest"

# Now retry the deploy — App Runner should succeed this time
npx cdk deploy magnacms-dev-compute -c env=dev
```

### 3. Deploy remaining stacks

```bash
npx cdk deploy magnacms-dev-edge magnacms-dev-observability -c env=dev
```

### 4. Populate the OpenAI API key

DataStack creates `magnacms-dev-openai-api-key` as an empty secret. Populate it via the console or CLI:

```bash
aws secretsmanager put-secret-value \
  --secret-id magnacms-dev-openai-api-key \
  --secret-string '<your-sk-proj-key>'
```

App Runner picks up the value on next deploy. If App Runner is already RUNNING, force a redeploy:

```bash
APPRUNNER_ARN=$(aws cloudformation describe-stacks \
  --stack-name magnacms-dev-compute \
  --query "Stacks[0].Outputs[?ExportName=='magnacms-dev-compute-apprunner-service-arn'].OutputValue" \
  --output text)
aws apprunner start-deployment --service-arn "$APPRUNNER_ARN"
```

### 5. Run initial migrations

```bash
MIGRATION_CLUSTER=$(aws cloudformation describe-stacks \
  --stack-name magnacms-dev-compute \
  --query "Stacks[0].Outputs[?ExportName=='magnacms-dev-compute-migration-cluster-arn'].OutputValue" \
  --output text)
MIGRATION_TASK_DEF=$(aws cloudformation describe-stacks \
  --stack-name magnacms-dev-compute \
  --query "Stacks[0].Outputs[?ExportName=='magnacms-dev-compute-migration-task-arn'].OutputValue" \
  --output text)
SUBNETS=$(aws ec2 describe-subnets \
  --filters "Name=tag:environment,Values=dev" \
            "Name=map-public-ip-on-launch,Values=true" \
  --query 'Subnets[].SubnetId' --output text | tr '\t' ',')

aws ecs run-task \
  --cluster "$MIGRATION_CLUSTER" \
  --task-definition "$MIGRATION_TASK_DEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],assignPublicIp=ENABLED}"
```

Watch for the task to reach STOPPED with exit code 0 in the ECS console. Logs are in the `/aws/ecs/...` log group.

### 6. Smoke test `/health`

```bash
APPRUNNER_URL=$(aws cloudformation describe-stacks \
  --stack-name magnacms-dev-compute \
  --query "Stacks[0].Outputs[?ExportName=='magnacms-dev-compute-apprunner-service-url'].OutputValue" \
  --output text)
curl -fsSL "https://$APPRUNNER_URL/api/v1/health"
```

Expected: `{"status":"ok","version":"0.1.0","environment":"dev","dependencies":{...}}`.

### 7. Update CORS_ORIGINS and IMAGES_CDN_BASE_URL

The compute stack ships with placeholder values for these. After EdgeStack deploys, you'll know the Amplify domain. Update via console:

1. App Runner → `magnacms-dev-backend` → Configuration → Environment variables
2. Update `CORS_ORIGINS` to include `https://<branch>.<amplify-app-id>.amplifyapp.com`
3. Leave `IMAGES_CDN_BASE_URL` empty until CloudFront-for-images lands in Phase 5

App Runner force-redeploys on env-var change.

### 8. **PREFLIGHT: Verify rate-limit IP identity** (P1.10 follow-up — critical)

The rate limiter in `app/middleware/rate_limit.py` keys on `scope["client"]`. Verify that App Runner forwards the real client IP rather than its internal load-balancer peer:

```bash
# From a single source IP, hit /auth/login 11 times in 60s.
for i in $(seq 1 11); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST "https://$APPRUNNER_URL/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"test@example.com","password":"x"}'
done
```

Expected: ten 401s (invalid credentials), then a 429 (rate-limited) on attempt 11.

**If you get 429 immediately on attempt 1 or 2, the limiter is keying on App Runner's load-balancer peer IP, not the real client.** Every user shares one bucket — global throttling at 10 req/min. Fix before going public:

1. Add `TRUST_PROXY_XFF=true` env var to App Runner
2. Update `rate_limit.py` to read `X-Forwarded-For` when the flag is set, scoped to App Runner egress IPs as trusted proxies

(See P1.10 plan notes for the follow-up code change.)

### 9. Connect Amplify to GitHub

CDK creates the Amplify app shell but can't auto-connect to a GitHub repo without an OAuth token. From the Amplify console:

1. Amplify → `magnacms-dev` → App settings → Repository settings → Reconnect repository
2. Authorize the GitHub App for `Eslam93/MagnaCMS`
3. Confirm the `main` branch is detected and auto-deploys are enabled

First Amplify build runs against the current `main` HEAD.

### 10. Record the live URLs in README

In the project root `README.md` §1 "Live demo":

```markdown
- **Backend**: https://<apprunner-url>/api/v1/health
- **Frontend**: https://<amplify-branch>.<amplify-app-id>.amplifyapp.com
```

### 11. Flip `deploy.yml` to auto-trigger

Once the manual deploy succeeds end-to-end (above), update `.github/workflows/deploy.yml`:

```yaml
on:
  workflow_dispatch:
    inputs:
      env: ...
  push:
    branches: [main]
    paths:
      - 'backend/**'
      - '.github/workflows/deploy.yml'
```

Also add the required GitHub Secrets:

- `AWS_DEPLOY_ROLE_ARN` — OIDC role ARN from your bootstrap. Create with `aws iam create-role` + the GitHub OIDC trust policy (see [AWS docs](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)).

## Routine deploys (after first-deploy bootstrap)

Once everything is set up, every push to `main` that touches `backend/` triggers `deploy.yml` automatically. The workflow:

1. OIDC-assumes the deploy role
2. Builds + pushes the backend Docker image to ECR (`:latest` + `:<sha>`)
3. Runs migrations as a Fargate one-off task
4. Triggers App Runner deployment
5. Waits for RUNNING status
6. Smoke-tests `/health`

If any step fails, the workflow exits non-zero and notifies on the PR / commit.

## Teardown

```bash
cd infra
npx cdk destroy --all -c env=dev
# Plus: delete the Amplify app manually from the console
#       (CDK has trouble removing Amplify apps connected to GitHub)
```

## Known issues

- **App Runner first deploy without a pushed image fails.** That's expected (see step 2). Push the image, then retry.
- **`amplify.yml` not yet present.** Lands in P2.9a (frontend scaffold). Until then, the inline buildSpec in EdgeStack serves as the build config.
- **CloudFront for images is deferred to Phase 5.** EdgeStack ships Amplify only because of a circular dependency between DataStack and CloudFront-for-S3 OAC. See PR #124 for the full reasoning.
- **The `prod` environment isn't wired.** `loadConfig('prod')` throws at startup. Adding prod is a single-PR follow-up — copy the dev entry in `lib/config.ts`, tighten instance sizes/retention/devIpAllowlist, switch removalPolicy to RETAIN, set `multi-AZ: true` on RDS.
