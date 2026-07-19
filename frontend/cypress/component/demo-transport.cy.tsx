import { DemoTransport } from "../../src/api/demoTransport";
import { demoWorkspace } from "../../src/api/demoData";
import type { HydrateRequest } from "../../src/api/types";

describe("DemoTransport hydration parity", () => {
  it("honors request budgets and only accounts for the helper when selected", () => {
    const transport = new DemoTransport();
    const baseRequest: HydrateRequest = {
      workspace_id: demoWorkspace.id,
      message: "Review the current project without changing its constraints.",
      thread_id: "thread-demo-budget-test",
      thread_label: "Budget test",
      adapter: "codex",
      mode: "hybrid_safe",
      max_input_tokens: 900,
      reserve_output_tokens: 200,
      use_local_model: false,
      include_debug: true,
    };

    cy.then(async () => {
      const withoutHelper = await transport.hydrate(baseRequest);
      expect(withoutHelper.envelope.token_plan.reserved_output_tokens).to.equal(200);
      expect(withoutHelper.envelope.token_plan.hydrated.tokens).to.be.at.most(700);
      expect(withoutHelper.envelope.token_plan.local_compactor_input_tokens).to.equal(0);
      expect(withoutHelper.envelope.token_plan.local_compactor_output_tokens).to.equal(0);
      expect(withoutHelper.envelope.metadata.budget).to.deep.equal({
        max_input_tokens: 900,
        reserve_output_tokens: 200,
        available_input_tokens: 700,
      });
      expect(withoutHelper.envelope.metadata.local_model_attempted).to.equal(false);
      expect(withoutHelper.envelope.metadata.local_model_used).to.equal(false);

      const withHelper = await transport.hydrate({
        ...baseRequest,
        thread_id: "thread-demo-helper-test",
        thread_label: "Helper test",
        max_input_tokens: 4_000,
        reserve_output_tokens: 500,
        use_local_model: true,
      });
      expect(withHelper.envelope.token_plan.reserved_output_tokens).to.equal(500);
      expect(withHelper.envelope.token_plan.local_compactor_input_tokens).to.be.greaterThan(0);
      expect(withHelper.envelope.token_plan.local_compactor_output_tokens).to.be.greaterThan(0);
      expect(withHelper.envelope.metadata.local_model_attempted).to.equal(true);
      expect(withHelper.envelope.metadata.local_model_used).to.equal(true);
    });
  });
});
