import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { mount } from "cypress/react";
import type { ReactNode } from "react";
import { apiClient } from "../../src/api/client";
import { useCreateWorkspace } from "../../src/api/queries";
import type { WorkspaceRecord } from "../../src/api/types";
import {
  WORKSPACE_SELECTION_STORAGE_KEY,
  WorkspaceProvider,
  useWorkspace,
} from "../../src/app/workspace";

const workspaceA: WorkspaceRecord = {
  id: "workspace-a",
  name: "Project Alpha",
  root_path: "/workspace/alpha",
  created_at: "2026-07-19T12:00:00.000Z",
  updated_at: "2026-07-19T12:00:00.000Z",
  last_sync_at: "2026-07-19T12:00:30.000Z",
};

const workspaceB: WorkspaceRecord = {
  id: "workspace-b",
  name: "Project Beta",
  root_path: "/workspace/beta",
  created_at: "2026-07-19T12:01:00.000Z",
  updated_at: "2026-07-19T12:01:00.000Z",
  last_sync_at: "2026-07-19T12:01:30.000Z",
};

function mountWorkspace(children: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  mount(
    <QueryClientProvider client={queryClient}>
      <WorkspaceProvider>{children}</WorkspaceProvider>
    </QueryClientProvider>,
  );
}

function WorkspaceProbe() {
  const {
    selectedWorkspace,
    selectedWorkspaceId,
    setSelectedWorkspaceId,
    workspaces,
  } = useWorkspace();

  return (
    <div>
      <output aria-label="selected workspace">{selectedWorkspace?.name ?? "None"}</output>
      <output aria-label="selected workspace id">{selectedWorkspaceId || "none"}</output>
      <output aria-label="workspace count">{workspaces.length}</output>
      <button type="button" onClick={() => setSelectedWorkspaceId(workspaceA.id)}>
        Select Alpha
      </button>
    </div>
  );
}

function CreateWorkspaceProbe() {
  const createWorkspace = useCreateWorkspace();
  const { selectedWorkspace, setSelectedWorkspaceId, workspaces } = useWorkspace();

  async function createAndSelect() {
    const created = await createWorkspace.mutateAsync({
      name: workspaceB.name,
      root_path: workspaceB.root_path,
    });
    setSelectedWorkspaceId(created.id);
  }

  return (
    <div>
      <output aria-label="selected workspace">{selectedWorkspace?.name ?? "None"}</output>
      <output aria-label="workspace count">{workspaces.length}</output>
      <button type="button" onClick={() => void createAndSelect()}>
        Add Beta
      </button>
    </div>
  );
}

describe("WorkspaceProvider", () => {
  it("restores a valid selection and lists workspaces once", () => {
    window.localStorage.setItem(WORKSPACE_SELECTION_STORAGE_KEY, workspaceB.id);
    const listStub = cy.stub(apiClient, "listWorkspaces").resolves([workspaceA, workspaceB]);

    mountWorkspace(<WorkspaceProbe />);

    cy.get('[aria-label="selected workspace"]').should("have.text", workspaceB.name);
    cy.get('[aria-label="workspace count"]').should("have.text", "2");
    cy.wrap(listStub).should("have.been.calledOnce");
  });

  it("replaces a stale cross-project selection with the first available workspace", () => {
    window.localStorage.setItem(WORKSPACE_SELECTION_STORAGE_KEY, "removed-workspace");
    cy.stub(apiClient, "listWorkspaces").resolves([workspaceA]);

    mountWorkspace(<WorkspaceProbe />);

    cy.get('[aria-label="selected workspace"]').should("have.text", workspaceA.name);
    cy.get('[aria-label="selected workspace id"]').should("have.text", workspaceA.id);
    cy.window().then((windowObject) => {
      expect(windowObject.localStorage.getItem(WORKSPACE_SELECTION_STORAGE_KEY)).to.equal(workspaceA.id);
    });
  });

  it("clears a stale selection when no workspace is registered", () => {
    window.localStorage.setItem(WORKSPACE_SELECTION_STORAGE_KEY, "removed-workspace");
    cy.stub(apiClient, "listWorkspaces").resolves([]);

    mountWorkspace(<WorkspaceProbe />);

    cy.get('[aria-label="selected workspace"]').should("have.text", "None");
    cy.get('[aria-label="selected workspace id"]').should("have.text", "none");
    cy.window().then((windowObject) => {
      expect(windowObject.localStorage.getItem(WORKSPACE_SELECTION_STORAGE_KEY)).to.equal(null);
    });
  });

  it("keeps a newly created workspace pending until its first scan succeeds", () => {
    cy.stub(apiClient, "listWorkspaces").resolves([workspaceA]);
    cy.stub(apiClient, "createWorkspace").resolves({ ...workspaceB, last_sync_at: null });

    mountWorkspace(<CreateWorkspaceProbe />);

    cy.get('[aria-label="selected workspace"]').should("have.text", workspaceA.name);
    cy.contains("button", "Add Beta").click();
    cy.get('[aria-label="selected workspace"]').should("have.text", workspaceA.name);
    cy.get('[aria-label="workspace count"]').should("have.text", "2");
    cy.window().then((windowObject) => {
      expect(windowObject.localStorage.getItem(WORKSPACE_SELECTION_STORAGE_KEY)).to.equal(workspaceA.id);
    });
  });
});
