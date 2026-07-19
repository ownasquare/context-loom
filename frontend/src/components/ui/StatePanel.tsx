import { Icon } from "../icons/Icon";

type StatePanelKind = "loading" | "empty" | "error";

interface StatePanelProps {
  kind: StatePanelKind;
  title?: string;
  description?: string;
  onRetry?: () => void;
  compact?: boolean;
}

const DEFAULTS: Record<StatePanelKind, { title: string; description: string }> = {
  loading: {
    title: "Loading local data…",
    description: "Reading the current project state.",
  },
  empty: {
    title: "Nothing here yet",
    description: "Connect a project or prepare the first message to populate this view.",
  },
  error: {
    title: "Local service unavailable",
    description: "Context Loom could not read this view. Your workspace files were not changed.",
  },
};

export function StatePanel({ kind, title, description, onRetry, compact = false }: StatePanelProps) {
  const content = DEFAULTS[kind];

  if (kind === "loading") {
    return (
      <div aria-busy="true" aria-live="polite" className={`state-panel state-panel--loading${compact ? " state-panel--compact" : ""}`}>
        <div aria-hidden="true" className="loom-loader">
          <span />
          <span />
          <span />
        </div>
        <div>
          <h3>{title ?? content.title}</h3>
          <p>{description ?? content.description}</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`state-panel state-panel--${kind}${compact ? " state-panel--compact" : ""}`} role={kind === "error" ? "alert" : "status"}>
      <span className="state-panel__icon"><Icon name={kind === "error" ? "refresh" : "layers"} /></span>
      <div>
        <h3>{title ?? content.title}</h3>
        <p>{description ?? content.description}</p>
      </div>
      {onRetry ? (
        <button className="button button--secondary button--small" onClick={onRetry} type="button">
          Try again
        </button>
      ) : null}
    </div>
  );
}
