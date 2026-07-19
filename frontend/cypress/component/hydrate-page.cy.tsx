import { mount } from "cypress/react";
import { AppProviders } from "../../src/app/AppProviders";
import { createDemoEnvelope, demoWorkspace } from "../../src/api/demoData";
import type { HydrateRequest, HydrationResponse } from "../../src/api/types";
import { HydratePage } from "../../src/pages/HydratePage";

describe("HydratePage request lifecycle", () => {
  it("retries the captured request and clears a result when the draft changes", () => {
    const requests: HydrateRequest[] = [];
    const exactMessage = "Review the current project.";
    const response: HydrationResponse = {
      envelope: createDemoEnvelope(exactMessage, "hybrid_safe"),
      rendered: {
        adapter: "codex",
        media_type: "text/markdown",
        payload: `Prepared: ${exactMessage}`,
        exact_message: exactMessage,
        instructions: [],
      },
    };

    cy.intercept("GET", "/api/v1/workspaces", [demoWorkspace]);
    cy.intercept("POST", "/api/v1/hydrations", (request) => {
      requests.push(request.body as HydrateRequest);
      if (requests.length === 1) {
        request.reply({
          statusCode: 503,
          body: { error: { code: "local_unavailable", message: "Local preparation failed", request_id: "request-1" } },
        });
        return;
      }
      request.reply({ statusCode: 201, body: response });
    }).as("hydrate");

    mount(<AppProviders><HydratePage /></AppProviders>);
    cy.get("#chat-message").type(exactMessage);
    cy.contains("button", "Prepare request").click();
    cy.wait("@hydrate");
    cy.contains("Could not prepare the request").should("be.visible");
    cy.contains("nothing was sent to a configured helper or chat provider").should("be.visible");

    cy.contains("button", "Try again").click();
    cy.wait("@hydrate");
    cy.get("[data-testid='rendered-payload']").should("contain.text", exactMessage);
    cy.then(() => {
      expect(requests).to.have.length(2);
      expect(requests[1]).to.deep.equal(requests[0]);
    });

    cy.get("#chat-message").type(" Updated.");
    cy.get("[data-testid='hydration-inspector']").should("not.exist");
  });

  it("does not promise zero transfer after a configured helper was attempted", () => {
    cy.intercept("GET", "/api/v1/workspaces", [demoWorkspace]);
    cy.intercept("POST", "/api/v1/hydrations", (request) => {
      expect(request.body.use_local_model).to.equal(true);
      request.reply({
        statusCode: 503,
        body: { error: { code: "helper_unavailable", message: "Helper failed", request_id: "request-helper" } },
      });
    }).as("helperHydrate");

    mount(<AppProviders><HydratePage /></AppProviders>);
    cy.get("#chat-message").type("Review the current project.");
    cy.contains("summary", "Advanced settings").click();
    cy.contains("label", "Use the optional local helper").find("input").check();
    cy.contains("button", "Prepare request").click();
    cy.wait("@helperHydrate");

    cy.contains("The configured helper may already have received selected, sanitized project context").should("be.visible");
    cy.contains("nothing was sent to an external provider").should("not.exist");
  });
});
