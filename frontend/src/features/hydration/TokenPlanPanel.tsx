import type { TokenPlan } from "../../api/types";
import { formatTokenCount } from "../../components/ui/TokenMetricCard";
import { Icon } from "../../components/icons/Icon";

interface TokenPlanPanelProps {
  plan: TokenPlan;
}

export function TokenPlanPanel({ plan }: TokenPlanPanelProps) {
  const hydratedRatio = plan.baseline.tokens === 0 ? 0 : plan.hydrated.tokens / plan.baseline.tokens;

  return (
    <section aria-labelledby="token-plan-title" className="token-plan card">
      <div className="token-plan__heading">
        <div>
          <p className="eyebrow">Estimated savings</p>
          <h3 id="token-plan-title">Request size</h3>
        </div>
        <span className="savings-orbit">−{plan.projected_reduction_percent}%</span>
      </div>
      <div className="token-plan__numbers">
        <div>
          <span>Without preparation</span>
          <strong>{formatTokenCount(plan.baseline.tokens)}</strong>
        </div>
        <Icon name="arrow" />
        <div>
          <span>Prepared request</span>
          <strong>{formatTokenCount(plan.hydrated.tokens)}</strong>
        </div>
      </div>
      <div className="budget-rail" title={`${Math.round(hydratedRatio * 100)}% of baseline retained`}>
        <span className="budget-rail__hydrated" style={{ width: `${Math.max(hydratedRatio * 100, 1)}%` }} />
      </div>
      <div className="token-plan__saved">
        <span><Icon name="token" size={17} />Estimated input saved</span>
        <strong>{formatTokenCount(plan.projected_input_tokens_saved)} tokens</strong>
      </div>
      <p className="metric-disclaimer">This is a local estimate, not usage reported by a model provider.</p>
      <details className="technical-disclosure">
        <summary>How this estimate was calculated</summary>
        <p className="metric-disclaimer">
          Baseline: {plan.baseline.method.replaceAll("_", " ")} ({Math.round(plan.baseline.confidence * 100)}% confidence).
          Prepared request: {plan.hydrated.method.replaceAll("_", " ")} ({Math.round(plan.hydrated.confidence * 100)}% confidence).
          Answer reserve: {formatTokenCount(plan.reserved_output_tokens)} tokens.
          Local helper input/output: {formatTokenCount(plan.local_compactor_input_tokens)} / {formatTokenCount(plan.local_compactor_output_tokens)} tokens.
        </p>
      </details>
    </section>
  );
}
