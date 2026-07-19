import { useEffect, useState } from "react";
import type { TurnSummary } from "../api/types";
import type { RouteId } from "../app/navigation";
import { useThreads } from "../api/queries";
import { useWorkspace } from "../app/workspace";
import { Icon } from "../components/icons/Icon";
import { Badge } from "../components/ui/Badge";
import { PageHeader } from "../components/ui/PageHeader";
import { ProgressBar } from "../components/ui/ProgressBar";
import { StatePanel } from "../components/ui/StatePanel";
import { TokenMetricCard, formatTokenCount } from "../components/ui/TokenMetricCard";
import { ProjectSetup } from "../features/workspaces/ProjectSetup";
import { UsageEntry } from "../features/usage/UsageEntry";
import type { UsageTarget } from "../features/usage/UsageEntry";
import { formatPercent, formatRelativeTime, titleCase } from "../lib/format";

interface ThreadsPageProps {
  onNavigate?: (route: RouteId) => void;
}

export function ThreadsPage({ onNavigate }: ThreadsPageProps = {}) {
  const { selectedWorkspace, selectedWorkspaceId, workspacesQuery } = useWorkspace();
  const threads = useThreads(selectedWorkspaceId);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [showUsage, setShowUsage] = useState(false);
  const selectedThread = threads.data?.find((thread) => thread.thread_id === selectedThreadId) ?? threads.data?.[0] ?? null;
  const usageTargets: UsageTarget[] = selectedThread ? [...selectedThread.history]
    .filter((turn) => !turn.usage_recorded)
    .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
    .map((turn) => ({
      hydrationId: turn.hydration_id,
      label: formatUsageTargetLabel(turn),
    })) : [];
  const usageButtonLabel = usageTargets.length
    ? showUsage ? "Close usage form" : "Add provider usage"
    : selectedThread?.actual_usage_completeness === 1 ? "Usage complete" : "Usage details unavailable";

  useEffect(() => {
    setSelectedThreadId(null);
    setShowUsage(false);
  }, [selectedWorkspaceId]);

  if (workspacesQuery.isPending) {
    return <StatePanel kind="loading" />;
  }

  if (workspacesQuery.isError) {
    return <StatePanel kind="error" onRetry={() => void workspacesQuery.refetch()} />;
  }

  if (!selectedWorkspace) {
    return <ProjectSetup />;
  }

  if (threads.isPending) {
    return <StatePanel description="Loading conversations and their token records." kind="loading" title="Opening savings" />;
  }

  if (threads.isError) {
    return <StatePanel kind="error" onRetry={() => void threads.refetch()} />;
  }

  if (!threads.data.length || !selectedThread) {
    return (
      <div className="page page--threads">
        <PageHeader description="Projected savings appear after you prepare the first message for a conversation." eyebrow={selectedWorkspace.name} title="Savings" />
        <div className="empty-with-action">
          <StatePanel description="Prepare a message and keep its conversation selected to build a lifetime savings record." kind="empty" title="No conversations yet" />
          {onNavigate ? <button className="button button--primary" onClick={() => onNavigate("hydrate")} type="button"><Icon name="threads" size={17} />Prepare your first message</button> : null}
        </div>
      </div>
    );
  }

  return (
    <div className="page page--threads">
      <PageHeader
        description="Compare estimated reductions with provider-reported usage. Unknown values stay unknown until you add trustworthy readback."
        eyebrow={selectedWorkspace.name}
        title="Savings"
      />
      <div className="threads-layout">
        <aside aria-label="Conversations" className="thread-picker card">
          <div className="thread-picker__heading"><div><p className="eyebrow">{threads.data.length} tracked</p><h2>Conversations</h2></div><Icon name="threads" /></div>
          <div className="thread-picker__list">
            {threads.data.map((thread) => (
              <button aria-pressed={selectedThread.thread_id === thread.thread_id} className="thread-choice" key={thread.thread_id} onClick={() => { setSelectedThreadId(thread.thread_id); setShowUsage(false); }} type="button">
                <span className="thread-choice__top"><strong>{displayThreadLabel(thread.label, thread.thread_id)}</strong><span>{formatRelativeTime(thread.updated_at)}</span></span>
                <span className="thread-choice__meta">{thread.turns} {thread.turns === 1 ? "message" : "messages"} <i /> {formatTokenCount(thread.projected_input_tokens_saved)} projected saved</span>
                <ProgressBar label={`${displayThreadLabel(thread.label, thread.thread_id)} provider usage completeness`} value={thread.actual_usage_completeness} />
              </button>
            ))}
          </div>
        </aside>

        <div className="thread-detail">
          <section className="thread-detail__header card">
            <div><p className="eyebrow">Conversation total</p><h2>{displayThreadLabel(selectedThread.label, selectedThread.thread_id)}</h2><span>{selectedThread.turns} {selectedThread.turns === 1 ? "prepared message" : "prepared messages"}</span></div>
            <div className="thread-detail__actions">
              <div className="completeness-meter"><strong>{formatPercent(selectedThread.actual_usage_completeness)}</strong><span>provider usage recorded</span></div>
              <button className="button button--secondary" disabled={usageTargets.length === 0} onClick={() => setShowUsage((current) => !current)} type="button"><Icon name="check" size={17} />{usageButtonLabel}</button>
            </div>
          </section>

          {showUsage && usageTargets.length ? <section className="card"><UsageEntry onRecorded={() => setShowUsage(false)} threadId={selectedThread.thread_id} usageTargets={usageTargets} workspaceId={selectedWorkspaceId} /></section> : null}

          <div className="metric-grid metric-grid--thread">
            <TokenMetricCard detail={`${formatTokenCount(selectedThread.estimated_baseline_input_tokens)} baseline → ${formatTokenCount(selectedThread.estimated_hydrated_input_tokens)} prepared`} kind="projected" value={selectedThread.projected_input_tokens_saved} />
            <TokenMetricCard detail="Input reported by a provider or chat harness" kind="observed" trend={formatPercent(selectedThread.actual_usage_completeness)} value={selectedThread.actual_input_tokens} />
            <TokenMetricCard detail="Measured against an equivalent unprepared request" kind="verified" value={selectedThread.verified_counterfactual_tokens_saved} />
          </div>

          <details className="accounting-card card technical-details">
            <summary>How these totals are calculated</summary>
            <div className="accounting-grid">
              <div><span>Observed output</span><strong>{formatKnownTokens(selectedThread.actual_output_tokens)}</strong></div>
              <div><span>Cached input</span><strong>{formatKnownTokens(selectedThread.cached_input_tokens)}</strong></div>
              <div><span>Local preparation cost</span><strong>{formatTokenCount(selectedThread.local_compactor_tokens)} tokens</strong></div>
              <div><span>Estimate-adjusted reduction</span><strong>{formatKnownTokens(selectedThread.baseline_estimate_adjusted_reduction)}</strong></div>
            </div>
            <p className="metric-disclaimer">Projected, provider-observed, and verified values are intentionally separate. Missing readback is never counted as zero.</p>
            <code>{selectedThread.thread_id}</code>
          </details>

          <section aria-labelledby="turn-history-title" className="turn-history card">
            <div className="turn-history__heading"><div><p className="eyebrow">Recent messages</p><h3 id="turn-history-title">Conversation activity</h3></div><span>{selectedThread.history.length} retained summaries</span></div>
            {selectedThread.history.length ? <div className="timeline">{selectedThread.history.map((turn) => <TurnRow key={turn.hydration_id} turn={turn} />)}</div> : <StatePanel compact description="The conversation total exists, but no per-message summaries are available." kind="empty" title="No activity details" />}
          </section>
        </div>
      </div>
    </div>
  );
}

interface TurnRowProps {
  turn: TurnSummary;
}

function TurnRow({ turn }: TurnRowProps) {
  const tone = turn.fidelity_status === "passed" ? "success" : turn.fidelity_status === "fallback" ? "warning" : "danger";
  return (
    <article className="timeline-entry">
      <span aria-hidden="true" className="timeline-entry__pin" />
      <div className="timeline-entry__identity"><strong>{formatRelativeTime(turn.created_at)}</strong><span>{titleCase(turn.adapter)} · {displayMode(turn.effective_mode)}</span></div>
      <div className="timeline-entry__metric"><span>Projected saved</span><strong>{formatTokenCount(turn.projected_input_tokens_saved)}</strong></div>
      <div className="timeline-entry__metric"><span>Provider input</span><strong>{formatKnownTokens(turn.actual_input_tokens)}</strong></div>
      <div className="timeline-entry__metric"><span>Verified saved</span><strong>{formatKnownTokens(turn.verified_counterfactual_tokens_saved)}</strong></div>
      <Badge tone={tone}>{turn.fidelity_status === "passed" ? "Checked" : titleCase(turn.fidelity_status)}</Badge>
      <details><summary>Technical ID</summary><code>{turn.hydration_id}</code></details>
    </article>
  );
}

function formatKnownTokens(value: number | null): string {
  return value === null ? "Unknown" : `${formatTokenCount(value)} tokens`;
}

function displayThreadLabel(label: string, id: string): string {
  if (label && label !== id) {
    return label;
  }
  const readable = id.replace(/^thread-/, "").replace(/[-_]+/g, " ").trim();
  if (!readable || /^[0-9a-f]{8,}$/i.test(readable.replaceAll(" ", ""))) {
    return "Untitled conversation";
  }
  return readable.charAt(0).toUpperCase() + readable.slice(1);
}

export function formatUsageTargetLabel(turn: TurnSummary): string {
  return `${formatRelativeTime(turn.created_at)} · ${titleCase(turn.adapter)} · ${formatTokenCount(turn.projected_input_tokens_saved)} projected saved · ID ${shortHydrationIdentifier(turn.hydration_id)}`;
}

function shortHydrationIdentifier(hydrationId: string): string {
  if (hydrationId.length <= 18) {
    return hydrationId;
  }
  return `${hydrationId.slice(0, 8)}…${hydrationId.slice(-6)}`;
}

function displayMode(mode: TurnSummary["effective_mode"]): string {
  const labels: Record<TurnSummary["effective_mode"], string> = {
    compact_aggressive: "Compact",
    hybrid_safe: "Balanced",
    passthrough: "Original message only",
    strict_extractive: "Source excerpts only",
  };
  return labels[mode];
}
