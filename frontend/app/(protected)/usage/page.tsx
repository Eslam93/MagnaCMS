/**
 * /usage placeholder. The per-user cost rollup is deferred until the
 * `usage_events` table lands in a later phase — every generation
 * already persists `input_tokens`, `output_tokens`, and `cost_usd` on
 * its row, so the data is in the DB; the page just doesn't aggregate
 * yet.
 */
export default function UsagePage() {
  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold">Usage</h1>
        <p className="text-sm text-muted-foreground">
          Per-account cost rollup. Coming up after the demo window.
        </p>
      </header>
      <div className="rounded-lg border border-dashed bg-card p-8 text-sm text-muted-foreground">
        Token + cost data is recorded on every generation and improvement row already (see the
        dashboard). A dedicated aggregation lands here with the usage-events table in a follow-up
        slice.
      </div>
    </div>
  );
}
