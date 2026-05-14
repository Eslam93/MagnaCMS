#!/usr/bin/env node
/**
 * CDK app entry for MagnaCMS infrastructure.
 *
 * Reads `--context env=dev` (or staging/prod once wired) and constructs
 * the five stacks (Network → Data → Compute → Edge → Observability) in
 * dependency order. Each stack is named `magnacms-${env}-${stack}` so
 * multiple environments can coexist in one AWS account if needed.
 *
 * Phase 2 (P2.1) ships this entry as a stub — no stacks are instantiated
 * yet. Subsequent PRs (P2.2 → P2.6) wire each stack in turn. The
 * `cdk synth --all` command in `infra-ci.yml` runs on every PR to catch
 * construct errors early.
 */

import "source-map-support/register";
import * as cdk from "aws-cdk-lib";

import { loadConfig } from "../lib/config";
import { DataStack } from "../lib/data-stack";
import { NetworkStack } from "../lib/network-stack";

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

const network = new NetworkStack(app, `magnacms-${envName}-network`, {
  env: awsEnv,
  cfg,
});

const data = new DataStack(app, `magnacms-${envName}-data`, {
  env: awsEnv,
  cfg,
  vpc: network.vpc,
  sgRds: network.sgRds,
  sgRedis: network.sgRedis,
});

// Downstream stacks (lands in subsequent PRs):
//   const compute = new ComputeStack(app, `magnacms-${envName}-compute`, { env: awsEnv, cfg, network, data });
//   const edge = new EdgeStack(app, `magnacms-${envName}-edge`, { env: awsEnv, cfg, data });
//   new ObservabilityStack(app, `magnacms-${envName}-observability`, { env: awsEnv, cfg, compute });
void data;

app.synth();
