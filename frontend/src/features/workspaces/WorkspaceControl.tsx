import { useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { useSyncWorkspace } from "../../api/queries";
import type { SyncReport, WorkspaceRecord } from "../../api/types";
import { useWorkspace } from "../../app/workspace";
import { Icon } from "../../components/icons/Icon";
import { ProjectSetup } from "./ProjectSetup";

interface WorkspaceControlProps {
  compact?: boolean;
}

export function WorkspaceControl({ compact = false }: WorkspaceControlProps) {
  const { selectedWorkspace, selectedWorkspaceId, setSelectedWorkspaceId, workspaces } = useWorkspace();
  const readyWorkspaces = workspaces.filter((workspace) => workspace.last_sync_at !== null);
  const syncWorkspace = useSyncWorkspace();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [report, setReport] = useState<SyncReport | null>(null);
  const [syncFailed, setSyncFailed] = useState(false);

  function selectWorkspace(event: ChangeEvent<HTMLSelectElement>) {
    setReport(null);
    setSyncFailed(false);
    setSelectedWorkspaceId(event.target.value);
  }

  async function sync() {
    if (!selectedWorkspaceId || syncWorkspace.isPending) {
      return;
    }
    setSyncFailed(false);
    try {
      const nextReport = await syncWorkspace.mutateAsync(selectedWorkspaceId);
      setReport(nextReport);
    } catch {
      setSyncFailed(true);
    }
  }

  function closeAfterConnect(workspace: WorkspaceRecord) {
    setSelectedWorkspaceId(workspace.id);
    window.setTimeout(() => dialogRef.current?.close(), 650);
  }

  if (!readyWorkspaces.length) {
    return null;
  }

  return (
    <div className={`workspace-control${compact ? " workspace-control--compact" : ""}`}>
      <label className="workspace-control__select">
        <span>Project</span>
        <select aria-label="Current project" onChange={selectWorkspace} value={selectedWorkspaceId}>
          {readyWorkspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
        </select>
      </label>
      <div className="workspace-control__actions">
        <button aria-label={`Scan ${selectedWorkspace?.name ?? "current project"} for changes`} className="icon-button" disabled={!selectedWorkspaceId || syncWorkspace.isPending} onClick={() => void sync()} title="Scan for changes" type="button">
          {syncWorkspace.isPending ? <span aria-hidden="true" className="button-spinner" /> : <Icon name="refresh" size={17} />}
        </button>
        <button aria-label="Add project" className="icon-button" onClick={() => dialogRef.current?.showModal()} title="Add project" type="button">+</button>
      </div>
      <p aria-live="polite" className="workspace-control__message">
        {syncWorkspace.isPending ? "Scanning changes…" : syncFailed ? "Scan failed. Previous project data is still available." : report ? scanSummary(report) : selectedWorkspace?.root_path}
      </p>

      <dialog className="project-dialog" ref={dialogRef}>
        <div className="project-dialog__toolbar">
          <strong>Add project</strong>
          <button aria-label="Close add project" className="icon-button" onClick={() => dialogRef.current?.close()} type="button">×</button>
        </div>
        <ProjectSetup compact onConnected={closeAfterConnect} />
      </dialog>
    </div>
  );
}

function scanSummary(report: SyncReport): string {
  const changed = report.added + report.modified + report.deleted;
  return changed === 0 ? "No file changes" : `${changed} file ${changed === 1 ? "change" : "changes"} found`;
}
