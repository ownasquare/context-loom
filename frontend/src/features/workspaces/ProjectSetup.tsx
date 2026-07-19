import { useEffect, useId, useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "../../api/ApiError";
import { useCreateWorkspace, useSyncWorkspace } from "../../api/queries";
import type { SyncReport, WorkspaceRecord } from "../../api/types";
import { useWorkspace } from "../../app/workspace";
import { Icon } from "../../components/icons/Icon";
import { InfoTip } from "../../components/ui/InfoTip";

interface ProjectSetupProps {
  compact?: boolean;
  onConnected?: (workspace: WorkspaceRecord) => void;
}

export function ProjectSetup({ compact = false, onConnected }: ProjectSetupProps) {
  const { setSelectedWorkspaceId, workspaces } = useWorkspace();
  const createWorkspace = useCreateWorkspace();
  const syncWorkspace = useSyncWorkspace();
  const projectPathId = useId();
  const projectPathHelpId = `${projectPathId}-help`;
  const [nameOverride, setNameOverride] = useState("");
  const [rootPath, setRootPath] = useState("");
  const [created, setCreated] = useState<WorkspaceRecord | null>(
    () => workspaces.find((workspace) => workspace.last_sync_at === null) ?? null,
  );
  const [report, setReport] = useState<SyncReport | null>(null);
  const [error, setError] = useState<unknown>(null);
  const pendingWorkspace = workspaces.find((workspace) => workspace.last_sync_at === null) ?? null;
  const isPending = createWorkspace.isPending || syncWorkspace.isPending;
  const suggestedName = projectNameFromPath(rootPath);
  const valid = rootPath.trim().length > 0;

  useEffect(() => {
    if (!created && pendingWorkspace) {
      setCreated(pendingWorkspace);
    }
  }, [created, pendingWorkspace]);

  async function scan(workspace: WorkspaceRecord) {
    setError(null);
    try {
      const nextReport = await syncWorkspace.mutateAsync(workspace.id);
      setReport(nextReport);
      setSelectedWorkspaceId(workspace.id);
      onConnected?.(workspace);
    } catch (caught) {
      setError(caught);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!valid || isPending) {
      return;
    }

    setError(null);
    try {
      const workspace = await createWorkspace.mutateAsync({
        name: nameOverride.trim() || suggestedName,
        root_path: rootPath.trim(),
      });
      setCreated(workspace);
      await scan(workspace);
    } catch (caught) {
      setError(caught);
    }
  }

  if (report && created) {
    return (
      <section aria-live="polite" className={`project-setup project-setup--success${compact ? " project-setup--compact" : ""}`}>
        <span className="project-setup__status-icon"><Icon name="check" /></span>
        <div>
          <p className="eyebrow">Project ready</p>
          <h2>{created.name}</h2>
          <p>{fileChangeSummary(report)}. Context Loom can now prepare messages from this project.</p>
        </div>
      </section>
    );
  }

  return (
    <section className={`project-setup card${compact ? " project-setup--compact" : ""}`}>
      <div className="project-setup__intro">
        <span className="project-setup__icon"><Icon name="layers" /></span>
        <div>
          <p className="eyebrow">{created ? "First scan" : compact ? "Projects" : "Get started"}</p>
          <h1>{created ? "Finish project setup" : compact ? "Add another project" : "Add your first project"}</h1>
          <p>{created ? "Complete the local scan before preparing messages from this project." : "Paste a folder path. Context Loom uses its folder name and scans it locally."}</p>
        </div>
      </div>

      {created ? (
        <div className="project-setup__retry">
          <strong>{created.name} was added, but its first scan did not finish.</strong>
          <p>{error ? publicError(error) : "Run the first scan to make its local project context available."}</p>
          <button className="button button--primary" disabled={syncWorkspace.isPending} onClick={() => void scan(created)} type="button">
            <Icon name="refresh" size={17} />
            {syncWorkspace.isPending ? "Scanning project…" : "Retry scan"}
          </button>
        </div>
      ) : (
        <form className="project-setup__form" onSubmit={(event) => void submit(event)}>
          <div className="field-group project-path-field">
            <span className="field-label field-label--with-tip"><label htmlFor={projectPathId}>Project folder</label><InfoTip label="Project folder">Use the full folder path on the same computer where Context Loom is running.</InfoTip></span>
            <input aria-describedby={projectPathHelpId} autoComplete="off" id={projectPathId} name="root_path" onChange={(event) => setRootPath(event.target.value)} placeholder="/workspace/website" required value={rootPath} />
            <small id={projectPathHelpId}>Use the full path on the computer running Context Loom. The first scan starts automatically.</small>
          </div>
          <details className="advanced-settings">
            <summary>Change project name (optional)</summary>
            <label className="field-group">
              <span className="field-label">Project name</span>
              <input aria-label="Project name" autoComplete="off" maxLength={120} onChange={(event) => setNameOverride(event.target.value)} placeholder={suggestedName} value={nameOverride} />
              <small>Default: {suggestedName}</small>
            </label>
          </details>
          {error ? <p className="form-message form-message--error" role="alert">{publicError(error)}</p> : null}
          <button className="button button--primary button--large" disabled={!valid || isPending} type="submit">
            {isPending ? <span aria-hidden="true" className="button-spinner" /> : <Icon name="layers" size={18} />}
            {createWorkspace.isPending ? "Adding project…" : syncWorkspace.isPending ? "Scanning project…" : "Add and scan project"}
          </button>
        </form>
      )}
    </section>
  );
}

function projectNameFromPath(path: string): string {
  const normalized = path.trim().replace(/[\\/]+$/, "");
  const folderName = normalized.split(/[\\/]/).filter(Boolean).at(-1);
  if (!folderName || folderName === "." || folderName === ".." || /^[a-z]:$/i.test(folderName)) {
    return "Local project";
  }
  return folderName.slice(0, 120);
}

function fileChangeSummary(report: SyncReport): string {
  const parts = [
    `${report.added} ${report.added === 1 ? "file" : "files"} added`,
    `${report.modified} changed`,
    `${report.excluded} excluded`,
  ];
  if (report.redacted > 0) {
    parts.push(`${report.redacted} redacted`);
  }
  return parts.join(" · ");
}

function publicError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.requestId ? `${error.message} (request ${error.requestId})` : error.message;
  }
  return "Context Loom could not complete this local setup. Check the folder path and try again.";
}
