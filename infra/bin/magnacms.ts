#!/usr/bin/env node
/**
 * CDK app entry for MagnaCMS infrastructure.
 *
 * Reads `--context env=dev` (or staging/prod once wired) and constructs
 * the five stacks (Network → Data → Compute → Edge → Observability) in
 * dependency order. Each stack is named `magnacms-${env}-${stack}` so
 * multiple environments can coexist in one AWS account if needed.
 *
 * # Required context for non-local deploys
 *
 * The backend's `Settings` validator rejects `CORS_ORIGINS` containing
 * `localhost` or `127.0.0.1` in any non-local environment, and an
 * empty `IMAGES_CDN_BASE_URL` makes generated images render as
 * relative paths that 404 from the Amplify origin. Both must be
 * passed explicitly:
 *
 *   npx cdk deploy --all \
 *     -c env=dev \
 *     -c cors_origins=https://main.dew27gk9z09jh.amplifyapp.com \
 *     -c images_cdn_base_url=https://grsv8u4uit.us-east-1.awsapprunner.com/local-images
 *
 * `cors_origins` accepts a CSV string and lands on App Runner's
 * `CORS_ORIGINS` env var verbatim. `images_cdn_base_url` is the
 * scheme + host + path prefix the frontend will use for `<img src>`
 * tags; today that's the App Runner URL + `/local-images` until the
 * S3 + CloudFront adapter ships.
 *
 * Synth aborts if either is missing for a non-local env unless the
 * escape hatch `-c allow_synthetic_endpoints=true` is set — that
 * mode emits clearly-synthetic placeholders so a bootstrap deploy
 * can run before the real Amplify URL is known. The placeholders
 * pass the Settings validator but produce a loud user-visible
 * failure on the first request, which is the point: deploy-time
 * crashes are easy to diagnose; runtime "everything is broken
 * silently" is not.
 */

import "source-map-support/register";
import * as cdk from "aws-cdk-lib";

import { ComputeStack } from "../lib/compute-stack";
import { loadConfig } from "../lib/config";
import { DataStack } from "../lib/data-stack";
import { EdgeStack } from "../lib/edge-stack";
import { NetworkStack } from "../lib/network-stack";
import { ObservabilityStack } from "../lib/observability-stack";

const app = new cdk.App();
const envName = app.node.tryGetContext("env") ?? "dev";
const cfg = loadConfig(envName);

const awsEnv: cdk.Environment = {
  account: cfg.account,
  region: cfg.region,
};

// Tag every resource with the env so it's easy to grep AWS console.
cdk.Tags.of(app).add("project", "magnacms");
cdk.Tags.of(app).add("environment", cfg.envName);
cdk.Tags.of(app).add("managed-by", "cdk");

// --- Resolve required context for non-local envs ---
const allowSynthetic =
  app.node.tryGetContext("allow_synthetic_endpoints") === "true" ||
  app.node.tryGetContext("allow_synthetic_endpoints") === true;

function requireContext(key: string, syntheticDefault: string): string {
  const supplied = app.node.tryGetContext(key);
  if (typeof supplied === "string" && supplied.length > 0) {
    return supplied;
  }
  if (allowSynthetic) {
    return syntheticDefault;
  }
  throw new Error(
    `[CDK] Missing required context '${key}'. ` +
      `Pass '-c ${key}=...' on cdk synth/deploy, ` +
      `or set '-c allow_synthetic_endpoints=true' to deploy with a ` +
      `clearly-synthetic placeholder (intended for first-bootstrap only).`,
  );
}

const corsOrigins = requireContext(
  "cors_origins",
  "https://magnacms-bootstrap.invalid",
);
const imagesCdnBaseUrl = requireContext(
  "images_cdn_base_url",
  "https://magnacms-bootstrap.invalid/local-images",
);

const network = new NetworkStack(app, `magnacms-${envName}-network`, {
  env: awsEnv,
  cfg,
});

const data = new DataStack(app, `magnacms-${envName}-data`, {
  env: awsEnv,
  cfg,
  vpc: network.vpc,
  sgRds: network.sgRds,
  // sgRedis kept on NetworkStack but unused by DataStack today — the
  // ElastiCache cluster was removed pending Phase 11 + a VPC connector.
});

const compute = new ComputeStack(app, `magnacms-${envName}-compute`, {
  env: awsEnv,
  cfg,
  vpc: network.vpc,
  imagesBucket: data.imagesBucket,
  jwtSecret: data.jwtSecret,
  openaiApiKeySecret: data.openaiApiKeySecret,
  rdsInstance: data.rdsInstance,
  corsOrigins,
  imagesCdnBaseUrl,
});

const edge = new EdgeStack(app, `magnacms-${envName}-edge`, {
  env: awsEnv,
  cfg,
});

const observability = new ObservabilityStack(
  app,
  `magnacms-${envName}-observability`,
  {
    env: awsEnv,
    cfg,
  },
);

void compute;
void edge;
void observability;

app.synth();
