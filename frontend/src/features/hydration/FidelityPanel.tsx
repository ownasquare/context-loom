import type { FidelityReport } from "../../api/types";
import { titleCase } from "../../lib/format";
import { Icon } from "../../components/icons/Icon";
import { Badge } from "../../components/ui/Badge";
import { ProgressBar } from "../../components/ui/ProgressBar";

interface FidelityPanelProps {
  report: FidelityReport;
}

export function FidelityPanel({ report }: FidelityPanelProps) {
  const isHealthy = report.status === "passed";

  return (
    <section aria-labelledby="fidelity-title" className={`fidelity-panel fidelity-panel--${report.status}`}>
      <div className="fidelity-panel__heading">
        <span className="fidelity-panel__icon"><Icon name={isHealthy ? "shield" : "refresh"} /></span>
        <div>
          <p className="eyebrow">Safety checks</p>
          <h3 id="fidelity-title">{isHealthy ? "Message and sources checked" : "A safe fallback was used"}</h3>
        </div>
        <Badge tone={isHealthy ? "success" : "warning"}>{titleCase(report.status)}</Badge>
      </div>

      <div className="gate-grid">
        <GateCheck label="Original message" passed={report.exact_message_preserved} />
        <GateCheck label="Source links" passed={report.citations_valid} />
        <GateCheck label="Current files" passed={report.freshness_valid} />
      </div>

      <details className="technical-disclosure">
        <summary>Review technical checks</summary>
        <div className="fidelity-panel__modes">
          <span>Requested <strong>{titleCase(report.requested_mode)}</strong></span>
          <Icon name="arrow" size={16} />
          <span>Used <strong>{titleCase(report.effective_mode)}</strong></span>
        </div>

        {report.fallback_reason ? <p className="callout callout--warning">{report.fallback_reason}</p> : null}

        <div className="coverage-grid">
          <div>
            <span>Protected terms</span>
            <strong>{Math.round(report.protected_atom_coverage * 100)}%</strong>
            <ProgressBar label="Protected term coverage" tone="success" value={report.protected_atom_coverage} />
          </div>
          <div>
            <span>Named references</span>
            <strong>{Math.round(report.explicit_reference_coverage * 100)}%</strong>
            <ProgressBar label="Named reference coverage" tone="success" value={report.explicit_reference_coverage} />
          </div>
        </div>

        {report.security_overrides.length > 0 ? <TechnicalList label="Security overrides" values={report.security_overrides} /> : null}
        {report.failures.length > 0 ? <TechnicalList label="Failures" values={report.failures} /> : null}
        <p className="replay-id"><span>Replay hash</span><code>{report.replay_hash.slice(0, 14)}…</code></p>
      </details>
    </section>
  );
}

interface TechnicalListProps {
  label: string;
  values: string[];
}

function TechnicalList({ label, values }: TechnicalListProps) {
  return (
    <div className="technical-list">
      <strong>{label}</strong>
      <ul>
        {values.map((value) => <li key={value}>{value}</li>)}
      </ul>
    </div>
  );
}

interface GateCheckProps {
  label: string;
  passed: boolean;
}

function GateCheck({ label, passed }: GateCheckProps) {
  return (
    <span className={passed ? "gate-check gate-check--passed" : "gate-check gate-check--failed"}>
      <Icon name={passed ? "check" : "info"} size={15} />{label}
    </span>
  );
}
