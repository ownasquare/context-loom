import { summarizeThreads } from "../../src/pages/OverviewPage";
import type { ThreadSummary } from "../../src/api/types";

function threadSummary(
  threadId: string,
  turns: number,
  completeness: number,
): ThreadSummary {
  return {
    thread_id: threadId,
    label: threadId,
    turns,
    updated_at: "2026-07-19T12:00:00.000Z",
    estimated_baseline_input_tokens: 1_000,
    estimated_hydrated_input_tokens: 400,
    projected_input_tokens_saved: 600,
    actual_input_tokens: completeness > 0 ? 400 : null,
    actual_output_tokens: null,
    cached_input_tokens: null,
    local_compactor_tokens: 20,
    baseline_estimate_adjusted_reduction: null,
    verified_counterfactual_tokens_saved: null,
    actual_usage_completeness: completeness,
    history: [],
  };
}

describe("overview token aggregation", () => {
  it("weights provider usage completeness by prepared-message count", () => {
    const totals = summarizeThreads([
      threadSummary("one-observed-message", 1, 1),
      threadSummary("one-hundred-unobserved-messages", 100, 0),
    ]);

    expect(totals.completeness).to.equal(1 / 101);
    expect(totals.projected).to.equal(1_200);
    expect(totals.observed).to.equal(400);
  });
});
