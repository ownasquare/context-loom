import { mount } from "cypress/react";
import { AppProviders } from "../../src/app/AppProviders";
import { demoResources, demoWorkspace } from "../../src/api/demoData";
import { ResourcesPage } from "../../src/pages/ResourcesPage";

describe("ResourcesPage status truth", () => {
  it("keeps indexed files usable without inventing scan totals after a status failure", () => {
    cy.intercept("GET", "/api/v1/workspaces", [demoWorkspace]);
    cy.intercept("GET", "/api/v1/resources*", [demoResources[0]]);
    cy.intercept("GET", `/api/v1/workspaces/${demoWorkspace.id}/status`, {
      statusCode: 503,
      body: { error: { code: "status_unavailable", message: "Status unavailable" } },
    });

    mount(<AppProviders><ResourcesPage /></AppProviders>);

    cy.contains("File summary unavailable").should("be.visible");
    cy.contains("The indexed file list is still available, but its scan totals could not be confirmed.").should("be.visible");
    cy.contains(demoResources[0]!.relative_path).should("be.visible");
    cy.contains("Searchable sections").should("not.exist");
    cy.contains("Last scan").should("not.exist");
  });
});
