import { mount } from "cypress/react";
import { AppProviders } from "../../src/app/AppProviders";
import { ProjectSetup } from "../../src/features/workspaces/ProjectSetup";
import { WorkspaceControl } from "../../src/features/workspaces/WorkspaceControl";
import { HydratePage } from "../../src/pages/HydratePage";

const now = "2026-07-19T12:00:00Z";
const workspace = {
  id: "workspace-alpha",
  name: "Alpha Project",
  root_path: "/workspace/Alpha Project",
  created_at: now,
  updated_at: now,
  last_sync_at: now,
};

describe("Phase 2 project controls", () => {
  it("creates and scans the first project without requiring the CLI", () => {
    cy.intercept("GET", "/api/v1/workspaces", []).as("listWorkspaces");
    cy.intercept("POST", "/api/v1/workspaces", (request) => {
      expect(request.body).to.deep.equal({
        name: "Alpha Project",
        root_path: "/workspace/Alpha Project",
      });
      request.reply(201, { ...workspace, last_sync_at: null });
    }).as("createWorkspace");
    cy.intercept("POST", "/api/v1/workspaces/workspace-alpha/sync", {
      workspace_id: workspace.id,
      generation_id: "generation-1",
      added: 8,
      modified: 0,
      deleted: 0,
      unchanged: 0,
      excluded: 3,
      redacted: 1,
      duration_ms: 42,
    }).as("syncWorkspace");

    mount(<AppProviders><ProjectSetup /></AppProviders>);
    cy.contains("Add your first project").should("be.visible");
    cy.contains("summary", "Change project name (optional)")
      .parent("details")
      .should("not.have.attr", "open");
    cy.contains("label", "Project folder").should("be.visible");
    cy.get('input[name="root_path"]').should("have.attr", "required");
    cy.get('input[name="root_path"]').type("/workspace/Alpha Project");
    cy.contains("button", "Add and scan project").click();
    cy.wait("@createWorkspace");
    cy.wait("@syncWorkspace");
    cy.contains("Project ready").should("be.visible");
    cy.contains("8 files added").should("be.visible");
  });

  it("keeps project-name customization optional and uses it when provided", () => {
    cy.intercept("GET", "/api/v1/workspaces", []);
    cy.intercept("POST", "/api/v1/workspaces", (request) => {
      expect(request.body).to.deep.equal({
        name: "Customer portal",
        root_path: "/workspace/Alpha Project/",
      });
      request.reply(201, { ...workspace, name: "Customer portal", root_path: "/workspace/Alpha Project/", last_sync_at: null });
    }).as("createNamedWorkspace");
    cy.intercept("POST", "/api/v1/workspaces/workspace-alpha/sync", {
      workspace_id: workspace.id,
      generation_id: "generation-1",
      added: 0,
      modified: 0,
      deleted: 0,
      unchanged: 8,
      excluded: 3,
      redacted: 0,
      duration_ms: 42,
    });

    mount(<AppProviders><ProjectSetup compact /></AppProviders>);
    cy.contains("Projects").should("be.visible");
    cy.contains("Add another project").should("be.visible");
    cy.contains("First project").should("not.exist");
    cy.get('input[name="root_path"]').type("/workspace/Alpha Project/");
    cy.contains("Change project name (optional)").click();
    cy.get('input[aria-label="Project name"]').type("Customer portal");
    cy.contains("button", "Add and scan project").click();
    cy.wait("@createNamedWorkspace");
  });

  it("switches the active project and stores only its harmless identifier", () => {
    cy.intercept("GET", "/api/v1/workspaces", [
      workspace,
      { ...workspace, id: "workspace-beta", name: "Beta project", root_path: "/workspace/Beta" },
    ]);

    mount(<AppProviders><WorkspaceControl /></AppProviders>);
    cy.get('select[aria-label="Current project"]').select("workspace-beta");
    cy.window().then((browserWindow) => {
      expect(browserWindow.localStorage.getItem("context-loom.workspace.v1")).to.equal("workspace-beta");
      expect(browserWindow.localStorage.getItem("context-loom.workspace.v1")).not.to.contain("/workspace/Beta");
    });
  });

  it("keeps first-project setup visible after a failed scan and retries before Prepare", () => {
    let ready = false;
    let scanAttempts = 0;
    const pendingWorkspace = { ...workspace, last_sync_at: null };
    const report = {
      workspace_id: workspace.id,
      generation_id: "generation-1",
      added: 8,
      modified: 0,
      deleted: 0,
      unchanged: 0,
      excluded: 3,
      redacted: 1,
      duration_ms: 42,
    };

    cy.intercept("GET", "/api/v1/workspaces", (request) => {
      request.reply(ready ? [workspace] : []);
    });
    cy.intercept("POST", "/api/v1/workspaces", {
      statusCode: 201,
      body: pendingWorkspace,
    }).as("createPendingWorkspace");
    cy.intercept("POST", "/api/v1/workspaces/workspace-alpha/sync", (request) => {
      scanAttempts += 1;
      if (scanAttempts === 1) {
        request.reply({ statusCode: 500, body: { detail: "The first scan stopped." } });
        return;
      }
      ready = true;
      request.reply(report);
    }).as("retryInitialScan");

    mount(<AppProviders><HydratePage /></AppProviders>);
    cy.get('input[name="root_path"]').type("/workspace/Alpha Project");
    cy.contains("button", "Add and scan project").click();
    cy.wait("@createPendingWorkspace");
    cy.wait("@retryInitialScan");

    cy.contains("h1", "Finish project setup").should("be.visible");
    cy.contains("button", "Retry scan").should("be.visible");
    cy.contains("h2", "What do you want to do?").should("not.exist");

    cy.contains("button", "Retry scan").click();
    cy.wait("@retryInitialScan");
    cy.contains("h2", "What do you want to do?").should("be.visible");
  });
});
