/**
 * ObservabilityStack — CloudWatch log groups + retention.
 *
 * App Runner auto-creates `/aws/apprunner/${service-name}/...` log
 * groups on first start, with no retention configured (logs accumulate
 * forever and bill accordingly). This stack pre-creates the same log
 * groups with explicit retention so App Runner finds them and writes
 * to them — and so they cost-bound.
 *
 * Dev: 14-day retention. Prod: 30 days (per brief §11). Both are
 * cfg-driven via `EnvConfig.logRetentionDays`.
 *
 * A CloudWatch alarm on App Runner 5xx rate is sketched out
 * (commented) — the brief defers full alarm setup to P11.6. When that
 * lands, the alarm definitions go here.
 */

import { CfnOutput, Stack, type StackProps } from "aws-cdk-lib";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import type { Construct } from "constructs";

import type { EnvConfig } from "./config";

export interface ObservabilityStackProps extends StackProps {
  cfg: EnvConfig;
}

/**
 * Map `cfg.logRetentionDays` (number) to the CDK `RetentionDays`
 * enum. CDK rejects arbitrary integers; only a fixed set of values
 * is valid.
 */
function retentionFromDays(days: number): RetentionDays {
  const map: Record<number, RetentionDays> = {
    1: RetentionDays.ONE_DAY,
    3: RetentionDays.THREE_DAYS,
    5: RetentionDays.FIVE_DAYS,
    7: RetentionDays.ONE_WEEK,
    14: RetentionDays.TWO_WEEKS,
    30: RetentionDays.ONE_MONTH,
    60: RetentionDays.TWO_MONTHS,
    90: RetentionDays.THREE_MONTHS,
    180: RetentionDays.SIX_MONTHS,
    365: RetentionDays.ONE_YEAR,
  };
  const value = map[days];
  if (!value) {
    throw new Error(
      `logRetentionDays=${days} is not one of CDK's supported values. ` +
        `Pick one of: ${Object.keys(map).join(", ")}.`,
    );
  }
  return value;
}

export class ObservabilityStack extends Stack {
  public readonly apprunnerServiceLogGroup: LogGroup;
  public readonly apprunnerApplicationLogGroup: LogGroup;

  constructor(scope: Construct, id: string, props: ObservabilityStackProps) {
    super(scope, id, props);

    const { cfg } = props;
    const retention = retentionFromDays(cfg.logRetentionDays);

    // App Runner emits two streams per service:
    //   - /service/   — service-level events (start, stop, deploy)
    //   - /application/ — container stdout/stderr
    this.apprunnerServiceLogGroup = new LogGroup(this, "AppRunnerServiceLogs", {
      logGroupName: `/aws/apprunner/magnacms-${cfg.envName}-backend/service`,
      retention,
    });
    this.apprunnerApplicationLogGroup = new LogGroup(
      this,
      "AppRunnerApplicationLogs",
      {
        logGroupName: `/aws/apprunner/magnacms-${cfg.envName}-backend/application`,
        retention,
      },
    );

    // CloudWatch alarm sketch (deferred to P11.6):
    //
    //   new cloudwatch.Alarm(this, "AppRunner5xxAlarm", {
    //     metric: new cloudwatch.Metric({
    //       namespace: "AWS/AppRunner",
    //       metricName: "5xxStatusResponses",
    //       dimensionsMap: { ServiceName: `magnacms-${cfg.envName}-backend` },
    //       statistic: "Sum",
    //       period: Duration.minutes(5),
    //     }),
    //     threshold: 5,
    //     evaluationPeriods: 1,
    //     comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
    //   });
    //
    // SNS topic + email subscription also lives here when P11.6 ships.

    new CfnOutput(this, "ServiceLogGroupName", {
      value: this.apprunnerServiceLogGroup.logGroupName,
      exportName: `${id}-service-log-group`,
    });
    new CfnOutput(this, "ApplicationLogGroupName", {
      value: this.apprunnerApplicationLogGroup.logGroupName,
      exportName: `${id}-application-log-group`,
    });
  }
}
