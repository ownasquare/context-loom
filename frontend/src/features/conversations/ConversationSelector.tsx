import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "../../components/icons/Icon";

const STORAGE_PREFIX = "context-loom:conversation-metadata:v1";
const MAX_LABEL_LENGTH = 80;
let fallbackThreadSequence = 0;

export interface ConversationMetadata {
  threadId: string;
  label: string;
}

interface StoredConversationState {
  activeThreadId: string;
  conversations: ConversationMetadata[];
}

export interface ProjectConversationSelection {
  activeConversation: ConversationMetadata;
  conversations: ConversationMetadata[];
  createConversation: () => void;
  renameConversation: (label: string) => void;
  selectConversation: (threadId: string) => void;
}

interface ConversationSelectorProps {
  selection: ProjectConversationSelection;
}

export function ConversationSelector({ selection }: ConversationSelectorProps) {
  const { activeConversation, conversations, createConversation, renameConversation, selectConversation } = selection;
  const selectId = `conversation-select-${activeConversation.threadId}`;
  const nameId = `conversation-name-${activeConversation.threadId}`;

  return (
    <details className="conversation-selector">
      <summary>
        <div>
          <span>Conversation</span>
          <strong>{activeConversation.label}</strong>
        </div>
        <span className="conversation-selector__manage">Manage <Icon name="chevron" size={16} /></span>
      </summary>
      <div className="conversation-selector__body">
        <p>Keep related messages together for a clearer source and savings history.</p>
        <div className="conversation-selector__fields">
          <label className="field-group" htmlFor={selectId}>
            <span className="field-label">Current conversation</span>
            <select
              id={selectId}
              onChange={(event) => selectConversation(event.target.value)}
              value={activeConversation.threadId}
            >
              {conversations.map((conversation) => (
                <option key={conversation.threadId} value={conversation.threadId}>{conversation.label}</option>
              ))}
            </select>
          </label>
          <label className="field-group" htmlFor={nameId}>
            <span className="field-label">Conversation name</span>
            <input
              id={nameId}
              maxLength={MAX_LABEL_LENGTH}
              onBlur={() => {
                if (activeConversation.label.trim().length === 0) {
                  renameConversation(defaultConversationLabel(conversations.indexOf(activeConversation) + 1));
                }
              }}
              onChange={(event) => renameConversation(event.target.value)}
              type="text"
              value={activeConversation.label}
            />
          </label>
        </div>
        <button className="button button--secondary" onClick={createConversation} type="button">New conversation</button>
      </div>
    </details>
  );
}

export function useProjectConversation(workspaceId: string): ProjectConversationSelection {
  const statesByWorkspace = useRef<Record<string, StoredConversationState>>({});
  const [, setRevision] = useState(0);
  const currentState = statesByWorkspace.current[workspaceId] ?? loadConversationState(workspaceId);
  statesByWorkspace.current[workspaceId] = currentState;

  useEffect(() => {
    persistConversationState(workspaceId, currentState);
  }, [currentState, workspaceId]);

  const updateState = useCallback((update: (state: StoredConversationState) => StoredConversationState) => {
    const existing = statesByWorkspace.current[workspaceId] ?? loadConversationState(workspaceId);
    statesByWorkspace.current[workspaceId] = update(existing);
    setRevision((revision) => revision + 1);
  }, [workspaceId]);

  const createConversation = useCallback(() => {
    updateState((state) => {
      const conversation: ConversationMetadata = {
        threadId: createThreadId(),
        label: defaultConversationLabel(state.conversations.length + 1),
      };
      return {
        activeThreadId: conversation.threadId,
        conversations: [...state.conversations, conversation],
      };
    });
  }, [updateState]);

  const renameConversation = useCallback((label: string) => {
    updateState((state) => ({
      ...state,
      conversations: state.conversations.map((conversation) => (
        conversation.threadId === state.activeThreadId
          ? { ...conversation, label: label.slice(0, MAX_LABEL_LENGTH) }
          : conversation
      )),
    }));
  }, [updateState]);

  const selectConversation = useCallback((threadId: string) => {
    updateState((state) => (
      state.conversations.some((conversation) => conversation.threadId === threadId)
        ? { ...state, activeThreadId: threadId }
        : state
    ));
  }, [updateState]);

  const activeConversation = currentState.conversations.find(
    (conversation) => conversation.threadId === currentState.activeThreadId,
  ) ?? currentState.conversations[0]!;

  return {
    activeConversation,
    conversations: currentState.conversations,
    createConversation,
    renameConversation,
    selectConversation,
  };
}

function loadConversationState(workspaceId: string): StoredConversationState {
  try {
    const rawState = window.localStorage.getItem(storageKey(workspaceId));
    const parsedState = rawState ? JSON.parse(rawState) : null;
    const normalizedState = normalizeStoredState(parsedState);
    if (normalizedState) {
      return normalizedState;
    }
  } catch {
    // A blocked or malformed local store should never block preparing a request.
  }

  const firstConversation: ConversationMetadata = {
    threadId: createThreadId(),
    label: defaultConversationLabel(1),
  };
  return {
    activeThreadId: firstConversation.threadId,
    conversations: [firstConversation],
  };
}

function persistConversationState(workspaceId: string, state: StoredConversationState) {
  try {
    window.localStorage.setItem(storageKey(workspaceId), JSON.stringify(state));
  } catch {
    // Conversation continuity is best effort when browser storage is unavailable.
  }
}

function normalizeStoredState(value: unknown): StoredConversationState | null {
  if (!isRecord(value) || !Array.isArray(value.conversations)) {
    return null;
  }

  const conversations = value.conversations.flatMap((candidate): ConversationMetadata[] => {
    if (!isRecord(candidate) || typeof candidate.threadId !== "string" || typeof candidate.label !== "string") {
      return [];
    }
    if (candidate.threadId.length === 0 || candidate.threadId.length > 160 || candidate.label.length > MAX_LABEL_LENGTH) {
      return [];
    }
    return [{ threadId: candidate.threadId, label: candidate.label }];
  });
  if (conversations.length === 0) {
    return null;
  }

  const requestedActiveId = typeof value.activeThreadId === "string" ? value.activeThreadId : "";
  const activeThreadId = conversations.some((conversation) => conversation.threadId === requestedActiveId)
    ? requestedActiveId
    : conversations[0]!.threadId;
  return { activeThreadId, conversations };
}

function createThreadId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return `thread-local-${globalThis.crypto.randomUUID()}`;
  }

  if (typeof globalThis.crypto?.getRandomValues === "function") {
    const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
    const fallbackId = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
    return `thread-local-${fallbackId}`;
  }

  fallbackThreadSequence += 1;
  return `thread-local-${Date.now().toString(36)}-${fallbackThreadSequence.toString(36)}`;
}

function defaultConversationLabel(sequence: number): string {
  return `Conversation ${Math.max(sequence, 1)}`;
}

function storageKey(workspaceId: string): string {
  return `${STORAGE_PREFIX}:${encodeURIComponent(workspaceId)}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
