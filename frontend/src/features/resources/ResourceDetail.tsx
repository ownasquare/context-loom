import { useEffect, useRef, useState } from "react";
import type { ResourceSummary } from "../../api/types";
import { useResourceVersion } from "../../api/queries";
import { Icon } from "../../components/icons/Icon";
import { Badge } from "../../components/ui/Badge";
import { StatePanel } from "../../components/ui/StatePanel";
import { formatRelativeTime, shortHash, titleCase } from "../../lib/format";

interface ResourceDetailProps {
  resource: ResourceSummary;
  onClose: () => void;
}

type CopyState = "idle" | "copied" | "failed";

export function ResourceDetail({ resource, onClose }: ResourceDetailProps) {
  const version = useResourceVersion(resource.resource_id, resource.version_id, true);
  const [copyState, setCopyState] = useState<CopyState>("idle");
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) {
      dialog.showModal();
    }
    return () => {
      if (dialog?.open) {
        dialog.close();
      }
    };
  }, []);

  function closeDialog() {
    if (dialogRef.current?.open) {
      dialogRef.current.close();
    }
    onClose();
  }

  async function copyContent() {
    if (!version.data) {
      return;
    }
    try {
      await navigator.clipboard.writeText(version.data.content);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  return (
    <dialog
      aria-label={`File preview: ${resource.relative_path}`}
      aria-modal="true"
      className="resource-detail"
      onCancel={(event) => {
        event.preventDefault();
        closeDialog();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          closeDialog();
        }
      }}
      ref={dialogRef}
    >
      <div className="resource-detail__surface">
        <header className="resource-detail__header">
          <div>
            <p className="eyebrow">Sanitized local copy</p>
            <h2>{resource.relative_path}</h2>
          </div>
          <button aria-label="Close file preview" autoFocus className="icon-button" onClick={closeDialog} type="button">×</button>
        </header>

        {version.isPending ? <StatePanel compact description="Loading the selected local version." kind="loading" title="Opening file" /> : null}
        {version.isError ? <StatePanel compact description="This indexed version could not be recovered." kind="error" onRetry={() => void version.refetch()} title="File preview unavailable" /> : null}
        {version.data ? (
          <>
            <div className="resource-detail__status">
              <Badge dot tone={version.data.current ? "success" : "warning"}>{version.data.current ? "Current version" : "Historical version"}</Badge>
              <span>{titleCase(version.data.kind)} · indexed {formatRelativeTime(version.data.created_at)}</span>
              <span>{version.data.redacted_count === 0 ? "No configured sensitive patterns detected" : `${version.data.redacted_count} detected sensitive ${version.data.redacted_count === 1 ? "pattern" : "patterns"} redacted`}</span>
            </div>
            <pre className="resource-detail__content" tabIndex={0}>{version.data.content || "This indexed file is empty."}</pre>
            <div className="resource-detail__actions">
              <p aria-live="polite">{copyState === "copied" ? "File content copied" : copyState === "failed" ? "Copy unavailable. Select the text above instead." : "Content is displayed as plain text and cannot run."}</p>
              <button className="button button--primary" onClick={() => void copyContent()} type="button"><Icon name="copy" size={17} />Copy file content</button>
            </div>
            <details className="technical-details">
              <summary>Version details</summary>
              <dl>
                <div><dt>Resource</dt><dd><code>{version.data.resource_id}</code></dd></div>
                <div><dt>Version</dt><dd><code>{version.data.version_id}</code></dd></div>
                <div><dt>Source hash</dt><dd><code>{shortHash(version.data.sha256)}</code></dd></div>
              </dl>
            </details>
          </>
        ) : null}
      </div>
    </dialog>
  );
}
