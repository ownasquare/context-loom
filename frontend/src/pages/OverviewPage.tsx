import { useMemo } from "react";
import type { RouteId } from "../app/navigation";
import type { ThreadSummary } from "../api/types";
import { useThreads, useWorkspaceStatus } from "../api/queries";
import { useWorkspace } from "../app/workspace";
import { Icon } from "../components/icons/Icon";
import { Badge } from "../components/ui/Badge";
import { InfoTip } from "../components/ui/InfoTip";
import { PageHeader } from "../components/ui/PageHeader";
import { ProgressBar } from "../components/ui/ProgressBar";
import { StatePanel } from "../components/ui/StatePanel";
import { ProjectSetup } from "../features/workspaces/ProjectSetup";
import { formatCompactNumber, formatPercent, formatRelativeTime } from "../lib/format";

interface OverviewPageProps {
  onNavigate: (route: RouteId) => void;
}

export interface ThreadTotals {
  projected: number;
  observed: number | null;
  verified: number | null;
  completeness: number;
}

export function OverviewPage({ onNavigate }: OverviewPageProps) {
  const { selectedWorkspace, selectedWorkspaceId, workspacesQuery } = useWorkspace();
  const status = useWorkspaceStatus(selectedWorkspaceId);
  const threads = useThreads(selectedWorkspaceId);
  const totals = useMemo(() => summarizeThreads(threads.data ?? []), [threads.data]);

  if (workspacesQuery.isPending) {
    return <StatePanel kind="loading" />;
  }

  if (workspacesQuery.isError) {
    return <StatePanel kind="error" onRetry={() => void workspacesQuery.refetch()} />;
  }

  if (!selectedWorkspace) {
    return (
      <div className="page page--welcome">
        <ProjectSetup />
        <section className="welcome-notes" aria-label="What happens next">
          <div><Icon name="shield" /><strong>Private by default</strong><span>Secrets and unsafe files are excluded before indexing.</span></div>
          <div><Icon name="search" /><strong>Focused context</strong><span>Only relevant, cited sections are attached to each message.</span></div>
          <div><Icon name="token" /><strong>Honest savings</strong><span>Estimates and provider-reported usage stay clearly separated.</span></div>
        </section>
      </div>
    );
  }

  return (
    <div className="page page--overview">
      <PageHeader
        action={<button className="button button--primary button--large" onClick={() => onNavigate("hydrate")} type="button"><Icon name="threads" />Prepare a message</button>}
        description="Scan for changes, prepare a message with focused project context, and keep a trustworthy record of token savings."
        eyebrow="Project home"
        title={selectedWorkspace.name}
      />

      {status.isPending ? (
        <section aria-label="Project status" className="project-status card">
          <StatePanel compact description="Reading the latest scan and file counts." kind="loading" title="Checking project status" />
        </section>
      ) : status.isError ? (
        <section aria-label="Project status" className="project-status card">
          <StatePanel
            compact
            description="Context Loom could not read this project's scan status. No files were changed."
            kind="error"
            onRetry={() => void status.refetch()}
            title="Project status unavailable"
          />
        </section>
      ) : (
        <section aria-labelledby="project-status-title" className="project-status card">
          <div className="project-status__heading">
            <div>
              <p className="eyebrow">Current project</p>
              <h2 id="project-status-title">{status.data.active_generation_id ? "Ready to prepare messages" : "First scan needed"}</h2>
            </div>
            <Badge dot tone={status.data.active_generation_id ? "success" : "warning"}>{status.data.active_generation_id ? "Ready" : "Not scanned"}</Badge>
          </div>
          <div className="project-status__facts">
            <div><span>Files available</span><strong>{formatCompactNumber(status.data.indexed_resources)}</strong></div>
            <div><span>Searchable sections</span><strong>{formatCompactNumber(status.data.indexed_chunks)}</strong></div>
            <div><span>Last scan</span><strong>{formatRelativeTime(status.data.workspace.last_sync_at)}</strong></div>
            <div><span>Excluded last scan</span><strong>{status.data.last_sync?.excluded ?? 0}</strong></div>
          </div>
          <details className="technical-details">
            <summary>Project details</summary>
            <code className="workspace-path">{selectedWorkspace.root_path}</code>
            {status.data.last_sync ? <p>{status.data.last_sync.added} added · {status.data.last_sync.modified} changed · {status.data.last_sync.deleted} removed · {status.data.last_sync.redacted} redacted</p> : <p>No completed scan is recorded yet.</p>}
          </details>
        </section>
      )}

      <section aria-labelledby="lifetime-title" className="home-section home-savings card">
        <div className="section-heading-inline">
          <div><p className="eyebrow">Across this project</p><h2 id="lifetime-title">Estimated tokens avoided</h2></div>
          <button className="text-button" onClick={() => onNavigate("threads")} type="button">View details <Icon name="arrow" size={15} /></button>
        </div>
        {threads.isPending ? (
          <StatePanel compact description="Loading conversation totals and provider usage records." kind="loading" title="Opening token savings" />
        ) : threads.isError ? (
          <StatePanel
            compact
            description="Context Loom could not read token savings for this project. Missing data has not been counted as zero."
            kind="error"
            onRetry={() => void threads.refetch()}
            title="Token savings unavailable"
          />
        ) : (
          <div className="home-savings__summary">
            <span className="home-savings__icon"><Icon name="token" /></span>
            <div className="home-savings__value">
              <strong>{formatCompactNumber(totals.projected)}</strong>
              <span>local estimate across prepared messages</span>
            </div>
            <div className="home-savings__coverage">
              <span>Provider usage captured <InfoTip label="Provider usage captured">The share of prepared messages with token totals imported from a chat provider. Missing usage stays unknown, never zero.</InfoTip></span>
              <strong>{formatPercent(totals.completeness)}</strong>
              <ProgressBar label="Provider usage completeness" value={totals.completeness} />
            </div>
          </div>
        )}
      </section>

      <section aria-labelledby="recent-title" className="recent-card home-section card">
          <div className="recent-card__heading"><div><p className="eyebrow">Recent work</p><h2 id="recent-title">Conversations</h2></div><button className="text-button" onClick={() => onNavigate("threads")} type="button">View all <Icon name="arrow" size={15} /></button></div>
          {threads.isPending ? (
            <StatePanel compact description="Loading recent conversation activity." kind="loading" title="Opening conversations" />
          ) : threads.isError ? (
            <StatePanel
              compact
              description="Context Loom could not read recent conversations. Try again without leaving this page."
              kind="error"
              onRetry={() => void threads.refetch()}
              title="Conversations unavailable"
            />
          ) : (threads.data ?? []).length ? (
            <>
              <div className="recent-threads">
                {(threads.data ?? []).slice(0, 4).map((thread) => (
                  <article className="recent-thread" key={thread.thread_id}>
                    <span className="recent-thread__icon"><Icon name="threads" size={18} /></span>
                    <div><strong>{displayThreadLabel(thread)}</strong><span>{thread.turns} {thread.turns === 1 ? "message" : "messages"} · {formatRelativeTime(thread.updated_at)}</span></div>
                    <div className="recent-thread__saving"><strong>{formatCompactNumber(thread.projected_input_tokens_saved)}</strong><span>projected saved</span></div>
                  </article>
                ))}
              </div>
              <div className="completeness-row"><span>Provider usage recorded</span><strong>{formatPercent(totals.completeness)}</strong></div>
              <ProgressBar label="Provider usage completeness" value={totals.completeness} />
            </>
          ) : <StatePanel compact description="Prepare the first message to start a conversation and savings record." kind="empty" title="No conversations yet" />}
      </section>
    </div>
  );
}

export function summarizeThreads(threads: ThreadSummary[]): ThreadTotals {
  let projected = 0;
  let observed = 0;
  let observedKnown = false;
  let verified = 0;
  let verifiedKnown = false;
  let observedTurns = 0;
  let totalTurns = 0;

  for (const thread of threads) {
    projected += thread.projected_input_tokens_saved;
    observedTurns += thread.actual_usage_completeness * thread.turns;
    totalTurns += thread.turns;
    if (thread.actual_input_tokens !== null) {
      observed += thread.actual_input_tokens;
      observedKnown = true;
    }
    if (thread.verified_counterfactual_tokens_saved !== null) {
      verified += thread.verified_counterfactual_tokens_saved;
      verifiedKnown = true;
    }
  }

  return {
    projected,
    observed: observedKnown ? observed : null,
    verified: verifiedKnown ? verified : null,
    completeness: totalTurns === 0 ? 0 : observedTurns / totalTurns,
  };
}

function displayThreadLabel(thread: ThreadSummary): string {
  return thread.label && thread.label !== thread.thread_id ? thread.label : "Untitled conversation";
}
