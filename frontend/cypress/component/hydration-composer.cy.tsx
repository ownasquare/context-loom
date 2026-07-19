import { mount } from "cypress/react";
import { HydrationComposer } from "../../src/features/hydration/HydrationComposer";

describe("HydrationComposer", () => {
  it("starts empty in production and uses plain-language controls", () => {
    mount(<HydrationComposer isPending={false} onSubmit={cy.stub()} workspaceId="ws-1" />);

    cy.get("#chat-message").should("have.value", "");
    cy.get("#chat-message").should("not.have.attr", "autofocus");
    cy.contains("h2", "What do you want to do?").should("be.visible");
    cy.contains("summary", "Output: Codex · Balanced").should("be.visible");
    cy.contains("button", "Prepare request").should("be.disabled");
    cy.get("details.conversation-selector").should("not.have.attr", "open");
    cy.contains("button", "Prepare request").then(($button) => {
      cy.get("details.conversation-selector").then(($conversation) => {
        expect($button[0]!.compareDocumentPosition($conversation[0]!) & Node.DOCUMENT_POSITION_FOLLOWING).to.be.greaterThan(0);
      });
    });
  });

  it("rejects whitespace-only input", () => {
    mount(<HydrationComposer initialMessage="   " isPending={false} onSubmit={cy.stub()} workspaceId="ws-1" />);
    cy.get("textarea").focus().blur();
    cy.contains("Enter a message before preparing the request.").should("be.visible");
    cy.contains("button", "Prepare request").should("be.disabled");
  });

  it("submits the exact textarea value with the active conversation", () => {
    const submit = cy.stub().resolves();
    mount(<HydrationComposer initialMessage="  Keep  both spaces.  " isPending={false} onSubmit={submit} workspaceId="ws-1" />);
    cy.contains("button", "Prepare request").click();
    cy.then(() => {
      expect(submit).to.have.been.calledOnce;
      expect(submit.firstCall.args[0].message).to.equal("  Keep  both spaces.  ");
      expect(submit.firstCall.args[0].thread_id).to.match(/^thread-local-/);
      expect(submit.firstCall.args[0].thread_label).to.equal("Conversation 1");
    });
  });

  it("invalidates prepared output for every request-relevant change", () => {
    const draftChange = cy.stub().as("draftChange");
    mount(
      <HydrationComposer
        initialMessage="Review the project."
        isPending={false}
        onDraftChange={draftChange}
        onSubmit={cy.stub()}
        workspaceId="ws-1"
      />,
    );

    cy.get("#chat-message").type(" More detail.");
    cy.get("@draftChange").should("have.been.called");
    cy.get("@draftChange").invoke("resetHistory");

    cy.get("details.conversation-selector > summary").click();
    cy.contains("label", "Conversation name").find("input").type(" updated");
    cy.get("@draftChange").should("have.been.called");
    cy.get("@draftChange").invoke("resetHistory");

    cy.contains("button", "New conversation").click();
    cy.get("@draftChange").should("have.been.calledOnce");
    cy.get("@draftChange").invoke("resetHistory");

    cy.contains("label", "Current conversation").find("select").select(0);
    cy.get("@draftChange").should("have.been.calledOnce");
    cy.get("@draftChange").invoke("resetHistory");

    cy.contains("summary", "Output:").click();
    cy.get("#adapter-format").select("Claude Code");
    cy.get("@draftChange").should("have.been.calledOnce");
    cy.get("@draftChange").invoke("resetHistory");

    cy.get("#context-style").select("Source excerpts only");
    cy.get("@draftChange").should("have.been.calledOnce");
    cy.get("@draftChange").invoke("resetHistory");

    cy.contains("summary", "Advanced settings").click();
    cy.contains("label", "Max input tokens").find("input").clear().type("5000");
    cy.get("@draftChange").should("have.been.called");
    cy.get("@draftChange").invoke("resetHistory");

    cy.contains("label", "Reserve for answer").find("input").clear().type("900");
    cy.get("@draftChange").should("have.been.called");
    cy.get("@draftChange").invoke("resetHistory");

    cy.contains("label", "Use the optional local helper").find("input").check();
    cy.get("@draftChange").should("have.been.calledOnce");
  });

  it("describes model transfer truthfully when the local helper is enabled", () => {
    mount(<HydrationComposer initialMessage="Review the project." isPending={false} onSubmit={cy.stub()} workspaceId="ws-1" />);

    cy.contains("Prepared locally. Nothing is sent to an external model.").should("be.visible");
    cy.contains("summary", "Advanced settings").click();
    cy.contains("label", "Use the optional local helper").find("input").check();
    cy.contains("Selected sanitized context is sent only to your configured local model.").should("be.visible");
  });
});
