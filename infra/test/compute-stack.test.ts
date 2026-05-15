/**
 * ComputeStack snapshot + resource-count tests.
 *
 * Pins: 1 ECR repo, 1 App Runner service, 1 ECS cluster (for
 * migrations), 1 Fargate task definition, 2 IAM roles (instance +
 * ECR-access), plus the App Runner-required wiring.
 */

import { App } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";

import { ComputeStack } from "../lib/compute-stack";
import { loadConfig } from "../lib/config";
import { DataStack } from "../lib/data-stack";
import { NetworkStack } from "../lib/network-stack";

describe("ComputeStack (dev)", () => {
  const cfg = loadConfig("dev");
  const app = new App();
  const network = new NetworkStack(app, "test-network", {
    env: { region: cfg.region },
    cfg,
  });
  const data = new DataStack(app, "test-data", {
    env: { region: cfg.region },
    cfg,
    vpc: network.vpc,
    sgRds: network.sgRds,
  });
  const stack = new ComputeStack(app, "test-compute", {
    env: { region: cfg.region },
    cfg,
    vpc: network.vpc,
    imagesBucket: data.imagesBucket,
    jwtSecret: data.jwtSecret,
    openaiApiKeySecret: data.openaiApiKeySecret,
    rdsInstance: data.rdsInstance,
  });
  const template = Template.fromStack(stack);

  it("matches snapshot", () => {
    expect(template.toJSON()).toMatchSnapshot();
  });

  it("provisions one ECR repository", () => {
    template.resourceCountIs("AWS::ECR::Repository", 1);
    template.hasResourceProperties("AWS::ECR::Repository", {
      RepositoryName: "magnacms-dev-backend",
    });
  });

  it("provisions one App Runner service with health check on /api/v1/health", () => {
    template.resourceCountIs("AWS::AppRunner::Service", 1);
    template.hasResourceProperties("AWS::AppRunner::Service", {
      ServiceName: "magnacms-dev-backend",
      HealthCheckConfiguration: {
        Protocol: "HTTP",
        Path: "/api/v1/health",
      },
    });
  });

  it("App Runner has no VPC connector (public egress)", () => {
    template.hasResourceProperties("AWS::AppRunner::Service", {
      NetworkConfiguration: {
        EgressConfiguration: { EgressType: "DEFAULT" },
      },
    });
  });

  it("App Runner runtime secrets inject JWT + OpenAI secret VALUES (bare strings)", () => {
    template.hasResourceProperties("AWS::AppRunner::Service", {
      SourceConfiguration: {
        ImageRepository: {
          ImageConfiguration: {
            RuntimeEnvironmentSecrets: Match.arrayWith([
              Match.objectLike({ Name: "JWT_SECRET" }),
              Match.objectLike({ Name: "OPENAI_API_KEY" }),
            ]),
          },
        },
      },
    });
  });

  it("RDS_SECRET_ARN is a plain env var on App Runner (not a secret ref)", () => {
    // The backend reads RDS_SECRET_ARN as an ARN and calls boto3
    // itself. Injecting it via RuntimeEnvironmentSecrets would put the
    // RDS JSON blob into the env var and break the SecretId lookup.
    // Read the raw template so we can inspect both lists directly.
    const services = template.findResources("AWS::AppRunner::Service");
    const service = Object.values(services)[0];
    const imageConfig =
      service.Properties.SourceConfiguration.ImageRepository.ImageConfiguration;
    const envNames = (
      imageConfig.RuntimeEnvironmentVariables as { Name: string }[]
    ).map((v) => v.Name);
    const secretNames = (
      imageConfig.RuntimeEnvironmentSecrets as { Name: string }[]
    ).map((v) => v.Name);
    expect(envNames).toContain("RDS_SECRET_ARN");
    expect(secretNames).not.toContain("RDS_SECRET_ARN");
  });

  it("migration task receives RDS_SECRET_ARN as a plain env var (not a secret ref)", () => {
    const taskDefs = template.findResources("AWS::ECS::TaskDefinition");
    const taskDef = Object.values(taskDefs).find(
      (t) => t.Properties.Family === "magnacms-dev-migrate",
    );
    expect(taskDef).toBeDefined();
    const container = taskDef!.Properties.ContainerDefinitions[0];
    const envNames = (container.Environment as { Name: string }[]).map(
      (v) => v.Name,
    );
    const secretNames = ((container.Secrets ?? []) as { Name: string }[]).map(
      (v) => v.Name,
    );
    expect(envNames).toContain("RDS_SECRET_ARN");
    expect(secretNames).not.toContain("RDS_SECRET_ARN");
  });

  it("provisions an ECS cluster + Fargate task definition for migrations", () => {
    template.resourceCountIs("AWS::ECS::Cluster", 1);
    template.resourceCountIs("AWS::ECS::TaskDefinition", 1);
    template.hasResourceProperties("AWS::ECS::TaskDefinition", {
      Family: "magnacms-dev-migrate",
      Cpu: "256",
      Memory: "512",
    });
  });

  it("IAM instance role grants secretsmanager:GetSecretValue", () => {
    template.hasResourceProperties("AWS::IAM::Policy", {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: "secretsmanager:GetSecretValue",
            Effect: "Allow",
          }),
        ]),
      },
    });
  });
});
