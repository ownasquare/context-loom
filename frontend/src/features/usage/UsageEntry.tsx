import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError } from "../../api/ApiError";
import { useRecordUsage } from "../../api/queries";
import { Icon } from "../../components/icons/Icon";

interface UsageEntryProps {
  threadId: string;
  workspaceId: string;
  usageTargets: readonly UsageTarget[];
  onRecorded?: () => void;
}

export interface UsageTarget {
  hydrationId: string;
  label: string;
}

export function UsageEntry({ threadId, workspaceId, usageTargets, onRecorded }: UsageEntryProps) {
  const recordUsage = useRecordUsage(workspaceId);
  const [selectedHydrationId, setSelectedHydrationId] = useState(usageTargets[0]?.hydrationId ?? "");
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [inputTokens, setInputTokens] = useState("");
  const [outputTokens, setOutputTokens] = useState("");
  const [cachedTokens, setCachedTokens] = useState("");
  const [verifiedBaseline, setVerifiedBaseline] = useState("");
  const [saved, setSaved] = useState(false);
  const valid = selectedHydrationId.length > 0 && provider.trim().length > 0 && model.trim().length > 0 && inputTokens.length > 0;

  useEffect(() => {
    if (!usageTargets.some((target) => target.hydrationId === selectedHydrationId)) {
      setSelectedHydrationId(usageTargets[0]?.hydrationId ?? "");
    }
  }, [selectedHydrationId, usageTargets]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!valid || recordUsage.isPending) {
      return;
    }
    setSaved(false);
    try {
      await recordUsage.mutateAsync({
        idempotency_key: createIdempotencyKey(),
        thread_id: threadId,
        hydration_id: selectedHydrationId,
        provider: provider.trim(),
        model: model.trim(),
        counting_method: "provider_observed",
        actual_input_tokens: optionalNumber(inputTokens),
        actual_output_tokens: optionalNumber(outputTokens),
        cached_input_tokens: optionalNumber(cachedTokens),
        reasoning_tokens: null,
        local_input_tokens: null,
        local_output_tokens: null,
        billable_input_tokens: null,
        billable_output_tokens: null,
        verified_baseline_input_tokens: optionalNumber(verifiedBaseline),
        provider_request_id_hash: null,
      });
      setSaved(true);
      onRecorded?.();
    } catch {
      setSaved(false);
    }
  }

  return (
    <form className="usage-entry" onSubmit={(event) => void submit(event)}>
      <div className="usage-entry__heading">
        <div><p className="eyebrow">Optional readback</p><h3>Record provider usage</h3></div>
        <span>Missing values remain unknown</span>
      </div>
      <div className="usage-entry__grid">
        <label className="field-group usage-entry__target"><span className="field-label">Prepared message</span><select aria-label="Prepared message" onChange={(event) => setSelectedHydrationId(event.target.value)} value={selectedHydrationId}>{usageTargets.map((target) => <option key={target.hydrationId} value={target.hydrationId}>{target.label}</option>)}</select></label>
        <label className="field-group"><span className="field-label">Provider</span><input aria-label="Provider" autoComplete="off" onChange={(event) => setProvider(event.target.value)} placeholder="OpenAI" value={provider} /></label>
        <label className="field-group"><span className="field-label">Model</span><input aria-label="Model" autoComplete="off" onChange={(event) => setModel(event.target.value)} placeholder="gpt-5" value={model} /></label>
        <label className="field-group"><span className="field-label">Input tokens</span><input aria-label="Input tokens" min="0" onChange={(event) => setInputTokens(event.target.value)} required type="number" value={inputTokens} /></label>
      </div>
      <details className="advanced-settings">
        <summary>More usage fields</summary>
        <div className="usage-entry__grid">
          <label className="field-group"><span className="field-label">Output tokens</span><input min="0" onChange={(event) => setOutputTokens(event.target.value)} type="number" value={outputTokens} /></label>
          <label className="field-group"><span className="field-label">Cached input tokens</span><input min="0" onChange={(event) => setCachedTokens(event.target.value)} type="number" value={cachedTokens} /></label>
          <label className="field-group"><span className="field-label">Measured unprepared baseline</span><input min="0" onChange={(event) => setVerifiedBaseline(event.target.value)} type="number" value={verifiedBaseline} /></label>
        </div>
      </details>
      <div className="usage-entry__footer">
        <p aria-live="polite" className={recordUsage.isError ? "form-message form-message--error" : "form-message"}>
          {recordUsage.isError ? publicError(recordUsage.error) : saved ? "Usage saved" : "Enter the counts reported by your provider or chat harness."}
        </p>
        <button className="button button--secondary" disabled={!valid || recordUsage.isPending} type="submit">
          {recordUsage.isPending ? <span aria-hidden="true" className="button-spinner" /> : <Icon name="check" size={17} />}
          {recordUsage.isPending ? "Saving…" : "Save usage"}
        </button>
      </div>
    </form>
  );
}

function optionalNumber(value: string): number | null {
  return value === "" ? null : Number(value);
}

function createIdempotencyKey(): string {
  return typeof crypto.randomUUID === "function" ? `usage-${crypto.randomUUID()}` : `usage-${Date.now()}`;
}

function publicError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.requestId ? `${error.message} (request ${error.requestId})` : error.message;
  }
  return "Usage could not be saved. Check the values and try again.";
}
