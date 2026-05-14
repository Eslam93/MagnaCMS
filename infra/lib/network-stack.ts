/**
 * NetworkStack — VPC, subnets, security groups.
 *
 * Design choices (per brief §11):
 *
 *   - 2 AZs, PUBLIC subnets only. No private subnets, no NAT gateways.
 *     App Runner sits outside the VPC entirely (no VPC connector) so
 *     it can reach OpenAI/S3/Secrets Manager over public egress
 *     without VPC endpoint sprawl. RDS sits in the public subnet but
 *     is locked down by SG to App Runner's egress IP prefix list
 *     plus an optional dev-IP allowlist.
 *
 *   - SG for RDS: inbound 5432 from App Runner egress prefix list
 *     (com.amazonaws.us-east-1.apprunner) + cfg.devIpAllowlist.
 *     The prefix list is a managed AWS resource — its IPs change as
 *     App Runner scales, but the list ID is stable.
 *
 *   - SG for ElastiCache: inbound 6379 from the same prefix list.
 *     Dev IP allowlist not extended here because Redis isn't
 *     externally browseable.
 *
 * Public-RDS-in-public-subnet is a deliberate trade-off. The brief
 * explains the rationale at length: keeping the network surface flat
 * removes a whole class of "I can't reach my DB" debugging that VPC
 * connectors + NAT + endpoint services would introduce. The SGs do
 * the actual access control.
 */

import { CfnOutput, Stack, type StackProps } from "aws-cdk-lib";
import {
  Peer,
  Port,
  SecurityGroup,
  SubnetType,
  Vpc,
} from "aws-cdk-lib/aws-ec2";
import type { Construct } from "constructs";

import type { EnvConfig } from "./config";

/**
 * App Runner's managed egress prefix list ID per region. AWS does not
 * publish a CDK helper for this; the ID is stable per region. Update
 * if AWS ever changes it (announced in their changelog).
 *
 * Source: https://docs.aws.amazon.com/apprunner/latest/dg/security-vpc.html
 */
const APPRUNNER_EGRESS_PREFIX_LIST_IDS: Record<string, string> = {
  "us-east-1": "pl-0fb53b9774434e7e1",
  "us-east-2": "pl-0c1f0fbbbcdcc4c43",
  "us-west-2": "pl-0a8a8a8a8a8a8a8a8",
  "eu-west-1": "pl-09beda8c47f6dd2c8",
};

function appRunnerPrefixListId(region: string): string {
  const id = APPRUNNER_EGRESS_PREFIX_LIST_IDS[region];
  if (!id) {
    throw new Error(
      `App Runner egress prefix list ID not catalogued for region ${region}. ` +
        `Add it to APPRUNNER_EGRESS_PREFIX_LIST_IDS in network-stack.ts.`,
    );
  }
  return id;
}

export interface NetworkStackProps extends StackProps {
  cfg: EnvConfig;
}

export class NetworkStack extends Stack {
  public readonly vpc: Vpc;
  public readonly sgRds: SecurityGroup;
  public readonly sgRedis: SecurityGroup;

  constructor(scope: Construct, id: string, props: NetworkStackProps) {
    super(scope, id, props);

    const { cfg } = props;

    this.vpc = new Vpc(this, "Vpc", {
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        {
          name: "public",
          subnetType: SubnetType.PUBLIC,
          cidrMask: 24,
          mapPublicIpOnLaunch: true,
        },
      ],
      // No private subnets; App Runner doesn't sit in the VPC.
    });

    const prefixListId = appRunnerPrefixListId(cfg.region);

    // --- RDS SG ---
    this.sgRds = new SecurityGroup(this, "SgRds", {
      vpc: this.vpc,
      description: "RDS Postgres: App Runner + dev IP allowlist only",
      allowAllOutbound: false,
    });
    this.sgRds.addIngressRule(
      Peer.prefixList(prefixListId),
      Port.tcp(5432),
      "PostgreSQL from App Runner egress",
    );
    for (const cidr of cfg.devIpAllowlist) {
      this.sgRds.addIngressRule(
        Peer.ipv4(cidr),
        Port.tcp(5432),
        `Dev access from ${cidr}`,
      );
    }

    // --- ElastiCache (Redis) SG ---
    this.sgRedis = new SecurityGroup(this, "SgRedis", {
      vpc: this.vpc,
      description: "ElastiCache Redis: App Runner only",
      allowAllOutbound: false,
    });
    this.sgRedis.addIngressRule(
      Peer.prefixList(prefixListId),
      Port.tcp(6379),
      "Redis from App Runner egress",
    );

    new CfnOutput(this, "VpcId", {
      value: this.vpc.vpcId,
      description: "VPC ID for downstream stacks",
      exportName: `${id}-vpc-id`,
    });
    new CfnOutput(this, "SgRdsId", {
      value: this.sgRds.securityGroupId,
      exportName: `${id}-sg-rds-id`,
    });
    new CfnOutput(this, "SgRedisId", {
      value: this.sgRedis.securityGroupId,
      exportName: `${id}-sg-redis-id`,
    });
  }
}
