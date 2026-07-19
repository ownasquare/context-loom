import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import type { HydrateRequest, HydrationResponse } from "../api/types";
import { useWorkspace } from "../app/workspace";
import { Icon } from "../components/icons/Icon";
import { PageHeader } from "../components/ui/PageHeader";
import { StatePanel } from "../components/ui/StatePanel";
import { HydrationComposer } from "../features/hydration/HydrationComposer";
import { HydrationInspector } from "../features/hydration/HydrationInspector";
import { ProjectSetup } from "../features/workspaces/ProjectSetup";
import { queryKeys } from "../api/queryKeys";

interface MutationInput {
  request: HydrateRequest;
  signal: AbortSignal;
}

export function HydratePage() {
  const { selectedWorkspace, selectedWorkspaceId, workspacesQuery } = useWorkspace();

  if (workspacesQuery.isPending) {
    return <StatePanel kind="loading" />;
  }

  if (workspacesQuery.isError) {
    return <StatePanel kind="error" onRetry={() => void workspacesQuery.refetch()} />;
  }

  if (!selectedWorkspace || !selectedWorkspaceId) {
    return <ProjectSetup />;
  }

  return (
    <WorkspaceHydratePage
      key={selectedWorkspaceId}
      workspaceId={selectedWorkspaceId}
      workspaceName={selectedWorkspace.name}
    />
  );
}

interface WorkspaceHydratePageProps {
  workspaceId: string;
  workspaceName: string;
}

const DEMO_MESSAGE = "Review src/context_loom/hydration/service.py and preserve max_input_tokens=4000. Do not enable outbound network access.";

function WorkspaceHydratePage({ workspaceId, workspaceName }: WorkspaceHydratePageProps) {
  const queryClient = useQueryClient();
  const [hydration, setHydration] = useState<HydrationResponse | null>(null);
  const [lastRequest, setLastRequest] = useState<HydrateRequest | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const requestVersionRef = useRef(0);
  const mutation = useMutation({
    mutationFn: ({ request, signal }: MutationInput) => apiClient.hydrate(request, signal),
  });

  useEffect(() => () => {
    requestVersionRef.current += 1;
    controllerRef.current?.abort();
  }, []);

  useEffect(() => {
    if (!hydration) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      const result = document.getElementById("prepared-request-result");
      result?.focus({ preventScroll: true });
      result?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "start",
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [hydration]);

  function clearPreparedResult() {
    requestVersionRef.current += 1;
    const controller = controllerRef.current;
    controllerRef.current = null;
    controller?.abort();
    setHydration(null);
    mutation.reset();
  }

  async function hydrate(request: HydrateRequest) {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const requestVersion = requestVersionRef.current + 1;
    requestVersionRef.current = requestVersion;
    setLastRequest(request);
    setHydration(null);

    try {
      const result = await mutation.mutateAsync({ request, signal: controller.signal });
      if (controller.signal.aborted || requestVersionRef.current !== requestVersion) {
        return;
      }
      controllerRef.current = null;
      setHydration(result);
      await queryClient.invalidateQueries({ queryKey: queryKeys.threads(workspaceId) });
    } catch {
      if (controller.signal.aborted || requestVersionRef.current !== requestVersion) {
        if (controllerRef.current === null) {
          mutation.reset();
        }
        return;
      }
      controllerRef.current = null;
    }
  }

  function retryLastRequest() {
    if (lastRequest) {
      void hydrate(lastRequest);
    }
  }

  const failureDescription = lastRequest?.use_local_model
    ? "The preparation failed. Try again to repeat the same request. The configured helper may already have received selected, sanitized project context; the finished request was not sent to a chat provider."
    : "The local preparation failed. Try again to repeat the same request; nothing was sent to a configured helper or chat provider.";

  return (
    <div className="page page--hydrate">
      <PageHeader
        description={`Write the request you planned to send about ${workspaceName}. Context Loom adds focused local context for you to review and copy.`}
        eyebrow={workspaceName}
        title="Prepare message"
      />
      <HydrationComposer
        initialMessage={apiClient.isDemoMode() ? DEMO_MESSAGE : undefined}
        isPending={mutation.isPending}
        onDraftChange={clearPreparedResult}
        onSubmit={hydrate}
        workspaceId={workspaceId}
      />
      {mutation.isPending ? <StatePanel description="Finding useful project sources and checking the prepared request." kind="loading" title="Preparing your request" /> : null}
      {mutation.isError && !mutation.isPending ? <StatePanel description={failureDescription} kind="error" onRetry={lastRequest ? retryLastRequest : undefined} title="Could not prepare the request" /> : null}
      <p aria-atomic="true" aria-live="polite" className="sr-only" role="status">{hydration ? "Prepared request ready. Review it, then copy it when you are ready." : ""}</p>
      {hydration && !mutation.isPending ? <HydrationInspector response={hydration} /> : null}
      {!hydration && !mutation.isPending && !mutation.isError ? <HydrationPreview /> : null}
    </div>
  );
}

function HydrationPreview() {
  return (
    <section aria-label="Prepared request preview" className="hydration-preview hydration-preview--quiet card">
      <span className="hydration-preview__icon"><Icon name="copy" /></span>
      <div>
        <h2>Your prepared request will appear here</h2>
        <p>Review the sources, then copy it when you are ready. Context Loom never sends it automatically.</p>
      </div>
    </section>
  );
}
