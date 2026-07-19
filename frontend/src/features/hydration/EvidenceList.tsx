import { useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { ContextItem, OmittedContext } from "../../api/types";
import { titleCase } from "../../lib/format";
import { Icon } from "../../components/icons/Icon";
import { Badge } from "../../components/ui/Badge";
import { ScoreBreakdownView } from "./ScoreBreakdownView";
import { useResourceVersion } from "../../api/queries";

interface EvidenceListProps {
  selected: ContextItem[];
  omitted: OmittedContext[];
}

type EvidenceTab = "selected" | "omitted";

export function EvidenceList({ selected, omitted }: EvidenceListProps) {
  const [tab, setTab] = useState<EvidenceTab>("selected");
  const idPrefix = useId();
  const selectedTabRef = useRef<HTMLButtonElement>(null);
  const omittedTabRef = useRef<HTMLButtonElement>(null);
  const selectedTabId = `${idPrefix}-used-tab`;
  const omittedTabId = `${idPrefix}-not-included-tab`;
  const panelId = `${idPrefix}-sources-panel`;

  function activateTab(nextTab: EvidenceTab) {
    setTab(nextTab);
    const target = nextTab === "selected" ? selectedTabRef.current : omittedTabRef.current;
    target?.focus();
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    let nextTab: EvidenceTab | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      nextTab = tab === "selected" ? "omitted" : "selected";
    } else if (event.key === "Home") {
      nextTab = "selected";
    } else if (event.key === "End") {
      nextTab = "omitted";
    }

    if (nextTab) {
      event.preventDefault();
      activateTab(nextTab);
    }
  }

  return (
    <section aria-labelledby="evidence-title" className="evidence-panel card">
      <div className="evidence-panel__heading">
        <div>
          <p className="eyebrow">Project context</p>
          <h3 id="evidence-title">Sources used</h3>
        </div>
        <div aria-label="Source view" className="tab-control" role="tablist">
          <button
            aria-controls={panelId}
            aria-selected={tab === "selected"}
            id={selectedTabId}
            onClick={() => activateTab("selected")}
            onKeyDown={handleTabKeyDown}
            ref={selectedTabRef}
            role="tab"
            tabIndex={tab === "selected" ? 0 : -1}
            type="button"
          >
            Used <span>{selected.length}</span>
          </button>
          <button
            aria-controls={panelId}
            aria-selected={tab === "omitted"}
            id={omittedTabId}
            onClick={() => activateTab("omitted")}
            onKeyDown={handleTabKeyDown}
            ref={omittedTabRef}
            role="tab"
            tabIndex={tab === "omitted" ? 0 : -1}
            type="button"
          >
            Not included <span>{omitted.length}</span>
          </button>
        </div>
      </div>

      <div
        aria-labelledby={tab === "selected" ? selectedTabId : omittedTabId}
        className="evidence-list"
        id={panelId}
        role="tabpanel"
        tabIndex={0}
      >
        {tab === "selected"
          ? selected.map((item, index) => <SelectedEvidenceItem index={index + 1} item={item} key={item.citation.chunk_id ?? item.citation.version_id} />)
          : omitted.map((item) => <OmittedEvidenceItem item={item} key={`${item.version_id}-${item.relative_path}`} />)}
        {tab === "selected" && selected.length === 0 ? <p className="context-digest__empty">No project sources were needed for this request.</p> : null}
        {tab === "omitted" && omitted.length === 0 ? <p className="context-digest__empty">No relevant sources were left out.</p> : null}
      </div>
    </section>
  );
}

interface SelectedEvidenceItemProps {
  item: ContextItem;
  index: number;
}

function SelectedEvidenceItem({ item, index }: SelectedEvidenceItemProps) {
  const citation = item.citation;
  return (
    <details className="evidence-item evidence-item--selected">
      <summary>
        <span className="evidence-item__index">{String(index).padStart(2, "0")}</span>
        <span className="evidence-item__identity">
          <strong>{citation.relative_path}</strong>
          <small>Lines {citation.start_line}–{citation.end_line} · {titleCase(item.kind)}</small>
        </span>
        <Icon className="evidence-item__chevron" name="chevron" size={18} />
      </summary>
      <div className="evidence-item__body">
        <p className="selection-reason"><Icon name="check" size={16} />{item.selection_reason}</p>
        <blockquote>{item.excerpt}</blockquote>
        <details className="technical-disclosure">
          <summary>Ranking and source integrity</summary>
          <div className="citation-strip">
            <span><strong>Version</strong> {citation.version_id}</span>
            <span><strong>Source hash</strong> <code>{citation.sha256}</code></span>
            <span><strong>Excerpt hash</strong> <code>{citation.excerpt_sha256}</code></span>
            <Badge tone={citation.stale ? "warning" : "success"}>{citation.stale ? "Stale" : "Current"}</Badge>
          </div>
          <div className="evidence-item__detail-grid">
            <div>
              <h4>Score explanation · {item.score.total.toFixed(2)}</h4>
              <ScoreBreakdownView score={item.score} />
            </div>
            <div>
              <h4>Protected terms</h4>
              <div className="atom-list">
                {item.protected_atoms.map((atom) => <code key={atom}>{atom}</code>)}
              </div>
            </div>
          </div>
        </details>
      </div>
    </details>
  );
}

interface OmittedEvidenceItemProps {
  item: OmittedContext;
}

function OmittedEvidenceItem({ item }: OmittedEvidenceItemProps) {
  const recovery = parseRecoveryReference(item);
  const [open, setOpen] = useState(false);

  return (
    <article className="evidence-item evidence-item--omitted">
      <span className="evidence-item__index"><Icon name="file" size={17} /></span>
      <div className="evidence-item__identity">
        <strong>{item.relative_path}</strong>
        <p>{item.reason}</p>
        {recovery ? <button className="button button--secondary button--small" onClick={() => setOpen((current) => !current)} type="button">{open ? "Close recovered source" : "Open sanitized source"}</button> : null}
        {open && recovery ? <RecoveredSource resourceId={recovery.resourceId} versionId={recovery.versionId} /> : null}
        <details className="technical-disclosure">
          <summary>Recovery details</summary>
          <div className="citation-strip">
            <span><strong>Version</strong> {item.version_id}</span>
            <span><strong>Estimated size</strong> {item.estimated_tokens} tokens</span>
          </div>
          <code>{item.recoverable_uri}</code>
        </details>
      </div>
    </article>
  );
}

function RecoveredSource({ resourceId, versionId }: { resourceId: string; versionId: string }) {
  const [copied, setCopied] = useState(false);
  const version = useResourceVersion(resourceId, versionId, true);
  const statusMessage = version.isPending
    ? "Recovering sanitized source."
    : version.data
      ? copied ? "Sanitized source copied." : "Sanitized source ready."
      : "";

  async function copyContent() {
    if (!version.data) {
      return;
    }
    try {
      await navigator.clipboard.writeText(version.data.content);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="recovery-preview">
      <p aria-atomic="true" aria-live="polite" className="sr-only" role="status">{statusMessage}</p>
      {version.isPending ? <p>Recovering this local version…</p> : null}
      {version.isError ? <p role="alert">This saved version is unavailable. The active project index was not changed.</p> : null}
      {version.data ? (
        <>
          <div><strong>{version.data.current ? "Current version" : "Historical version"}</strong><span>{version.data.redacted_count} redactions</span></div>
          <pre tabIndex={0}>{version.data.content || "This indexed file is empty."}</pre>
          <button className="button button--secondary button--small" onClick={() => void copyContent()} type="button"><Icon name={copied ? "check" : "copy"} size={16} />{copied ? "Copied source" : "Copy source"}</button>
        </>
      ) : null}
    </div>
  );
}

function parseRecoveryReference(item: OmittedContext): { resourceId: string; versionId: string } | null {
  try {
    const uri = new URL(item.recoverable_uri);
    const segments = uri.pathname.split("/").filter(Boolean);
    if (uri.protocol !== "context-loom:" || uri.hostname !== "resources" || segments.length !== 3 || segments[1] !== "versions") {
      return null;
    }
    const [resourceId, , versionId] = segments;
    if (!resourceId || !versionId || versionId !== item.version_id) {
      return null;
    }
    return { resourceId, versionId };
  } catch {
    return null;
  }
}
