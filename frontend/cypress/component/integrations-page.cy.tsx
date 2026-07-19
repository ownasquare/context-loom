import { mount } from "cypress/react";
import { AppProviders } from "../../src/app/AppProviders";
import type { AdapterCapability } from "../../src/api/types";
import { IntegrationsPage } from "../../src/pages/IntegrationsPage";

const adapters: AdapterCapability[] = [
  {
    id: "generic_markdown",
    display_name: "Generic Markdown",
    injection: "manual",
    usage_visibility: "manual",
    formats: ["markdown"],
    install_supported: false,
    status: "available",
    description: "Portable Markdown output",
  },
  {
    id: "openai_responses",
    display_name: "OpenAI Responses",
    injection: "automatic",
    usage_visibility: "provider_observed",
    formats: ["json"],
    install_supported: true,
    status: "available",
    description: "Provider-shaped JSON output",
  },
  {
    id: "codex",
    display_name: "Codex",
    injection: "mcp",
    usage_visibility: "importable",
    formats: ["markdown", "mcp"],
    install_supported: true,
    status: "available",
    description: "MCP-compatible output",
  },
];

describe("IntegrationsPage", () => {
  it("leads with three truthful connection methods and keeps renderers advanced", () => {
    cy.intercept("GET", "/api/v1/workspaces", []);
    cy.intercept("GET", "/api/v1/adapters", adapters);
    mount(<AppProviders><IntegrationsPage /></AppProviders>);

    cy.contains("h3", "Copy and paste").should("be.visible");
    cy.contains("h3", "MCP connection").should("be.visible");
    cy.contains("h3", "MCP connection").should("have.text", "MCP connection");
    cy.contains("h3", "Local API").should("be.visible");
    cy.contains("Recommended").should("be.visible");
    cy.get("body").should("not.contain.text", "adapter preview openai_responses");
    cy.contains("summary", "View setup").click();
    cy.contains("code", "context-loom adapter preview codex").should("be.visible");
    cy.contains("a", "Open harness setup guide")
      .should("have.attr", "href")
      .and("include", "#2-mcp-connection");
    cy.contains("summary", "Advanced output formats").click();
    cy.contains("OpenAI Responses").should("be.visible");
    cy.contains("Provider-shaped output only — not a connection installer.").should("be.visible");
  });
});
