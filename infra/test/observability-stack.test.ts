/**
 * ObservabilityStack snapshot + resource-count tests.
 *
 * Pins: 2 LogGroups (service + application), 14-day retention in dev.
 */

import { App } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";

import { loadConfig } from "../lib/config";
import { ObservabilityStack } from "../lib/observability-stack";

describe("ObservabilityStack (dev)", () => {
  const cfg = loadConfig("dev");
  const app = new App();
  const stack = new ObservabilityStack(app, "test-observability", {
    env: { region: cfg.region },
    cfg,
  });
  const template = Template.fromStack(stack);

  it("matches snapshot", () => {
    expect(template.toJSON()).toMatchSnapshot();
  });

  it("provisions exactly two log groups (service + application)", () => {
    template.resourceCountIs("AWS::Logs::LogGroup", 2);
  });

  it("dev retention is 14 days", () => {
    template.hasResourceProperties("AWS::Logs::LogGroup", {
      RetentionInDays: 14,
    });
  });

  it("log group names follow the /aws/apprunner/<service> convention", () => {
    template.hasResourceProperties("AWS::Logs::LogGroup", {
      LogGroupName: "/aws/apprunner/magnacms-dev-backend/service",
    });
    template.hasResourceProperties("AWS::Logs::LogGroup", {
      LogGroupName: "/aws/apprunner/magnacms-dev-backend/application",
    });
  });
});
