import { DemoTransport } from "./demoTransport";
import { fetchJson } from "./fetchJson";
import type {
  AdapterCapability,
  ApiList,
  HealthStatus,
  HydrateRequest,
  HydrationResponse,
  ReadinessStatus,
  ResourceSummary,
  ResourceVersionContent,
  SyncReport,
  ThreadSummary,
  ThreadTokenSummary,
  UsageObservation,
  WorkspaceCreate,
  WorkspaceRecord,
  WorkspaceStatus,
} from "./types";

export class ContextLoomApiClient {
  private readonly demoMode: boolean;
  private readonly demoTransport = new DemoTransport();

  constructor(search = window.location.search) {
    this.demoMode = new URLSearchParams(search).get("demo") === "1";
  }

  isDemoMode(): boolean {
    return this.demoMode;
  }

  async listWorkspaces(signal?: AbortSignal): Promise<WorkspaceRecord[]> {
    if (this.demoMode) {
      return this.demoTransport.listWorkspaces(signal);
    }

    return normalizeList(await fetchJson<ApiList<WorkspaceRecord> | WorkspaceRecord[]>("/api/v1/workspaces", { signal }));
  }

  async createWorkspace(request: WorkspaceCreate, signal?: AbortSignal): Promise<WorkspaceRecord> {
    if (this.demoMode) {
      return this.demoTransport.createWorkspace(request, signal);
    }

    return fetchJson<WorkspaceRecord>("/api/v1/workspaces", {
      method: "POST",
      body: request,
      signal,
    });
  }

  async getWorkspaceStatus(workspaceId: string, signal?: AbortSignal): Promise<WorkspaceStatus> {
    if (this.demoMode) {
      return this.demoTransport.getWorkspaceStatus(workspaceId, signal);
    }

    return fetchJson<WorkspaceStatus>(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/status`, { signal });
  }

  async syncWorkspace(workspaceId: string, signal?: AbortSignal): Promise<SyncReport> {
    if (this.demoMode) {
      return this.demoTransport.syncWorkspace(workspaceId, signal);
    }

    return fetchJson<SyncReport>(
      `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sync`,
      { method: "POST", signal },
    );
  }

  async listResources(workspaceId: string, signal?: AbortSignal): Promise<ResourceSummary[]> {
    if (this.demoMode) {
      return this.demoTransport.listResources(workspaceId, signal);
    }

    const params = new URLSearchParams({ workspace_id: workspaceId });
    return normalizeList(await fetchJson<ApiList<ResourceSummary> | ResourceSummary[]>(`/api/v1/resources?${params.toString()}`, { signal }));
  }

  async resolveResourceVersion(
    resourceId: string,
    versionId: string,
    signal?: AbortSignal,
  ): Promise<ResourceVersionContent> {
    if (this.demoMode) {
      return this.demoTransport.resolveResourceVersion(resourceId, versionId, signal);
    }

    return fetchJson<ResourceVersionContent>(
      `/api/v1/resources/${encodeURIComponent(resourceId)}/versions/${encodeURIComponent(versionId)}`,
      { signal },
    );
  }

  async listThreads(workspaceId: string, signal?: AbortSignal): Promise<ThreadSummary[]> {
    if (this.demoMode) {
      return this.demoTransport.listThreads(workspaceId, signal);
    }

    const params = new URLSearchParams({ workspace_id: workspaceId });
    return normalizeList(await fetchJson<ApiList<ThreadSummary> | ThreadSummary[]>(`/api/v1/threads?${params.toString()}`, { signal }));
  }

  async recordUsage(
    observation: UsageObservation,
    signal?: AbortSignal,
  ): Promise<ThreadTokenSummary> {
    if (this.demoMode) {
      return this.demoTransport.recordUsage(observation, signal);
    }

    return fetchJson<ThreadTokenSummary>(
      `/api/v1/threads/${encodeURIComponent(observation.thread_id)}/usage`,
      { method: "POST", body: observation, signal },
    );
  }

  async listAdapters(signal?: AbortSignal): Promise<AdapterCapability[]> {
    if (this.demoMode) {
      return this.demoTransport.listAdapters(signal);
    }

    const adapters = normalizeList(
      await fetchJson<ApiList<AdapterCapabilityWire> | AdapterCapabilityWire[]>("/api/v1/adapters", { signal }),
    );
    return adapters.map(enrichAdapter);
  }

  async getHealth(signal?: AbortSignal): Promise<HealthStatus> {
    if (this.demoMode) {
      return this.demoTransport.getHealth(signal);
    }

    return fetchJson<HealthStatus>("/healthz", { signal });
  }

  async getReadiness(signal?: AbortSignal): Promise<ReadinessStatus> {
    if (this.demoMode) {
      return this.demoTransport.getReadiness(signal);
    }

    return fetchJson<ReadinessStatus>("/readyz", { signal });
  }

  async hydrate(request: HydrateRequest, signal?: AbortSignal): Promise<HydrationResponse> {
    if (this.demoMode) {
      return this.demoTransport.hydrate(request, signal);
    }

    const response = await fetchJson<HydrationResponse>("/api/v1/hydrations", {
      method: "POST",
      body: request,
      signal,
    });
    return response;
  }
}

function normalizeList<T>(response: ApiList<T> | T[]): T[] {
  return Array.isArray(response) ? response : response.items;
}

type AdapterCapabilityWire = Omit<AdapterCapability, "status" | "description"> &
  Partial<Pick<AdapterCapability, "status" | "description">>;

function enrichAdapter(adapter: AdapterCapabilityWire): AdapterCapability {
  return {
    ...adapter,
    status: adapter.status ?? deriveAdapterStatus(adapter),
    description: adapter.description ?? deriveAdapterDescription(adapter),
  };
}

function deriveAdapterStatus(adapter: AdapterCapabilityWire): AdapterCapability["status"] {
  if (!adapter.install_supported || adapter.injection === "manual") {
    return "manual_setup";
  }
  return adapter.injection === "automatic" || adapter.injection === "mcp" ? "ready" : "available";
}

function deriveAdapterDescription(adapter: AdapterCapabilityWire): string {
  if (adapter.injection === "automatic") {
    return "Automatic local hydration with canonical envelope rendering and usage readback.";
  }
  if (adapter.injection === "mcp") {
    return "Harness-neutral MCP tools for hydration, context inspection, and token records.";
  }
  if (adapter.injection === "wrapper") {
    return "A local wrapper renders source-preserving context for this harness.";
  }
  return "Copy or export a compiled envelope without storing provider credentials.";
}

export const apiClient = new ContextLoomApiClient();
