import { Icon } from "../icons/Icon";
import type { IconName } from "../icons/Icon";

export type TokenMetricKind = "projected" | "observed" | "verified";

interface TokenMetricCardProps {
  kind: TokenMetricKind;
  value: number | null;
  detail: string;
  trend?: string;
}

const METRIC_CONTENT: Record<TokenMetricKind, { label: string; qualifier: string; icon: IconName }> = {
  projected: {
    label: "Expected savings",
    qualifier: "Local estimate",
    icon: "token",
  },
  observed: {
    label: "Actual input used",
    qualifier: "Provider report",
    icon: "clock",
  },
  verified: {
    label: "Measured savings",
    qualifier: "Direct comparison",
    icon: "shield",
  },
};

export function TokenMetricCard({ kind, value, detail, trend }: TokenMetricCardProps) {
  const content = METRIC_CONTENT[kind];
  const isUnknown = value === null;

  return (
    <article className={`metric-card metric-card--${kind}`}>
      <div className="metric-card__header">
        <span className="metric-card__icon"><Icon name={content.icon} /></span>
        <span className="metric-card__qualifier">{content.qualifier}</span>
      </div>
      <p className="metric-card__label">{content.label}</p>
      <p className={`metric-card__value${isUnknown ? " metric-card__value--unknown" : ""}`}>
        {isUnknown ? "Unknown" : formatTokenCount(value)}
        {isUnknown ? null : <span> tokens</span>}
      </p>
      <div className="metric-card__footer">
        <p>{detail}</p>
        {trend ? <span className="metric-card__trend">{trend}</span> : null}
      </div>
    </article>
  );
}

export function formatTokenCount(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}
