import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";
import { queryKeys } from "./queryKeys";
import type { UsageObservation, WorkspaceCreate, WorkspaceRecord } from "./types";

export function useWorkspaces() {
  return useQuery({
    queryKey: queryKeys.workspaces,
    queryFn: ({ signal }) => apiClient.listWorkspaces(signal),
  });
}

export function useCreateWorkspace() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (request: WorkspaceCreate) => apiClient.createWorkspace(request),
    onSuccess: (createdWorkspace) => {
      queryClient.setQueryData<WorkspaceRecord[]>(queryKeys.workspaces, (current = []) => {
        const withoutDuplicate = current.filter(
          (workspace) => workspace.id !== createdWorkspace.id,
        );
        return [...withoutDuplicate, createdWorkspace];
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.workspaces,
        refetchType: "none",
      });
    },
  });
}

export function useWorkspaceStatus(workspaceId: string) {
  return useQuery({
    enabled: workspaceId.length > 0,
    queryKey: queryKeys.workspaceStatus(workspaceId),
    queryFn: ({ signal }) => apiClient.getWorkspaceStatus(workspaceId, signal),
  });
}

export function useSyncWorkspace() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (workspaceId: string) => apiClient.syncWorkspace(workspaceId),
    onSuccess: async (_report, workspaceId) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.workspaces }),
        queryClient.invalidateQueries({ queryKey: queryKeys.workspaceStatus(workspaceId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.resources(workspaceId) }),
      ]);
    },
  });
}

export function useResources(workspaceId: string) {
  return useQuery({
    enabled: workspaceId.length > 0,
    queryKey: queryKeys.resources(workspaceId),
    queryFn: ({ signal }) => apiClient.listResources(workspaceId, signal),
  });
}

export function useResourceVersion(
  resourceId: string,
  versionId: string,
  enabled = true,
) {
  return useQuery({
    enabled: enabled && resourceId.length > 0 && versionId.length > 0,
    queryKey: queryKeys.resourceVersion(resourceId, versionId),
    queryFn: ({ signal }) => apiClient.resolveResourceVersion(resourceId, versionId, signal),
  });
}

export function useThreads(workspaceId: string) {
  return useQuery({
    enabled: workspaceId.length > 0,
    queryKey: queryKeys.threads(workspaceId),
    queryFn: ({ signal }) => apiClient.listThreads(workspaceId, signal),
  });
}

export function useRecordUsage(workspaceId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (observation: UsageObservation) => apiClient.recordUsage(observation),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.threads(workspaceId) });
    },
  });
}

export function useAdapters() {
  return useQuery({
    queryKey: queryKeys.adapters,
    queryFn: ({ signal }) => apiClient.listAdapters(signal),
  });
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => apiClient.getHealth(signal),
  });
}

export function useReadiness() {
  return useQuery({
    queryKey: queryKeys.readiness,
    queryFn: ({ signal }) => apiClient.getReadiness(signal),
  });
}
