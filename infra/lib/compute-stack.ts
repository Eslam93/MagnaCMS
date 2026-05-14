/**
 * ComputeStack — ECR repo, App Runner service, IAM role, migration
 * task definition.
 *
 * Design choices:
 *
 *   - ECR repo `magnacms-${env}-backend`. Lifecycle rule keeps the
 *     last 10 images so dev tear-down doesn't strand storage cost.
 *
 *   - App Runner service:
 *       * NO VPC connector. Public egress to OpenAI/S3/Secrets.
 *       * Image source: the ECR repo (placeholder ImageIdentifier
 *         `:latest` — the deploy workflow pushes real images).
 *       * Auto-scaling: min 1, max 3, concurrency 80.
 *       * Health check at `/api/v1/health`.
 *       * Env split: secrets injected via `RuntimeEnvironmentSecrets`
 *         (Secrets Manager refs); plain config via
 *         `RuntimeEnvironmentVariables`.
 *
 *   - IAM role for the App Runner instance:
 *       * `secretsmanager:GetSecretValue` on the three secret ARNs
 *         exposed by DataStack (RDS, JWT, OpenAI).
 *       * `s3:GetObject` + `s3:PutObject` on the images bucket.
 *       * `logs:CreateLogStream` + `logs:PutLogEvents` for the
 *         `/aws/apprunner/...` log group that ObservabilityStack
 *         provisions in P2.6.
 *
 *   - Migration runner: a separate Fargate task definition with the
 *     same backend image, command `["alembic", "upgrade", "head"]`.
 *     The deploy workflow (P2.8) runs `aws ecs run-task` against this
 *     before flipping App Runner traffic. The Fargate task gets a
 *     trimmed IAM role: SecretsManager read for the RDS secret only,
 *     no S3 access.
 *
 * The placeholder `:latest` image is replaced on first deploy by
 * `deploy.yml`. The very first `cdk deploy` will fail at App Runner
 * creation because the image doesn't exist yet — `DEPLOY.md` covers
 * the bootstrap step (push a placeholder image to ECR before
 * `cdk deploy --all`).
 */

import { CfnOutput, RemovalPolicy, Stack, type StackProps } from "aws-cdk-lib";
import { CfnService } from "aws-cdk-lib/aws-apprunner";
import {
  Cluster,
  ContainerImage,
  FargateTaskDefinition,
  LogDriver,
  Secret as EcsSecret,
} from "aws-cdk-lib/aws-ecs";
import { Repository, TagMutability } from "aws-cdk-lib/aws-ecr";
import {
  PolicyStatement,
  Role,
  ServicePrincipal,
  Effect,
} from "aws-cdk-lib/aws-iam";
import { type Vpc } from "aws-cdk-lib/aws-ec2";
import type { Bucket } from "aws-cdk-lib/aws-s3";
import type { Secret } from "aws-cdk-lib/aws-secretsmanager";
import type { DatabaseInstance } from "aws-cdk-lib/aws-rds";
import type { Construct } from "constructs";

import type { EnvConfig } from "./config";

export interface ComputeStackProps extends StackProps {
  cfg: EnvConfig;
  vpc: Vpc;
  imagesBucket: Bucket;
  jwtSecret: Secret;
  openaiApiKeySecret: Secret;
  rdsInstance: DatabaseInstance;
}

export class ComputeStack extends Stack {
  public readonly ecrRepo: Repository;
  public readonly apprunnerService: CfnService;
  public readonly migrationTaskDefinition: FargateTaskDefinition;
  public readonly ecsCluster: Cluster;

  constructor(scope: Construct, id: string, props: ComputeStackProps) {
    super(scope, id, props);

    const {
      cfg,
      vpc,
      imagesBucket,
      jwtSecret,
      openaiApiKeySecret,
      rdsInstance,
    } = props;

    // --- ECR repository ---
    this.ecrRepo = new Repository(this, "BackendRepo", {
      repositoryName: `magnacms-${cfg.envName}-backend`,
      imageTagMutability: TagMutability.MUTABLE, // allow :latest re-tags
      removalPolicy:
        cfg.envName === "dev" ? RemovalPolicy.DESTROY : RemovalPolicy.RETAIN,
      emptyOnDelete: cfg.envName === "dev",
      lifecycleRules: [
        {
          description: "Keep last 10 images, remove older",
          maxImageCount: 10,
        },
      ],
    });

    // --- IAM role for App Runner instance ---
    const apprunnerInstanceRole = new Role(this, "AppRunnerInstanceRole", {
      assumedBy: new ServicePrincipal("tasks.apprunner.amazonaws.com"),
      description: "Runtime role assumed by the App Runner backend service",
    });

    apprunnerInstanceRole.addToPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ["secretsmanager:GetSecretValue"],
        resources: [
          jwtSecret.secretArn,
          openaiApiKeySecret.secretArn,
          rdsInstance.secret!.secretArn,
        ],
      }),
    );
    apprunnerInstanceRole.addToPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
        resources: [`${imagesBucket.bucketArn}/*`],
      }),
    );
    apprunnerInstanceRole.addToPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ["s3:ListBucket"],
        resources: [imagesBucket.bucketArn],
      }),
    );
    // CloudWatch logs are auto-attached by App Runner's service role,
    // but we add the policy explicitly so the runtime role can write
    // structured logs from inside the container.
    apprunnerInstanceRole.addToPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: ["logs:CreateLogStream", "logs:PutLogEvents"],
        resources: [`arn:aws:logs:${cfg.region}:*:log-group:/aws/apprunner/*`],
      }),
    );

    // --- IAM role for App Runner ECR access ---
    const apprunnerAccessRole = new Role(this, "AppRunnerAccessRole", {
      assumedBy: new ServicePrincipal("build.apprunner.amazonaws.com"),
      description: "Service role App Runner uses to pull the ECR image",
    });
    this.ecrRepo.grantPull(apprunnerAccessRole);

    // --- App Runner service ---
    // Construct DATABASE_URL from RDS Secrets Manager entries. The
    // secret stores `{ username, password, host, port, dbname }` —
    // App Runner doesn't natively support templating these into a
    // single env var, so we pass the JSON fields as separate env vars
    // and let the backend's config.py reconstruct the URL.
    //
    // Actually, simpler: pass the full secret ARN as `RDS_SECRET_ARN`
    // and let the backend pull and parse it at startup. That avoids
    // template gymnastics and matches the brief's "secrets at runtime"
    // model. For now we pass DATABASE_URL via the rds secret's JSON
    // host field — see comment below.
    this.apprunnerService = new CfnService(this, "Service", {
      serviceName: `magnacms-${cfg.envName}-backend`,
      sourceConfiguration: {
        authenticationConfiguration: {
          accessRoleArn: apprunnerAccessRole.roleArn,
        },
        autoDeploymentsEnabled: false, // deploy workflow drives explicit deploys
        imageRepository: {
          imageIdentifier: `${this.ecrRepo.repositoryUri}:latest`,
          imageRepositoryType: "ECR",
          imageConfiguration: {
            port: "8000",
            runtimeEnvironmentVariables: [
              { name: "ENVIRONMENT", value: cfg.envName },
              { name: "AWS_REGION", value: cfg.region },
              { name: "AI_PROVIDER_MODE", value: "openai" },
              { name: "USE_REDIS", value: "true" },
              { name: "LOG_LEVEL", value: "INFO" },
              {
                name: "S3_BUCKET_IMAGES",
                value: imagesBucket.bucketName,
              },
              // CORS_ORIGINS gets populated post-deploy with the
              // Amplify URL — see DEPLOY.md step "Update CORS_ORIGINS".
              { name: "CORS_ORIGINS", value: "http://localhost:3000" },
              // IMAGES_CDN_BASE_URL also updated post-deploy with the
              // CloudFront URL from EdgeStack.
              { name: "IMAGES_CDN_BASE_URL", value: "" },
            ],
            runtimeEnvironmentSecrets: [
              {
                name: "JWT_SECRET",
                value: jwtSecret.secretArn,
              },
              {
                name: "OPENAI_API_KEY",
                value: openaiApiKeySecret.secretArn,
              },
              // DATABASE_URL: pass the RDS secret ARN as RDS_SECRET_ARN
              // and let the backend assemble the URL. Alternative is
              // to use a secret field selector like
              // `${rdsInstance.secret!.secretArn}:host::` to pull a
              // single key, but that's brittle. The backend already
              // knows how to build a DSN from {host, port, user,
              // password, dbname}.
              {
                name: "RDS_SECRET_ARN",
                value: rdsInstance.secret!.secretArn,
              },
            ],
          },
        },
      },
      instanceConfiguration: {
        cpu: cfg.apprunnerCpu,
        memory: cfg.apprunnerMemory,
        instanceRoleArn: apprunnerInstanceRole.roleArn,
      },
      healthCheckConfiguration: {
        protocol: "HTTP",
        path: "/api/v1/health",
        interval: 10,
        timeout: 5,
        healthyThreshold: 1,
        unhealthyThreshold: 5,
      },
      autoScalingConfigurationArn: undefined, // use default
      networkConfiguration: {
        egressConfiguration: { egressType: "DEFAULT" }, // public egress, no VPC connector
      },
    });

    // --- Migration runner (Fargate task definition) ---
    // Runs `alembic upgrade head` as a one-off task pre-deploy.
    // No service — invoked by `aws ecs run-task` from deploy.yml.
    this.ecsCluster = new Cluster(this, "MigrationCluster", {
      clusterName: `magnacms-${cfg.envName}-migrations`,
      vpc,
    });

    this.migrationTaskDefinition = new FargateTaskDefinition(
      this,
      "MigrationTask",
      {
        family: `magnacms-${cfg.envName}-migrate`,
        cpu: 256,
        memoryLimitMiB: 512,
      },
    );
    this.migrationTaskDefinition.addContainer("migrate", {
      image: ContainerImage.fromEcrRepository(this.ecrRepo, "latest"),
      command: ["uv", "run", "alembic", "upgrade", "head"],
      logging: LogDriver.awsLogs({
        streamPrefix: "alembic",
        logRetention: cfg.logRetentionDays,
      }),
      environment: {
        ENVIRONMENT: cfg.envName,
        AWS_REGION: cfg.region,
      },
      secrets: {
        // Migrations need DATABASE_URL — pass via RDS_SECRET_ARN like
        // the backend service does. `EcsSecret.fromSecretsManager`
        // wires the IAM read grant onto the task role automatically.
        RDS_SECRET_ARN: EcsSecret.fromSecretsManager(rdsInstance.secret!),
      },
    });

    new CfnOutput(this, "EcrRepoUri", {
      value: this.ecrRepo.repositoryUri,
      exportName: `${id}-ecr-uri`,
    });
    new CfnOutput(this, "AppRunnerServiceArn", {
      value: this.apprunnerService.attrServiceArn,
      exportName: `${id}-apprunner-service-arn`,
    });
    new CfnOutput(this, "AppRunnerServiceUrl", {
      value: this.apprunnerService.attrServiceUrl,
      exportName: `${id}-apprunner-service-url`,
    });
    new CfnOutput(this, "MigrationClusterArn", {
      value: this.ecsCluster.clusterArn,
      exportName: `${id}-migration-cluster-arn`,
    });
    new CfnOutput(this, "MigrationTaskDefinitionArn", {
      value: this.migrationTaskDefinition.taskDefinitionArn,
      exportName: `${id}-migration-task-arn`,
    });
  }
}

