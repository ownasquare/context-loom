import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import { useWorkspaces } from "../api/queries";
import type { WorkspaceRecord } from "../api/types";

export const WORKSPACE_SELECTION_STORAGE_KEY = "context-loom.workspace.v1";

const EMPTY_WORKSPACES: WorkspaceRecord[] = [];

interface WorkspaceContextValue {
  workspaces: WorkspaceRecord[];
  selectedWorkspace: WorkspaceRecord | null;
  selectedWorkspaceId: string;
  setSelectedWorkspaceId: (workspaceId: string) => void;
  workspacesQuery: ReturnType<typeof useWorkspaces>;
  refetchWorkspaces: ReturnType<typeof useWorkspaces>["refetch"];
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

interface WorkspaceProviderProps {
  children: ReactNode;
}

export function WorkspaceProvider({ children }: WorkspaceProviderProps) {
  const workspacesQuery = useWorkspaces();
  const workspaces = workspacesQuery.data ?? EMPTY_WORKSPACES;
  const readyWorkspaces = useMemo(
    () => workspaces.filter((workspace) => workspace.last_sync_at !== null),
    [workspaces],
  );
  const [requestedWorkspaceId, setRequestedWorkspaceId] = useState(readStoredWorkspaceId);
  const selectedWorkspace =
    readyWorkspaces.find((workspace) => workspace.id === requestedWorkspaceId) ??
    readyWorkspaces[0] ??
    null;
  const selectedWorkspaceId = selectedWorkspace?.id ?? "";

  useEffect(() => {
    if (!workspacesQuery.isSuccess) {
      return;
    }

    if (selectedWorkspaceId && requestedWorkspaceId !== selectedWorkspaceId) {
      setRequestedWorkspaceId(selectedWorkspaceId);
      writeStoredWorkspaceId(selectedWorkspaceId);
      return;
    }

    if (!selectedWorkspaceId && requestedWorkspaceId) {
      setRequestedWorkspaceId("");
      writeStoredWorkspaceId("");
    }
  }, [
    requestedWorkspaceId,
    selectedWorkspaceId,
    workspacesQuery.isSuccess,
  ]);

  const selectWorkspace = useCallback((workspaceId: string) => {
    const nextWorkspaceId = workspaceId.trim();
    setRequestedWorkspaceId(nextWorkspaceId);
    writeStoredWorkspaceId(nextWorkspaceId);
  }, []);

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      workspaces,
      selectedWorkspace,
      selectedWorkspaceId,
      setSelectedWorkspaceId: selectWorkspace,
      workspacesQuery,
      refetchWorkspaces: workspacesQuery.refetch,
    }),
    [
      selectWorkspace,
      selectedWorkspace,
      selectedWorkspaceId,
      workspaces,
      workspacesQuery,
    ],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error("useWorkspace must be used inside WorkspaceProvider");
  }
  return context;
}

function readStoredWorkspaceId(): string {
  if (typeof window === "undefined") {
    return "";
  }
  try {
    return window.localStorage.getItem(WORKSPACE_SELECTION_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function writeStoredWorkspaceId(workspaceId: string): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    if (workspaceId) {
      window.localStorage.setItem(WORKSPACE_SELECTION_STORAGE_KEY, workspaceId);
    } else {
      window.localStorage.removeItem(WORKSPACE_SELECTION_STORAGE_KEY);
    }
  } catch {
    // A blocked storage API should not prevent local workspace use.
  }
}
