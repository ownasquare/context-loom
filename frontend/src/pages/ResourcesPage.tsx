import { useDeferredValue, useMemo, useRef, useState } from "react";
import type { ResourceSummary } from "../api/types";
import { useResources, useSyncWorkspace, useWorkspaceStatus } from "../api/queries";
import { useWorkspace } from "../app/workspace";
import { Icon } from "../components/icons/Icon";
import { Badge } from "../components/ui/Badge";
import { PageHeader } from "../components/ui/PageHeader";
import { StatePanel } from "../components/ui/StatePanel";
import { ProjectSetup } from "../features/workspaces/ProjectSetup";
import { ResourceDetail } from "../features/resources/ResourceDetail";
import { formatCompactNumber, formatRelativeTime, titleCase } from "../lib/format";

type ResourceFilter = "all" | "current" | "changed";

const FILTERS: readonly { value: ResourceFilter; label: string }[] = [
  { value: "all", label: "All files" },
  { value: "current", label: "Unchanged" },
  { value: "changed", label: "Changed" },
];

export function ResourcesPage() {
  const { selectedWorkspace, selectedWorkspaceId, workspacesQuery } = useWorkspace();
  const resources = useResources(selectedWorkspaceId);
  const status = useWorkspaceStatus(selectedWorkspaceId);
  const syncWorkspace = useSyncWorkspace();
  const [filter, setFilter] = useState<ResourceFilter>("all");
  const [search, setSearch] = useState("");
  const [selectedResource, setSelectedResource] = useState<ResourceSummary | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());
  const visibleResources = useMemo(
    () => (resources.data ?? []).filter((resource) => {
      const matchesFilter = filter === "all" || resource.status === filter;
      const matchesSearch = deferredSearch.length === 0 || resource.relative_path.toLowerCase().includes(deferredSearch) || resource.kind.includes(deferredSearch);
      return matchesFilter && matchesSearch;
    }),
    [deferredSearch, filter, resources.data],
  );

  function openResource(resource: ResourceSummary, trigger: HTMLButtonElement) {
    triggerRef.current = trigger;
    setSelectedResource(resource);
  }

  function closeResource() {
    setSelectedResource(null);
    window.requestAnimationFrame(() => triggerRef.current?.focus());
  }

  if (workspacesQuery.isPending) {
    return <StatePanel kind="loading" />;
  }

  if (workspacesQuery.isError) {
    return <StatePanel kind="error" onRetry={() => void workspacesQuery.refetch()} />;
  }

  if (!selectedWorkspace) {
    return <ProjectSetup />;
  }

  if (resources.isPending) {
    return <StatePanel description="Loading the sanitized files in this project." kind="loading" title="Opening project files" />;
  }

  if (resources.isError) {
    return <StatePanel kind="error" onRetry={() => void resources.refetch()} />;
  }

  return (
    <div className="page page--resources">
      <PageHeader
        action={<button className="button button--secondary" disabled={syncWorkspace.isPending} onClick={() => void syncWorkspace.mutateAsync(selectedWorkspaceId).catch(() => undefined)} type="button"><Icon name="refresh" size={17} />{syncWorkspace.isPending ? "Scanning…" : "Scan for changes"}</button>}
        description="Search the local, sanitized copies Context Loom can use when preparing a message. Open any row to inspect exactly what is available."
        eyebrow={selectedWorkspace.name}
        title="Project files"
      />
      {syncWorkspace.isError ? <p className="form-message form-message--error" role="alert">The scan could not finish. The previous indexed version is still available.</p> : null}

      {status.isPending ? (
        <section aria-label="Project file summary" className="resource-summary-state">
          <StatePanel compact description="Reading current file counts and the latest scan record." kind="loading" title="Loading file summary" />
        </section>
      ) : status.isError ? (
        <section aria-label="Project file summary" className="resource-summary-state">
          <StatePanel compact description="The indexed file list is still available, but its scan totals could not be confirmed." kind="error" onRetry={() => void status.refetch()} title="File summary unavailable" />
        </section>
      ) : (
        <section className="resource-summary-grid" aria-label="Project file summary">
          <div><span className="summary-icon"><Icon name="file" /></span><strong>{formatCompactNumber(status.data.indexed_resources)}</strong><span>Files available</span></div>
          <div><span className="summary-icon"><Icon name="layers" /></span><strong>{formatCompactNumber(status.data.indexed_chunks)}</strong><span>Searchable sections</span></div>
          <div><span className="summary-icon"><Icon name="shield" /></span><strong>{status.data.last_sync?.excluded ?? status.data.excluded_resources}</strong><span>Excluded on last scan</span></div>
          <div><span className="summary-icon"><Icon name="clock" /></span><strong>{formatRelativeTime(status.data.workspace.last_sync_at)}</strong><span>Last scan</span></div>
        </section>
      )}

      <section aria-labelledby="resource-list-title" className="resource-browser card">
        <div className="resource-browser__toolbar">
          <div>
            <p className="eyebrow">{resources.data.length} indexed files</p>
            <h2 id="resource-list-title">Browse files</h2>
          </div>
          <label className="search-field">
            <Icon name="search" size={18} />
            <span className="sr-only">Search project files</span>
            <input onChange={(event) => setSearch(event.target.value)} placeholder="Search by path or type" type="search" value={search} />
            {search ? <button aria-label="Clear search" onClick={() => setSearch("")} type="button">×</button> : null}
          </label>
        </div>
        <div aria-label="Filter project files" className="filter-chips">
          {FILTERS.map((item) => (
            <button aria-pressed={filter === item.value} key={item.value} onClick={() => setFilter(item.value)} type="button">{item.label}</button>
          ))}
        </div>

        {visibleResources.length ? (
          <div className="resource-list">
            <div aria-hidden="true" className="resource-list__header"><span>File</span><span>Type</span><span>Size</span><span>Status</span></div>
            {visibleResources.map((resource) => <ResourceRow key={resource.resource_id} onOpen={openResource} resource={resource} />)}
          </div>
        ) : (
          <StatePanel compact description="Try another path, file type, or status filter." kind="empty" title="No files match this view" />
        )}
      </section>

      {selectedResource ? <ResourceDetail onClose={closeResource} resource={selectedResource} /> : null}
    </div>
  );
}

interface ResourceRowProps {
  resource: ResourceSummary;
  onOpen: (resource: ResourceSummary, trigger: HTMLButtonElement) => void;
}

function ResourceRow({ resource, onOpen }: ResourceRowProps) {
  const tone = resource.status === "current" ? "success" : resource.status === "changed" ? "accent" : resource.status === "stale" ? "warning" : "neutral";
  return (
    <button className="resource-row" onClick={(event) => onOpen(resource, event.currentTarget)} type="button">
      <span className="resource-row__identity">
        <span><Icon name={resource.kind === "code" || resource.kind === "test" ? "terminal" : "file"} size={18} /></span>
        <span><strong>{resource.relative_path}</strong><small>{resource.chunks} searchable sections · {formatRelativeTime(resource.changed_at)}</small></span>
      </span>
      <span className="resource-row__version"><span>{titleCase(resource.kind)}</span><small>Version available</small></span>
      <span className="resource-row__tokens">{formatCompactNumber(resource.estimated_tokens)} tokens</span>
      <span className="resource-row__status"><Badge dot tone={tone}>{resource.status === "current" ? "Unchanged" : titleCase(resource.status)}</Badge><small>{titleCase(resource.change_type)}</small></span>
    </button>
  );
}
