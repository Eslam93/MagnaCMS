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
    // DATABASE_URL is assembled at backend startup from the RDS secret.
    //
    // Two patterns App Runner supports for getting secrets into a
    // container, and they behave differently:
    //
    //   * RuntimeEnvironmentSecrets: the env var receives the secret
    //     VALUE (the JSON blob for an RDS-managed secret). Right for
    //     bare-string secrets like JWT_SECRET and OPENAI_API_KEY where
    //     the backend reads `os.environ[...]` directly.
    //   * RuntimeEnvironmentVariables: plain string. The backend then
    //     calls `boto3.get_secret_value(SecretId=arn)` itself, using
    //     the IAM grant on the instance role.
    //
    // For DATABASE_URL we want the second pattern: the env var holds
    // the ARN, and `app/core/aws_secrets.py` fetches + parses the JSON.
    // Injecting the JSON value as `RDS_SECRET_ARN` would feed JSON into
    // `boto3.get_secret_value(SecretId=...)` and fail at startup.
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
              // USE_REDIS=false: ElastiCache lives in the VPC, App
              // Runner here has no VPC connector, so Redis is
              // unreachable. The backend has an in-memory fallback
              // path; lights up once the VPC connector arrives (P11.x).
              { name: "USE_REDIS", value: "false" },
              { name: "LOG_LEVEL", value: "INFO" },
              // Cross-domain (*.amplifyapp.com → *.awsapprunner.com)
              // requires SameSite=None on refresh cookies. Custom
              // domains can flip this back to lax. P4.x will add
              // Origin-header CSRF defense.
              { name: "COOKIE_SAMESITE", value: "none" },
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
              // RDS_SECRET_ARN must be a plain env var, NOT a secret
              // ref — the backend treats it as an ARN and looks up the
              // JSON itself via boto3 (see app/core/aws_secrets.py).
              // Injecting via runtimeEnvironmentSecrets would put the
              // JSON value into the env var and break the SecretId
              // call at startup. The instance role's GetSecretValue
              // grant on the RDS secret ARN (below) is what actually
              // authorizes the fetch.
              {
                name: "RDS_SECRET_ARN",
                value: rdsInstance.secret!.secretArn,
              },
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
      // The runtime image ships /opt/venv/bin on PATH but not `uv`
      // itself (uv is in the builder stage only). Call alembic
      // directly out of the venv.
      command: ["alembic", "upgrade", "head"],
      logging: LogDriver.awsLogs({
        streamPrefix: "alembic",
        logRetention: cfg.logRetentionDays,
      }),
      environment: {
        ENVIRONMENT: cfg.envName,
        AWS_REGION: cfg.region,
        // Plain env var (not a `secrets:` ref): the backend treats this
        // as an ARN and fetches the JSON via boto3 inside the task,
        // matching the App Runner wiring above. `secrets.fromSecretsManager`
        // would inject the JSON value here and break the SecretId lookup.
        RDS_SECRET_ARN: rdsInstance.secret!.secretArn,
      },
    });

    // The migration task role needs GetSecretValue on the RDS secret
    // so the in-container boto3 call can resolve `RDS_SECRET_ARN`.
    // (When we used `EcsSecret.fromSecretsManager`, CDK added this
    // grant automatically. Dropping that ref means adding it by hand.)
    rdsInstance.secret!.grantRead(this.migrationTaskDefinition.taskRole);

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

