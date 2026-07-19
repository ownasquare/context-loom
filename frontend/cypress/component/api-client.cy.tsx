import { ContextLoomApiClient } from "../../src/api/client";
import { ApiError } from "../../src/api/ApiError";
import { createDemoEnvelope, demoWorkspace } from "../../src/api/demoData";
import type {
  HydrateRequest,
  ResourceVersionContent,
  SyncReport,
  ThreadTokenSummary,
  UsageObservation,
} from "../../src/api/types";

const request: HydrateRequest = {
  workspace_id: "workspace-1",
  message: "  exact request\n",
  adapter: "codex",
  mode: "hybrid_safe",
  max_input_tokens: 4_000,
  reserve_output_tokens: 800,
  use_local_model: false,
  include_debug: true,
};

describe("ContextLoomApiClient production transport", () => {
  it("unwraps the canonical hydration response and forwards AbortSignal", () => {
    const envelope = createDemoEnvelope(request.message, request.mode);
    const response = new Response(
      JSON.stringify({
        envelope,
        rendered: {
          adapter: "codex",
          media_type: "text/markdown",
          payload: "compiled",
          exact_message: request.message,
          instructions: [],
        },
      }),
      { status: 201, headers: { "content-type": "application/json" } },
    );
    const fetchStub = cy.stub(window, "fetch").resolves(response);
    const controller = new AbortController();
    const client = new ContextLoomApiClient("");

    cy.then(async () => {
      const result = await client.hydrate(request, controller.signal);
      expect(result.envelope.message_exact).to.equal(request.message);
      expect(result.rendered.adapter).to.equal("codex");
      expect(result.rendered.payload).to.equal("compiled");
      expect(fetchStub).to.have.been.calledOnce;
      expect(fetchStub.firstCall.args[0]).to.equal("/api/v1/hydrations");
      expect(fetchStub.firstCall.args[1]?.signal).to.equal(controller.signal);
    });
  });

  it("surfaces the backend's nested redacted error contract", () => {
    const response = new Response(
      JSON.stringify({
        error: {
          code: "invalid_request",
          message: "Request validation failed",
          request_id: "request-1",
          details: { fields: [] },
        },
      }),
      { status: 422, headers: { "content-type": "application/json" } },
    );
    cy.stub(window, "fetch").resolves(response);
    const client = new ContextLoomApiClient("");

    cy.then(async () => {
      try {
        await client.hydrate(request);
        throw new Error("Expected hydrate to reject");
      } catch (error) {
        expect(error).to.be.instanceOf(ApiError);
        expect((error as ApiError).code).to.equal("invalid_request");
        expect((error as ApiError).requestId).to.equal("request-1");
      }
    });
  });

  it("creates and syncs workspaces through the versioned local API", () => {
    const syncReport: SyncReport = {
      workspace_id: demoWorkspace.id,
      generation_id: "generation-2",
      added: 2,
      modified: 1,
      deleted: 0,
      unchanged: 12,
      excluded: 4,
      redacted: 1,
      duration_ms: 48,
    };
    const fetchStub = cy.stub(window, "fetch");
    fetchStub.onFirstCall().resolves(
      new Response(JSON.stringify(demoWorkspace), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    );
    fetchStub.onSecondCall().resolves(
      new Response(JSON.stringify(syncReport), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const client = new ContextLoomApiClient("");

    cy.then(async () => {
      const created = await client.createWorkspace({
        name: "Context Loom",
        root_path: "/workspace/context-loom",
      });
      const synced = await client.syncWorkspace(created.id);

      expect(created).to.deep.equal(demoWorkspace);
      expect(synced).to.deep.equal(syncReport);
      expect(fetchStub.firstCall.args[0]).to.equal("/api/v1/workspaces");
      expect(fetchStub.firstCall.args[1]?.method).to.equal("POST");
      expect(fetchStub.firstCall.args[1]?.body).to.equal(
        JSON.stringify({ name: "Context Loom", root_path: "/workspace/context-loom" }),
      );
      expect(fetchStub.secondCall.args[0]).to.equal(
        `/api/v1/workspaces/${encodeURIComponent(created.id)}/sync`,
      );
      expect(fetchStub.secondCall.args[1]?.method).to.equal("POST");
    });
  });

  it("resolves an exact resource version with encoded identifiers", () => {
    const resource: ResourceVersionContent = {
      resource_id: "resource/one",
      version_id: "version current",
      workspace_id: demoWorkspace.id,
      relative_path: "src/context_loom/runtime.py",
      kind: "code",
      sha256: "a".repeat(64),
      content: "class ContextLoomRuntime:\n    pass\n",
      current: true,
      redacted_count: 0,
      created_at: "2026-07-19T12:00:00.000Z",
    };
    const fetchStub = cy.stub(window, "fetch").resolves(
      new Response(JSON.stringify(resource), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const controller = new AbortController();
    const client = new ContextLoomApiClient("");

    cy.then(async () => {
      const result = await client.resolveResourceVersion(
        resource.resource_id,
        resource.version_id,
        controller.signal,
      );

      expect(result.content).to.equal(resource.content);
      expect(fetchStub.firstCall.args[0]).to.equal(
        "/api/v1/resources/resource%2Fone/versions/version%20current",
      );
      expect(fetchStub.firstCall.args[1]?.signal).to.equal(controller.signal);
    });
  });

  it("records provider usage against the observation's thread", () => {
    const observation: UsageObservation = {
      idempotency_key: "usage-1",
      thread_id: "thread/one",
      hydration_id: "hydration-1",
      provider: "openai",
      model: "gpt-5",
      counting_method: "provider_observed",
      actual_input_tokens: 1_250,
      actual_output_tokens: 240,
    };
    const summary: ThreadTokenSummary = {
      thread_id: observation.thread_id,
      turns: 1,
      estimated_baseline_input_tokens: 2_000,
      estimated_hydrated_input_tokens: 1_300,
      projected_input_tokens_saved: 700,
      actual_input_tokens: 1_250,
      actual_output_tokens: 240,
      cached_input_tokens: null,
      local_compactor_tokens: 80,
      baseline_estimate_adjusted_reduction: 750,
      verified_counterfactual_tokens_saved: null,
      actual_usage_completeness: 1,
    };
    const fetchStub = cy.stub(window, "fetch").resolves(
      new Response(JSON.stringify(summary), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const client = new ContextLoomApiClient("");

    cy.then(async () => {
      const result = await client.recordUsage(observation);

      expect(result).to.deep.equal(summary);
      expect(fetchStub.firstCall.args[0]).to.equal("/api/v1/threads/thread%2Fone/usage");
      expect(fetchStub.firstCall.args[1]?.method).to.equal("POST");
      expect(fetchStub.firstCall.args[1]?.body).to.equal(JSON.stringify(observation));
    });
  });

  it("reads migration and local-model readiness separately from liveness", () => {
    const fetchStub = cy.stub(window, "fetch").resolves(
      new Response(
        JSON.stringify({
          status: "ready",
          database: "ready",
          local_model: "available",
          migrations_current: true,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    const controller = new AbortController();
    const client = new ContextLoomApiClient("");

    cy.then(async () => {
      const result = await client.getReadiness(controller.signal);

      expect(result.migrations_current).to.equal(true);
      expect(result.local_model).to.equal("available");
      expect(fetchStub.firstCall.args[0]).to.equal("/readyz");
      expect(fetchStub.firstCall.args[1]?.signal).to.equal(controller.signal);
    });
  });
});

describe("ContextLoomApiClient demo transport", () => {
  it("keeps newly connected demo projects empty until real files can be indexed", () => {
    const client = new ContextLoomApiClient("?demo=1");

    cy.then(async () => {
      const created = await client.createWorkspace({
        name: "New Project",
        root_path: "/demo/new-project",
      });
      const beforeSync = await client.getWorkspaceStatus(created.id);
      const sync = await client.syncWorkspace(created.id);
      const resources = await client.listResources(created.id);

      expect(created.id).to.equal("ws-demo-new-project");
      expect(beforeSync.indexed_resources).to.equal(0);
      expect(sync.added).to.equal(0);
      expect(sync.unchanged).to.equal(0);
      expect(resources).to.deep.equal([]);
    });
  });

  it("applies an idempotent demo usage observation only once", () => {
    const client = new ContextLoomApiClient("?demo=1");

    cy.then(async () => {
      const [thread] = await client.listThreads(demoWorkspace.id);
      expect(thread).not.to.equal(undefined);
      const observation: UsageObservation = {
        idempotency_key: "demo-usage-1",
        thread_id: thread!.thread_id,
        provider: "openai",
        model: "gpt-5",
        actual_input_tokens: 100,
        actual_output_tokens: 20,
      };
      const first = await client.recordUsage(observation);
      const duplicate = await client.recordUsage(observation);

      expect(duplicate).to.deep.equal(first);
      expect(first.actual_input_tokens).to.equal((thread!.actual_input_tokens ?? 0) + 100);
      expect(first.actual_output_tokens).to.equal((thread!.actual_output_tokens ?? 0) + 20);
    });
  });

  it("records prepared messages only in their selected demo project", () => {
    const client = new ContextLoomApiClient("?demo=1");

    cy.then(async () => {
      const existingThreads = await client.listThreads(demoWorkspace.id);
      const created = await client.createWorkspace({
        name: "Isolated Project",
        root_path: "/demo/isolated-project",
      });
      await client.syncWorkspace(created.id);
      const hydration = await client.hydrate({
        ...request,
        workspace_id: created.id,
        thread_id: "thread-isolated",
        thread_label: "Isolated review",
      });

      const isolatedThreads = await client.listThreads(created.id);
      const unchangedExistingThreads = await client.listThreads(demoWorkspace.id);
      expect(isolatedThreads).to.have.length(1);
      expect(isolatedThreads[0]).to.include({
        thread_id: "thread-isolated",
        label: "Isolated review",
        turns: 1,
      });
      expect(isolatedThreads[0]!.history[0]).to.include({
        hydration_id: hydration.envelope.hydration_id,
        usage_recorded: false,
      });
      expect(unchangedExistingThreads).to.deep.equal(existingThreads);
    });
  });

  it("aggregates multiple demo hydrations into one durable conversation", () => {
    const client = new ContextLoomApiClient("?demo=1");
    const threadId = "thread-demo-aggregate";

    cy.then(async () => {
      const first = await client.hydrate({
        ...request,
        workspace_id: demoWorkspace.id,
        thread_id: threadId,
        thread_label: "Aggregate review",
      });
      const second = await client.hydrate({
        ...request,
        workspace_id: demoWorkspace.id,
        thread_id: threadId,
      });
      const threads = await client.listThreads(demoWorkspace.id);
      const thread = threads.find((candidate) => candidate.thread_id === threadId);

      expect(thread).not.to.equal(undefined);
      expect(thread!.turns).to.equal(2);
      expect(thread!.label).to.equal("Aggregate review");
      expect(thread!.estimated_baseline_input_tokens).to.equal(
        first.envelope.token_plan.baseline.tokens + second.envelope.token_plan.baseline.tokens,
      );
      expect(thread!.estimated_hydrated_input_tokens).to.equal(
        first.envelope.token_plan.hydrated.tokens + second.envelope.token_plan.hydrated.tokens,
      );
      expect(thread!.projected_input_tokens_saved).to.equal(
        first.envelope.token_plan.projected_input_tokens_saved +
          second.envelope.token_plan.projected_input_tokens_saved,
      );
      expect(thread!.history.map((turn) => turn.hydration_id)).to.deep.equal([
        second.envelope.hydration_id,
        first.envelope.hydration_id,
      ]);
      expect(new Set(thread!.history.map((turn) => turn.hydration_id)).size).to.equal(2);
    });
  });

  it("enforces demo hydration ownership, idempotency, and one usage observation", () => {
    const client = new ContextLoomApiClient("?demo=1");

    cy.then(async () => {
      const first = await client.hydrate({
        ...request,
        workspace_id: demoWorkspace.id,
        thread_id: "thread-usage-owner",
      });
      await client.hydrate({
        ...request,
        workspace_id: demoWorkspace.id,
        thread_id: "thread-usage-other",
      });
      const observation: UsageObservation = {
        idempotency_key: "usage-owned-once",
        thread_id: "thread-usage-owner",
        hydration_id: first.envelope.hydration_id,
        provider: "openai",
        model: "gpt-5",
        actual_input_tokens: 321,
        actual_output_tokens: 45,
        verified_baseline_input_tokens: 500,
      };

      const recorded = await client.recordUsage(observation);
      const replayed = await client.recordUsage(observation);
      expect(replayed).to.deep.equal(recorded);
      expect(recorded.actual_usage_completeness).to.equal(1);

      const threads = await client.listThreads(demoWorkspace.id);
      const owner = threads.find((thread) => thread.thread_id === observation.thread_id);
      expect(owner!.history[0]).to.include({
        hydration_id: observation.hydration_id,
        usage_recorded: true,
        actual_input_tokens: 321,
        verified_counterfactual_tokens_saved: 179,
      });

      await expectApiError(
        client.recordUsage({ ...observation, actual_input_tokens: 322 }),
        "usage_idempotency_conflict",
      );
      await expectApiError(
        client.recordUsage({ ...observation, idempotency_key: "usage-second-observation" }),
        "hydration_usage_conflict",
      );
      await expectApiError(
        client.recordUsage({
          ...observation,
          idempotency_key: "usage-wrong-owner",
          thread_id: "thread-usage-other",
        }),
        "hydration_thread_mismatch",
      );
      await expectApiError(
        client.recordUsage({
          ...observation,
          idempotency_key: "usage-missing-hydration",
          hydration_id: "missing-hydration",
        }),
        "not_found",
      );
    });
  });
});

async function expectApiError(promise: Promise<unknown>, code: string): Promise<void> {
  try {
    await promise;
    throw new Error(`Expected ${code}`);
  } catch (error) {
    expect(error).to.be.instanceOf(ApiError);
    expect((error as ApiError).code).to.equal(code);
  }
}
