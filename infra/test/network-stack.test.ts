/**
 * NetworkStack snapshot + resource-count tests.
 *
 * Snapshot covers regression on the synthesized CloudFormation —
 * any unexpected resource churn shows up as a diff. Resource counts
 * pin the brief's stated topology: 1 VPC, 2 AZs (so 2 public subnets),
 * 2 SGs (RDS + Redis), 0 NAT gateways.
 */

import { App } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";

import { loadConfig } from "../lib/config";
import { NetworkStack } from "../lib/network-stack";

describe("NetworkStack (dev)", () => {
  const cfg = loadConfig("dev");
  const app = new App();
  const stack = new NetworkStack(app, "test-network", {
    env: { region: cfg.region },
    cfg,
  });
  const template = Template.fromStack(stack);

  it("matches snapshot", () => {
    expect(template.toJSON()).toMatchSnapshot();
  });

  it("provisions exactly one VPC", () => {
    template.resourceCountIs("AWS::EC2::VPC", 1);
  });

  it("provisions two public subnets (one per AZ, maxAzs=2)", () => {
    template.resourceCountIs("AWS::EC2::Subnet", 2);
  });

  it("provisions zero NAT gateways (App Runner is outside the VPC)", () => {
    template.resourceCountIs("AWS::EC2::NatGateway", 0);
  });

  it("provisions two security groups (RDS + Redis)", () => {
    template.resourceCountIs("AWS::EC2::SecurityGroup", 2);
  });

  // CDK renders ingress rules added via `addIngressRule` as separate
  // `AWS::EC2::SecurityGroupIngress` resources rather than inline
  // SecurityGroupIngress properties — that lets it amend SGs in
  // downstream stacks without rewriting the parent. Assertions match.

  it("RDS SG ingress includes Postgres port + App Runner prefix list", () => {
    template.hasResourceProperties("AWS::EC2::SecurityGroupIngress", {
      IpProtocol: "tcp",
      FromPort: 5432,
      ToPort: 5432,
      SourcePrefixListId: "pl-0fb53b9774434e7e1", // us-east-1 App Runner
    });
  });

  it("Redis SG ingress includes Redis port + App Runner prefix list", () => {
    template.hasResourceProperties("AWS::EC2::SecurityGroupIngress", {
      IpProtocol: "tcp",
      FromPort: 6379,
      ToPort: 6379,
      SourcePrefixListId: "pl-0fb53b9774434e7e1",
    });
  });
});
