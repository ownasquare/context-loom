import { mount } from "cypress/react";
import { AppProviders } from "../../src/app/AppProviders";
import { ResourceDetail } from "../../src/features/resources/ResourceDetail";
import type { ResourceSummary } from "../../src/api/types";

const resource: ResourceSummary = {
  resource_id: "resource-1",
  version_id: "version-1",
  relative_path: "src/example.ts",
  kind: "code",
  sha256: "a".repeat(64),
  estimated_tokens: 24,
  chunks: 2,
  status: "current",
  changed_at: "2026-07-19T12:00:00Z",
  change_type: "unchanged",
};

describe("ResourceDetail", () => {
  it("loads sanitized immutable content and keeps source text inert", () => {
    cy.intercept("GET", "/api/v1/workspaces", []);
    cy.intercept("GET", "/api/v1/resources/resource-1/versions/version-1", {
      ...resource,
      workspace_id: "workspace-1",
      content: "<script>window.__unsafe = true</script>\nexport const ready = true;",
      current: true,
      redacted_count: 2,
      created_at: resource.changed_at,
    }).as("resolveVersion");

    mount(<AppProviders><ResourceDetail onClose={cy.stub().as("close")} resource={resource} /></AppProviders>);
    cy.wait("@resolveVersion");
    cy.get("dialog[open]").should("have.attr", "aria-modal", "true");
    cy.contains("h2", "src/example.ts").should("be.visible");
    cy.contains("2 detected sensitive patterns redacted").should("be.visible");
    cy.get("pre").should("contain.text", "<script>window.__unsafe = true</script>");
    cy.window().its("__unsafe").should("be.undefined");
    cy.get('button[aria-label="Close file preview"]').click();
    cy.get("@close").should("have.been.calledOnce");
  });

  it("closes the native modal through a cancel request", () => {
    cy.intercept("GET", "/api/v1/workspaces", []);
    cy.intercept("GET", "/api/v1/resources/resource-1/versions/version-1", {
      ...resource,
      workspace_id: "workspace-1",
      content: "export const ready = true;",
      current: true,
      redacted_count: 0,
      created_at: resource.changed_at,
    });

    mount(<AppProviders><ResourceDetail onClose={cy.stub().as("cancelClose")} resource={resource} /></AppProviders>);
    cy.get("dialog[open]").trigger("cancel");
    cy.get("@cancelClose").should("have.been.calledOnce");
    cy.get("dialog").should("not.have.attr", "open");
  });

  it("closes the native modal through a backdrop click", () => {
    cy.intercept("GET", "/api/v1/workspaces", []);
    cy.intercept("GET", "/api/v1/resources/resource-1/versions/version-1", {
      ...resource,
      workspace_id: "workspace-1",
      content: "export const ready = true;",
      current: true,
      redacted_count: 0,
      created_at: resource.changed_at,
    });

    mount(<AppProviders><ResourceDetail onClose={cy.stub().as("backdropClose")} resource={resource} /></AppProviders>);
    cy.get("dialog[open]").then(($dialog) => {
      ($dialog[0] as HTMLDialogElement).click();
    });
    cy.get("@backdropClose").should("have.been.calledOnce");
    cy.get("dialog").should("not.have.attr", "open");
  });
});
