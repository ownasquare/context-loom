import { mount } from "cypress/react";
import { AppProviders } from "../../src/app/AppProviders";
import { UsageEntry } from "../../src/features/usage/UsageEntry";
import { formatUsageTargetLabel } from "../../src/pages/ThreadsPage";
import type { TurnSummary } from "../../src/api/types";

describe("UsageEntry", () => {
  it("records observed usage without inventing unknown values", () => {
    cy.intercept("GET", "/api/v1/workspaces", []);
    cy.intercept("POST", "/api/v1/threads/thread-1/usage", (request) => {
      expect(request.body.thread_id).to.equal("thread-1");
      expect(request.body.hydration_id).to.equal("hydration-1");
      expect(request.body.provider).to.equal("OpenAI");
      expect(request.body.model).to.equal("gpt-5");
      expect(request.body.actual_input_tokens).to.equal(1200);
      expect(request.body.actual_output_tokens).to.equal(null);
      expect(request.body.verified_baseline_input_tokens).to.equal(null);
      request.reply({
        thread_id: "thread-1",
        turns: 1,
        estimated_baseline_input_tokens: 2400,
        estimated_hydrated_input_tokens: 1000,
        projected_input_tokens_saved: 1400,
        actual_input_tokens: 1200,
        actual_output_tokens: null,
        cached_input_tokens: null,
        local_compactor_tokens: 0,
        baseline_estimate_adjusted_reduction: null,
        verified_counterfactual_tokens_saved: null,
        actual_usage_completeness: 1,
      });
    }).as("recordUsage");

    mount(<AppProviders><UsageEntry threadId="thread-1" usageTargets={[{ hydrationId: "hydration-1", label: "Most recent prepared message" }]} workspaceId="workspace-1" /></AppProviders>);
    cy.get('select[aria-label="Prepared message"]').should("have.value", "hydration-1");
    cy.get('input[aria-label="Provider"]').type("OpenAI");
    cy.get('input[aria-label="Model"]').type("gpt-5");
    cy.get('input[aria-label="Input tokens"]').type("1200");
    cy.contains("button", "Save usage").click();
    cy.wait("@recordUsage");
    cy.contains("Usage saved").should("be.visible");
  });

  it("gives otherwise-identical prepared messages distinct stable labels", () => {
    const baseTurn: TurnSummary = {
      hydration_id: "hydration-aaaaaaaa-111111",
      created_at: "2026-07-19T12:00:00.000Z",
      adapter: "codex",
      effective_mode: "hybrid_safe",
      projected_input_tokens_saved: 1_400,
      usage_recorded: false,
      actual_input_tokens: null,
      verified_counterfactual_tokens_saved: null,
      fidelity_status: "passed",
    };
    const first = formatUsageTargetLabel(baseTurn);
    const second = formatUsageTargetLabel({
      ...baseTurn,
      hydration_id: "hydration-bbbbbbbb-222222",
    });

    expect(first).to.contain("ID hydratio…111111");
    expect(second).to.contain("ID hydratio…222222");
    expect(first).not.to.equal(second);
  });
});
