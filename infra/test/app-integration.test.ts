/**
 * App-level integration test: instantiate the full app, synth it,
 * verify all five stacks are present and connected correctly.
 *
 * This is the closest thing P2.7 has to a "first deployment succeeds"
 * acceptance test under the code-only constraint — actual `cdk deploy`
 * happens manually via DEPLOY.md.
 */

import { App } from "aws-cdk-lib";

import { ComputeStack } from "../lib/compute-stack";
import { loadConfig } from "../lib/config";
import { DataStack } from "../lib/data-stack";
import { EdgeStack } from "../lib/edge-stack";
import { NetworkStack } from "../lib/network-stack";
import { ObservabilityStack } from "../lib/observability-stack";

describe("Full app synthesis (dev)", () => {
  const app = new App();
  const cfg = loadConfig("dev");
  const env = { region: cfg.region };

  const network = new NetworkStack(app, "magnacms-dev-network", { env, cfg });
  const data = new DataStack(app, "magnacms-dev-data", {
    env,
    cfg,
    vpc: network.vpc,
    sgRds: network.sgRds,
    sgRedis: network.sgRedis,
  });
  const compute = new ComputeStack(app, "magnacms-dev-compute", {
    env,
    cfg,
    vpc: network.vpc,
    imagesBucket: data.imagesBucket,
    jwtSecret: data.jwtSecret,
    openaiApiKeySecret: data.openaiApiKeySecret,
    rdsInstance: data.rdsInstance,
  });
  const edge = new EdgeStack(app, "magnacms-dev-edge", { env, cfg });
  const observability = new ObservabilityStack(
    app,
    "magnacms-dev-observability",
    { env, cfg },
  );

  const assembly = app.synth();

  it("synthesizes five stacks", () => {
    expect(assembly.stacks).toHaveLength(5);
  });

  it("stack names follow `magnacms-${env}-${component}`", () => {
    const stackNames = assembly.stacks.map((s) => s.stackName).sort();
    expect(stackNames).toEqual([
      "magnacms-dev-compute",
      "magnacms-dev-data",
      "magnacms-dev-edge",
      "magnacms-dev-network",
      "magnacms-dev-observability",
    ]);
  });

  it("compute depends on data (RDS, secrets, S3 references)", () => {
    // CDK assembly tracks cross-stack dependencies via SSM exports +
    // imports, plus each stack has an `.assets` companion artifact.
    // Filter out the `.assets` entries.
    //
    // The compute stack imports from data (RDS secret ARN, image
    // bucket ARN, JWT/OpenAI secret ARNs). The VPC reference from
    // network may or may not generate a stack-level dep depending on
    // how CDK resolves it — the important contract here is that
    // data → compute import flow works.
    const computeArtifact = assembly.getStackArtifact("magnacms-dev-compute");
    const stackDeps = computeArtifact.dependencies
      .map((d) => d.id)
      .filter((id) => !id.endsWith(".assets"));
    expect(stackDeps).toContain("magnacms-dev-data");
  });

  it("edge has no stack-level dependencies (CloudFront-for-images deferred — see P2.5)", () => {
    const edgeArtifact = assembly.getStackArtifact("magnacms-dev-edge");
    const stackDeps = edgeArtifact.dependencies
      .map((d) => d.id)
      .filter((id) => !id.endsWith(".assets"));
    expect(stackDeps).toHaveLength(0);
  });

  // Defeat "unused variable" lint
  void compute;
  void edge;
  void observability;
});
