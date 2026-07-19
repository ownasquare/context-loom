import { mount } from "cypress/react";
import type { FidelityReport } from "../../src/api/types";
import { createDemoEnvelope } from "../../src/api/demoData";
import { EvidenceList } from "../../src/features/hydration/EvidenceList";
import { FidelityPanel } from "../../src/features/hydration/FidelityPanel";
import { AppProviders } from "../../src/app/AppProviders";

const fallbackReport: FidelityReport = {
  status: "fallback",
  requested_mode: "hybrid_safe",
  effective_mode: "strict_extractive",
  exact_message_preserved: true,
  citations_valid: true,
  freshness_valid: true,
  protected_atom_coverage: 1,
  explicit_reference_coverage: 1,
  security_overrides: [],
  failures: [],
  replay_hash: "f".repeat(64),
  fallback_reason: "A generated claim lacked a current citation, so strict extraction was used.",
};

describe("Fidelity and evidence inspection", () => {
  it("shows the effective fallback and its reason", () => {
    mount(<FidelityPanel report={fallbackReport} />);
    cy.contains("Safety checks").should("be.visible");
    cy.contains("A safe fallback was used").should("be.visible");
    cy.contains("summary", "Review technical checks").click();
    cy.contains("Hybrid Safe").should("be.visible");
    cy.contains("Strict Extractive").should("be.visible");
    cy.contains("lacked a current citation").should("be.visible");
  });

  it("uses accessible source tabs and keeps ranking and recovery details disclosed", () => {
    const envelope = createDemoEnvelope("Review the hydration service.", "hybrid_safe");
    cy.intercept("GET", "/api/v1/workspaces", []);
    cy.intercept("GET", "/api/v1/resources/res-architecture/versions/ver-3ac1", {
      resource_id: "res-architecture",
      version_id: "ver-3ac1",
      workspace_id: "ws-context-loom",
      relative_path: "docs/architecture.md",
      kind: "documentation",
      sha256: "a".repeat(64),
      content: "# Local architecture\n\nRecovered sanitized content.",
      current: true,
      redacted_count: 0,
      created_at: "2026-07-19T12:00:00Z",
    }).as("recoverSource");
    mount(<AppProviders><EvidenceList omitted={envelope.omitted_context} selected={envelope.context_items} /></AppProviders>);

    cy.contains("h3", "Sources used").should("be.visible");
    cy.contains("[role='tab']", /^Used/).should("have.attr", "aria-selected", "true").and("have.attr", "tabindex", "0");
    cy.get("[role='tabpanel']").should("be.visible");

    cy.contains("src/context_loom/hydration/service.py").click();
    cy.contains("summary", "Ranking and source integrity").click();
    cy.contains("Score explanation").should("be.visible");
    cy.contains("Source hash").should("be.visible");
    cy.contains("max_input_tokens=4000").should("be.visible");

    cy.contains("[role='tab']", /^Used/).focus().type("{rightarrow}");
    cy.contains("[role='tab']", /^Not included/).should("have.focus").and("have.attr", "aria-selected", "true");
    cy.contains("docs/architecture.md").should("be.visible");
    cy.contains("button", "Open sanitized source").first().click();
    cy.wait("@recoverSource");
    cy.contains("Recovered sanitized content").should("be.visible");
    cy.get(".recovery-preview").should("not.have.attr", "aria-live");
    cy.get(".recovery-preview [role='status']")
      .should("have.text", "Sanitized source ready.")
      .and("not.contain.text", "Recovered sanitized content");
    cy.contains("summary", "Recovery details").click();
    cy.contains("context-loom://resources/res-architecture").should("be.visible");

    cy.contains("[role='tab']", /^Not included/).type("{home}");
    cy.contains("[role='tab']", /^Used/).should("have.focus");
    cy.contains("[role='tab']", /^Used/).type("{end}");
    cy.contains("[role='tab']", /^Not included/).should("have.focus");
    cy.contains("[role='tab']", /^Not included/).type("{leftarrow}");
    cy.contains("[role='tab']", /^Used/).should("have.focus");
  });
});
