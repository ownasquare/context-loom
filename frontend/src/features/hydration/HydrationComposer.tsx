import { useState } from "react";
import type { FormEvent } from "react";
import type { CompactionMode, HydrateRequest } from "../../api/types";
import { Icon } from "../../components/icons/Icon";
import { InfoTip } from "../../components/ui/InfoTip";
import { ConversationSelector, useProjectConversation } from "../conversations/ConversationSelector";
import type { ProjectConversationSelection } from "../conversations/ConversationSelector";

interface HydrationComposerProps {
  workspaceId: string;
  isPending: boolean;
  onDraftChange?: () => void;
  onSubmit: (request: HydrateRequest) => Promise<void>;
  initialMessage?: string;
}

export function HydrationComposer({ workspaceId, isPending, onDraftChange, onSubmit, initialMessage = "" }: HydrationComposerProps) {
  const [message, setMessage] = useState(initialMessage);
  const [mode, setMode] = useState<CompactionMode>("hybrid_safe");
  const [adapter, setAdapter] = useState("codex");
  const [maxInputTokens, setMaxInputTokens] = useState(4_000);
  const [reserveOutputTokens, setReserveOutputTokens] = useState(800);
  const [useLocalModel, setUseLocalModel] = useState(false);
  const [messageTouched, setMessageTouched] = useState(false);
  const conversationSelection = useProjectConversation(workspaceId);
  const { activeConversation } = conversationSelection;
  const messageIsEmpty = message.trim().length === 0;
  const invalidatingConversationSelection: ProjectConversationSelection = {
    ...conversationSelection,
    createConversation: () => {
      conversationSelection.createConversation();
      onDraftChange?.();
    },
    renameConversation: (label) => {
      conversationSelection.renameConversation(label);
      onDraftChange?.();
    },
    selectConversation: (threadId) => {
      conversationSelection.selectConversation(threadId);
      onDraftChange?.();
    },
  };

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessageTouched(true);
    if (messageIsEmpty || isPending) {
      return;
    }

    await onSubmit({
      workspace_id: workspaceId,
      message,
      thread_id: activeConversation.threadId,
      thread_label: activeConversation.label.trim() || "Untitled conversation",
      adapter,
      mode,
      max_input_tokens: maxInputTokens,
      reserve_output_tokens: reserveOutputTokens,
      use_local_model: useLocalModel,
      include_debug: true,
    });
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <div className="composer__heading">
        <div>
          <p className="eyebrow">Your message</p>
          <h2 id="composer-message-title">What do you want to do?</h2>
        </div>
        <span className="exact-pill"><Icon name="shield" size={15} />Original wording preserved</span>
      </div>

      <textarea
        aria-describedby="message-help"
        aria-invalid={messageTouched && messageIsEmpty}
        aria-labelledby="composer-message-title"
        className="message-input"
        id="chat-message"
        name="message"
        onBlur={() => setMessageTouched(true)}
        onChange={(event) => {
          setMessage(event.target.value);
          onDraftChange?.();
        }}
        placeholder="Describe the task. Include any files, names, or constraints that matter."
        rows={5}
        spellCheck="true"
        value={message}
      />
      <div className="field-meta" id="message-help">
        <span className={messageTouched && messageIsEmpty ? "field-error" : undefined}>
          {messageTouched && messageIsEmpty ? "Enter a message before preparing the request." : "Your wording, spacing, paths, and constraints stay unchanged."}
        </span>
        <span>{message.length} characters</span>
      </div>

      <div className="composer__submit-row">
        <p className="compiler-route">
          {useLocalModel
            ? "Prepared locally. Selected sanitized context is sent only to your configured local model."
            : "Prepared locally. Nothing is sent to an external model."}
        </p>
        <button className="button button--primary button--large" disabled={messageIsEmpty || isPending || workspaceId.length === 0} type="submit">
          {isPending ? <span aria-hidden="true" className="button-spinner" /> : <Icon name="check" />}
          {isPending ? "Preparing…" : "Prepare request"}
        </button>
      </div>

      <div className="composer__secondary-controls">
        <details className="request-options">
          <summary>Output: {adapterLabel(adapter)} · {modeLabel(mode)}</summary>
          <div className="composer__controls">
            <div className="field-group">
              <span className="field-label field-label--with-tip"><label htmlFor="adapter-format">Format for</label> <InfoTip label="Format for">Choose the chat tool or portable format you plan to paste the prepared request into.</InfoTip></span>
              <select id="adapter-format" onChange={(event) => {
                setAdapter(event.target.value);
                onDraftChange?.();
              }} value={adapter}>
                <option value="codex">Codex</option>
                <option value="claude">Claude Code</option>
                <option value="cursor">Cursor</option>
                <option value="generic_markdown">Generic Markdown</option>
              </select>
            </div>
            <div className="field-group">
              <span className="field-label field-label--with-tip"><label htmlFor="context-style">Context style</label> <InfoTip label="Context style">Balanced is the recommended default. Source excerpts only avoids generated summaries.</InfoTip></span>
              <select id="context-style" onChange={(event) => {
                setMode(event.target.value as CompactionMode);
                onDraftChange?.();
              }} value={mode}>
                <option value="hybrid_safe">Balanced</option>
                <option value="strict_extractive">Source excerpts only</option>
                <option value="passthrough">Original message only</option>
              </select>
            </div>
          </div>
        </details>
        <ConversationSelector selection={invalidatingConversationSelection} />
        <details className="advanced-settings">
          <summary>Advanced settings</summary>
          <div className="advanced-settings__grid">
            <label className="field-group">
              <span className="field-label">Max input tokens</span>
              <input min="256" onChange={(event) => {
                setMaxInputTokens(event.target.valueAsNumber);
                onDraftChange?.();
              }} type="number" value={maxInputTokens} />
            </label>
            <label className="field-group">
              <span className="field-label">Reserve for answer</span>
              <input min="0" onChange={(event) => {
                setReserveOutputTokens(event.target.valueAsNumber);
                onDraftChange?.();
              }} type="number" value={reserveOutputTokens} />
            </label>
            <label className="toggle-row">
              <input checked={useLocalModel} onChange={(event) => {
                setUseLocalModel(event.target.checked);
                onDraftChange?.();
              }} type="checkbox" />
              <span>
                <strong>Use the optional local helper</strong>
                <small>Only selected, sanitized project context is passed to the configured local model.</small>
              </span>
            </label>
          </div>
        </details>
      </div>
    </form>
  );
}

function adapterLabel(adapter: string): string {
  const labels: Record<string, string> = {
    claude: "Claude",
    codex: "Codex",
    cursor: "Cursor",
    generic_markdown: "Markdown",
  };
  return labels[adapter] ?? "Custom";
}

function modeLabel(mode: CompactionMode): string {
  const labels: Record<CompactionMode, string> = {
    compact_aggressive: "Compact",
    hybrid_safe: "Balanced",
    passthrough: "Original only",
    strict_extractive: "Source excerpts",
  };
  return labels[mode];
}
