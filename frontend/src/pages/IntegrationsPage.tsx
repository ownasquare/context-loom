import { useAdapters } from "../api/queries";
import { Icon } from "../components/icons/Icon";
import { Badge } from "../components/ui/Badge";
import { InfoTip } from "../components/ui/InfoTip";
import { PageHeader } from "../components/ui/PageHeader";
import { StatePanel } from "../components/ui/StatePanel";

export function IntegrationsPage() {
  const adapters = useAdapters();

  if (adapters.isPending) {
    return <StatePanel kind="loading" />;
  }

  if (adapters.isError) {
    return <StatePanel kind="error" onRetry={() => void adapters.refetch()} />;
  }

  return (
    <div className="page page--integrations">
      <PageHeader
        description="Start with copy and paste, or connect a chat tool through MCP or the local API."
        eyebrow="Manage"
        title="Connections"
      />
      <section aria-labelledby="connection-methods-title" className="adapter-section">
        <div className="adapter-section__heading"><div><p className="eyebrow">Choose one</p><h2 id="connection-methods-title">Connection methods</h2></div><p>Copy and paste works everywhere and needs no setup.</p></div>
        <div className="connection-method-grid">
          <article className="connection-method card connection-method--recommended">
            <div className="connection-method__heading"><span className="adapter-card__icon"><Icon name="copy" /></span><Badge tone="accent">Recommended</Badge></div>
            <h3>Copy and paste</h3>
            <p>Prepare a request, review it, and paste it into any chat tool. Nothing is connected and no credentials are needed.</p>
            <div className="connection-method__steps"><span>1. Prepare</span><span>2. Copy</span><span>3. Paste</span></div>
          </article>
          <article className="connection-method card">
            <div className="connection-method__heading"><span className="adapter-card__icon"><Icon name="network" /></span><Badge tone="neutral">Optional</Badge></div>
            <div className="connection-method__title"><h3>MCP connection</h3><InfoTip label="MCP connection">MCP lets a compatible chat harness call Context Loom's local tools. The harness still needs its own configuration.</InfoTip></div>
            <p>Let Codex, Claude, Cursor, or Copilot request prepared context from the local MCP server.</p>
            <details className="connection-setup"><summary>View setup <Icon name="chevron" size={16} /></summary><div><p>Generate a reviewed config snippet with the detected executable path. The preview never edits harness settings.</p><code>context-loom adapter preview codex</code><a href="https://github.com/ownasquare/context-loom/blob/main/docs/harness-integrations.md#2-mcp-connection">Open harness setup guide</a></div></details>
          </article>
          <article className="connection-method card">
            <div className="connection-method__heading"><span className="adapter-card__icon"><Icon name="terminal" /></span><Badge tone="neutral">Developers</Badge></div>
            <h3>Local API</h3>
            <p>Integrate through the loopback FastAPI service when your tool can make local HTTP requests.</p>
            <details className="connection-setup"><summary>View endpoint <Icon name="chevron" size={16} /></summary><div><p>Create and review a prepared request locally. Outbound provider forwarding stays separately opt-in.</p><code>POST {localOrigin()}/api/v1/hydrations</code><a href="https://github.com/ownasquare/context-loom/blob/main/docs/api.md">Open API guide</a></div></details>
          </article>
        </div>
      </section>
      <details className="output-formats card">
        <summary>Advanced output formats <Icon name="chevron" size={16} /></summary>
        <div><p>Choose these on the Prepare page when another program expects a specific JSON or Markdown shape.</p><div className="output-format-list">{adapters.data.map((adapter) => <span key={adapter.id}><strong>{adapter.display_name}</strong><small>{adapter.formats.join(" · ")}</small></span>)}</div><p className="output-format-note">Provider-shaped output only — not a connection installer.</p></div>
      </details>
    </div>
  );
}

function localOrigin(): string {
  return window.location.origin === "null" ? "http://127.0.0.1:8768" : window.location.origin;
}
