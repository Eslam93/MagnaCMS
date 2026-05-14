# Infra — AWS CDK (TypeScript)

Infrastructure-as-code for the entire stack. Five CDK stacks:

| Stack | Owns |
|---|---|
| `NetworkStack` | VPC, subnets, security groups |
| `DataStack` | RDS Postgres, ElastiCache Serverless Redis, S3 image bucket, Secrets Manager entries |
| `ComputeStack` | ECR repo, App Runner service, IAM role (S3 + Secrets Manager + CloudWatch) |
| `EdgeStack` | Amplify Hosting app, CloudFront for images, ACM cert + Route53 (optional) |
| `ObservabilityStack` | CloudWatch log groups + retention |

See the top-level [`README.md`](../README.md) for the stack overview and [`ARCHITECTURE.md`](../ARCHITECTURE.md) for the load-bearing decisions (including why App Runner runs without a VPC connector).

## Single-command deploy / teardown

```bash
cd infra && npm install
npx cdk deploy --all     # provision everything
npx cdk destroy --all    # tear it all down
```
