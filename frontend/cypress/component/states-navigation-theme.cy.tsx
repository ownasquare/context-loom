import { mount } from "cypress/react";
import { Sidebar } from "../../src/components/layout/Sidebar";
import { StatePanel } from "../../src/components/ui/StatePanel";
import { ThemeControl } from "../../src/components/ui/ThemeControl";
import { ThemeProvider } from "../../src/app/theme";
import { AppProviders } from "../../src/app/AppProviders";
import { Topbar } from "../../src/components/layout/Topbar";

describe("Workbench states and controls", () => {
  it("provides distinct loading, empty, and recoverable error states", () => {
    mount(
      <div>
        <StatePanel compact kind="loading" />
        <StatePanel compact kind="empty" />
        <StatePanel compact kind="error" onRetry={cy.stub().as("retry")} />
      </div>,
    );

    cy.contains("Loading local data").should("be.visible");
    cy.contains("Nothing here yet").should("be.visible");
    cy.contains("Local service unavailable").should("be.visible");
    cy.contains("button", "Try again").click();
    cy.get("@retry").should("have.been.calledOnce");
  });

  it("routes semantic navigation without requiring a full reload", () => {
    const navigate = cy.stub().as("navigate");
    cy.intercept("GET", "/api/v1/workspaces", []);
    cy.intercept("GET", "/healthz", {
      status: "ok",
      version: "0.1.0",
      database: "ready",
      local_model: "disabled",
      outbound_allowed: false,
      retain_message_content: false,
    });
    mount(<AppProviders><Sidebar activeRoute="overview" onNavigate={navigate} /></AppProviders>);
    cy.contains("Local by default").should("be.visible");
    cy.contains("Outbound blocked · messages not retained").should("be.visible");
    cy.contains("a", "Project files").click();
    cy.get("@navigate").should("have.been.calledWith", "resources");
  });

  it("reports outbound and retention settings truthfully in persistent chrome", () => {
    const navigate = cy.stub();
    cy.intercept("GET", "/api/v1/workspaces", []);
    cy.intercept("GET", "/healthz", {
      status: "ok",
      version: "0.1.0",
      database: "ready",
      local_model: "disabled",
      outbound_allowed: true,
      retain_message_content: true,
    });

    mount(
      <AppProviders>
        <Sidebar activeRoute="overview" onNavigate={navigate} />
        <Topbar activeRoute="overview" onNavigate={navigate} />
      </AppProviders>,
    );

    cy.contains("Outbound and retention on").should("be.visible");
    cy.contains("Selected context may leave · messages retained").should("be.visible");
    cy.contains("Outbound + retention").should("be.visible");
  });

  it("uses neutral loading copy instead of flashing disconnected or private claims", () => {
    const navigate = cy.stub();
    cy.viewport(1400, 800);
    cy.intercept("GET", "/api/v1/workspaces", (request) => {
      request.reply({ delay: 10_000, body: [] });
    });
    cy.intercept("GET", "/healthz", (request) => {
      request.reply({
        delay: 10_000,
        body: {
          status: "ok",
          version: "0.1.0",
          database: "ready",
          local_model: "disabled",
          outbound_allowed: false,
          retain_message_content: false,
        },
      });
    });

    mount(
      <AppProviders>
        <Sidebar activeRoute="overview" onNavigate={navigate} />
        <Topbar activeRoute="overview" onNavigate={navigate} />
      </AppProviders>,
    );

    cy.get(".topbar__title").should("contain.text", "Loading project…");
    cy.contains("No project connected").should("not.exist");
    cy.contains("Checking privacy").should("be.visible");
    cy.contains("Local and private").should("not.exist");
  });

  it("applies and stores an explicit dark theme preference", () => {
    mount(<ThemeProvider><ThemeControl /></ThemeProvider>);
    cy.contains("button", "Dark").click();
    cy.document().its("documentElement.dataset.theme").should("equal", "dark");
    cy.window().then((windowObject) => {
      expect(windowObject.localStorage.getItem("context-loom.theme.v1")).to.equal("dark");
    });
    cy.contains("button", "Dark").type("{rightarrow}");
    cy.contains("button", "System").should("have.attr", "aria-checked", "true").and("be.focused");
  });

  it("closes the mobile destination menu after selection, outside click, and Escape", () => {
    const navigate = cy.stub().as("mobileNavigate");
    cy.viewport(390, 844);
    cy.intercept("GET", "/api/v1/workspaces", []);
    cy.intercept("GET", "/healthz", {
      status: "ok",
      version: "0.1.0",
      database: "ready",
      local_model: "disabled",
      outbound_allowed: false,
      retain_message_content: false,
    });
    mount(<AppProviders><Topbar activeRoute="overview" onNavigate={navigate} /></AppProviders>);

    cy.get('.mobile-more > summary[aria-label="Project and app controls"]').click();
    cy.get("details.mobile-more").should("have.attr", "open");
    cy.contains(".mobile-more button", "Connections").click();
    cy.get("@mobileNavigate").should("have.been.calledWith", "integrations");
    cy.get("details.mobile-more").should("not.have.attr", "open");

    cy.get('.mobile-more > summary[aria-label="Project and app controls"]').click();
    cy.get("body").click(1, 1);
    cy.get("details.mobile-more").should("not.have.attr", "open");

    cy.get('.mobile-more > summary[aria-label="Project and app controls"]').click();
    cy.document().trigger("keydown", { key: "Escape" });
    cy.get("details.mobile-more").should("not.have.attr", "open");
    cy.get(".mobile-more > summary").should("be.focused");
  });

  it("keeps project actions and truthful privacy warnings reachable on mobile", () => {
    const navigate = cy.stub();
    const now = "2026-07-19T12:00:00Z";
    const alpha = { id: "workspace-alpha", name: "Alpha project", root_path: "/workspace/alpha", created_at: now, updated_at: now, last_sync_at: now };
    const beta = { ...alpha, id: "workspace-beta", name: "Beta project", root_path: "/workspace/beta" };
    cy.viewport(320, 568);
    cy.intercept("GET", "/api/v1/workspaces", [alpha, beta]);
    cy.intercept("GET", "/healthz", {
      status: "ok",
      version: "0.1.0",
      database: "ready",
      local_model: "disabled",
      outbound_allowed: true,
      retain_message_content: true,
    });
    cy.intercept("POST", "/api/v1/workspaces/workspace-beta/sync", {
      workspace_id: beta.id,
      generation_id: "generation-beta",
      added: 0,
      modified: 1,
      deleted: 0,
      unchanged: 7,
      excluded: 2,
      redacted: 0,
      duration_ms: 31,
    }).as("scanBeta");

    mount(<AppProviders><Topbar activeRoute="overview" onNavigate={navigate} /></AppProviders>);

    cy.get(".privacy-chip")
      .should("be.visible")
      .and("contain.text", "Outbound + retention")
      .and("have.attr", "aria-label", "Outbound and retention on. Selected context may leave · messages retained");
    cy.get('summary[aria-label="Project and app controls"]').click();
    cy.get('select[aria-label="Current project"]').select(beta.id);
    cy.get('button[aria-label="Scan Beta project for changes"]').click();
    cy.wait("@scanBeta");
    cy.get('button[aria-label="Add project"]').click();
    cy.get("dialog[open]").should("be.visible");
    cy.get('button[aria-label="Close add project"]').click();
  });
});
