import { useHealth, useReadiness } from "../api/queries";
import { Icon } from "../components/icons/Icon";
import { Badge } from "../components/ui/Badge";
import { PageHeader } from "../components/ui/PageHeader";
import { StatePanel } from "../components/ui/StatePanel";
import { ThemeControl } from "../components/ui/ThemeControl";
import { titleCase } from "../lib/format";

export function SettingsPage() {
  const health = useHealth();
  const readiness = useReadiness();
  const retentionEnabled = health.data?.retain_message_content;
  const outboundEnabled = health.data?.outbound_allowed;

  return (
    <div className="page page--settings">
      <PageHeader
        description="Manage appearance and review what the local service stores, excludes, and can connect to."
        eyebrow="Manage"
        title="Settings"
      />
      <div className="settings-layout">
        <section aria-labelledby="appearance-title" className="settings-card card">
          <div className="settings-card__heading"><span><Icon name="sun" /></span><div><p className="eyebrow">Display</p><h2 id="appearance-title">Appearance</h2></div></div>
          <p>Follow your system automatically or choose a fixed palette. Theme, current project ID, and conversation names are the only preferences kept in browser storage.</p>
          <ThemeControl />
        </section>

        <section aria-labelledby="runtime-title" className="settings-card card">
          <div className="settings-card__heading"><span><Icon name="database" /></span><div><p className="eyebrow">Service health</p><h2 id="runtime-title">Local runtime</h2></div></div>
          {health.isPending ? <StatePanel compact kind="loading" /> : null}
          {health.isError ? <StatePanel compact kind="error" onRetry={() => void health.refetch()} /> : null}
          {health.data ? (
            <dl className="settings-list">
              <div><dt>Context Loom</dt><dd><Badge dot tone={health.data.status === "ok" ? "success" : "warning"}>{titleCase(health.data.status)}</Badge><span>v{health.data.version}</span></dd></div>
              <div><dt>SQLite / WAL</dt><dd><Badge tone={health.data.database === "ready" ? "success" : "danger"}>{titleCase(health.data.database)}</Badge></dd></div>
              <div><dt>Local model</dt><dd><Badge tone={readiness.data?.local_model === "available" ? "accent" : "neutral"}>{titleCase(readiness.data?.local_model ?? health.data.local_model)}</Badge></dd></div>
              <div><dt>Outbound network</dt><dd><Badge tone={health.data.outbound_allowed ? "warning" : "success"}>{health.data.outbound_allowed ? "Opted in" : "Blocked"}</Badge></dd></div>
            </dl>
          ) : null}
          {readiness.isError ? <StatePanel compact description="The service is running, but its migration and local-helper readiness could not be confirmed." kind="error" onRetry={() => void readiness.refetch()} title="Readiness check failed" /> : null}
        </section>

        <section aria-labelledby="privacy-title" className="settings-card settings-card--wide card">
          <div className="settings-card__heading"><span><Icon name="shield" /></span><div><p className="eyebrow">Data boundary</p><h2 id="privacy-title">Privacy controls</h2></div><Badge dot tone={retentionEnabled ? "warning" : retentionEnabled === false ? "success" : "neutral"}>{retentionEnabled ? "Message retention on" : retentionEnabled === false ? "Default privacy" : "Checking"}</Badge></div>
          <div className="privacy-grid">
            <PrivacyItem icon="file" title="Sensitive-file controls" description="Configured secret files, private keys, binaries, dependency trees, and unsafe symlinks are excluded. Recognized credential patterns are redacted before indexing." />
            <PrivacyItem icon="threads" title="Prompt storage" description={retentionEnabled ? "Exact messages and prepared envelopes are retained in private local state because retention is enabled." : retentionEnabled === false ? "Exact messages and prepared envelopes are not durably stored by the local service." : "Checking the local service retention setting."} />
            <PrivacyItem icon="network" title={outboundEnabled ? "Network opt-in enabled" : outboundEnabled === false ? "Network denied by default" : "Network policy"} description={outboundEnabled ? "The local service may use an explicitly requested local-helper or forwarding path. Review each request before sending." : outboundEnabled === false ? "Preparation stays local unless both the service and an individual request explicitly opt into another path." : "Checking the local service network setting."} />
          </div>
        </section>

        <section aria-labelledby="retention-title" className="settings-card settings-card--wide card">
          <div className="settings-card__heading"><span><Icon name="clock" /></span><div><p className="eyebrow">Local storage</p><h2 id="retention-title">Retention and rebuilding</h2></div></div>
          <div className="retention-row"><div><strong>Versioned local index</strong><span>Sanitized content-addressed objects and SQLite metadata</span></div><Badge tone="info">Authoritative local state</Badge></div>
          <div className="retention-row"><div><strong>Exact message and envelope retention</strong><span>Controlled by the local service, not by this browser</span></div><Badge tone={retentionEnabled ? "warning" : retentionEnabled === false ? "success" : "neutral"}>{retentionEnabled ? "Retained locally" : retentionEnabled === false ? "Not retained" : "Checking"}</Badge></div>
          <div className="retention-row"><div><strong>FTS, embeddings, exports, and this UI</strong><span>Derived artifacts that can be rebuilt from current local resources</span></div><Badge tone="neutral">Rebuildable</Badge></div>
        </section>
      </div>
    </div>
  );
}

interface PrivacyItemProps {
  icon: "file" | "threads" | "network";
  title: string;
  description: string;
}

function PrivacyItem({ icon, title, description }: PrivacyItemProps) {
  return <article><span><Icon name={icon} /></span><div><h3>{title}</h3><p>{description}</p></div></article>;
}
