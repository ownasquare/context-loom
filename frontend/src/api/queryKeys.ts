export const queryKeys = {
  workspaces: ["workspaces"] as const,
  workspaceStatus: (workspaceId: string) => ["workspace", workspaceId, "status"] as const,
  resources: (workspaceId: string) => ["workspace", workspaceId, "resources"] as const,
  resourceVersion: (resourceId: string, versionId: string) =>
    ["resource", resourceId, "version", versionId] as const,
  threads: (workspaceId: string) => ["workspace", workspaceId, "threads"] as const,
  adapters: ["adapters"] as const,
  health: ["health"] as const,
  readiness: ["readiness"] as const,
};
