import { useState } from "react";
import type { HydrationResponse, RenderedPrompt } from "../../api/types";
import { Icon } from "../../components/icons/Icon";
import { Badge } from "../../components/ui/Badge";
import { EvidenceList } from "./EvidenceList";
import { FidelityPanel } from "./FidelityPanel";
import { TokenPlanPanel } from "./TokenPlanPanel";

interface HydrationInspectorProps {
  response: HydrationResponse;
}

type CopyStatus = "idle" | "copied" | "failed";

export function HydrationInspector({ response }: HydrationInspectorProps) {
  const { envelope, rendered } = response;
  const [copyStatus, setCopyStatus] = useState<CopyStatus>("idle");
  const renderedPayload = serializeRenderedPayload(rendered);
  const destination = displayAdapter(rendered.adapter);
  const sourceCount = envelope.context_items.length;

  async function copyEnvelope() {
    try {
      await navigator.clipboard.writeText(renderedPayload);
      setCopyStatus("copied");
      window.setTimeout(() => setCopyStatus("idle"), 1_800);
    } catch {
      setCopyStatus("failed");
    }
  }

  function downloadEnvelope() {
    const blob = new Blob([JSON.stringify(envelope, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${envelope.hydration_id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="inspector" data-testid="hydration-inspector">
      <section aria-labelledby="prepared-request-title" className="prepared-output message-proof card" id="prepared-request-result" tabIndex={-1}>
        <div className="inspector__toolbar">
          <div>
            <p className="eyebrow">Ready to use</p>
            <h2 id="prepared-request-title">Prepared request</h2>
            <p className="prepared-output__summary">{sourceCount} project {sourceCount === 1 ? "source" : "sources"} included · Exact wording preserved</p>
          </div>
          <div className="inspector__actions">
            <Badge dot tone="success">Format: {destination}</Badge>
            <button className="button button--primary" onClick={() => void copyEnvelope()} type="button">
              <Icon name={copyStatus === "copied" ? "check" : "copy"} size={17} />
              {copyStatus === "copied" ? "Copied" : copyStatus === "failed" ? "Copy unavailable" : "Copy prepared request"}
            </button>
          </div>
        </div>
        <p aria-atomic="true" aria-live="polite" className={`copy-guidance${copyStatus === "copied" ? " copy-guidance--success" : ""}`} role="status">
          {copyStatus === "copied"
            ? `Copied — paste it into ${destination} when ready.`
            : copyStatus === "failed"
              ? "Copy was unavailable. Open the full request and select it manually."
              : `Nothing is sent automatically. Copy, review, then paste into ${destination}.`}
        </p>
        <details className="payload-disclosure">
          <summary>Review full prepared request <Icon name="chevron" size={16} /></summary>
          <pre data-testid="rendered-payload">{renderedPayload}</pre>
        </details>
      </section>

      <div className="inspector__audit-grid">
        <FidelityPanel report={envelope.fidelity} />
        <TokenPlanPanel plan={envelope.token_plan} />
      </div>

      <EvidenceList omitted={envelope.omitted_context} selected={envelope.context_items} />

      <details className="technical-disclosure advanced-settings">
        <summary>Message integrity and technical details</summary>
        <div className="inspector__grid">
          <section aria-labelledby="exact-message-title" className="message-proof card">
            <div className="message-proof__heading">
              <div>
                <p className="eyebrow">Original input</p>
                <h3 id="exact-message-title">Exact message</h3>
              </div>
              <span className="byte-proof"><Icon name="check" size={14} />Byte-preserved</span>
            </div>
            <pre data-testid="exact-message">{envelope.message_exact}</pre>
          </section>

          <section aria-labelledby="context-digest-title" className="context-digest card">
            <div className="context-digest__heading">
              <div>
                <p className="eyebrow">Local context</p>
                <h3 id="context-digest-title">Context digest</h3>
              </div>
              <span>{envelope.context_items.length} cited excerpts</span>
            </div>
            {envelope.context_digest ? <pre>{envelope.context_digest}</pre> : <p className="context-digest__empty">No compacted context was attached because the original-message-only option was used.</p>}
          </section>
        </div>
        <div className="inspector__actions">
          <button className="button button--secondary" onClick={downloadEnvelope} type="button"><Icon name="download" size={17} />Download JSON envelope</button>
        </div>
      </details>
    </div>
  );
}

function serializeRenderedPayload(rendered: RenderedPrompt): string {
  return typeof rendered.payload === "string"
    ? rendered.payload
    : JSON.stringify(rendered.payload, null, 2);
}

function displayAdapter(adapter: string): string {
  const labels: Record<string, string> = {
    anthropic_messages: "Anthropic",
    claude: "Claude",
    codex: "Codex",
    copilot: "GitHub Copilot",
    cursor: "Cursor",
    gemini_contents: "Gemini",
    generic_json: "your chat tool",
    generic_markdown: "your chat tool",
    openai_chat: "OpenAI-compatible chat",
    openai_responses: "OpenAI Responses",
  };
  return labels[adapter] ?? adapter.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}
