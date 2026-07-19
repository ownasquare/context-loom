import { mount } from "cypress/react";
import {
  ConversationSelector,
  useProjectConversation,
} from "../../src/features/conversations/ConversationSelector";

interface HarnessProps {
  workspaceId: string;
}

function ConversationHarness({ workspaceId }: HarnessProps) {
  const selection = useProjectConversation(workspaceId);

  return (
    <>
      <ConversationSelector selection={selection} />
      <output data-testid="active-conversation-id">{selection.activeConversation.threadId}</output>
    </>
  );
}

describe("ConversationSelector", () => {
  it("reuses the active conversation until New conversation is explicit", () => {
    mount(<ConversationHarness workspaceId="project-a" />);

    cy.get("[data-testid='active-conversation-id']").invoke("text").then((firstThreadId) => {
      expect(firstThreadId).to.match(/^thread-local-/);

      mount(<ConversationHarness workspaceId="project-a" />);
      cy.get("[data-testid='active-conversation-id']").should("have.text", firstThreadId);

      cy.get("details.conversation-selector > summary").click();
      cy.contains("button", "New conversation").click();
      cy.get("[data-testid='active-conversation-id']").invoke("text").should("not.equal", firstThreadId);
    });
  });

  it("persists only project-scoped id and label metadata", () => {
    mount(<ConversationHarness workspaceId="project-a" />);
    cy.get("details.conversation-selector > summary").click();
    cy.contains("label", "Conversation name").find("input").clear().type("Release review");

    cy.get("[data-testid='active-conversation-id']").invoke("text").then((projectAThreadId) => {
      mount(<ConversationHarness workspaceId="project-b" />);
      cy.get("[data-testid='active-conversation-id']").invoke("text").should("not.equal", projectAThreadId);
      cy.get("details.conversation-selector > summary").click();
      cy.contains("label", "Conversation name").find("input").should("have.value", "Conversation 1");

      cy.window().then((browserWindow) => {
        const storedValues = Object.entries(browserWindow.localStorage)
          .filter(([key]) => key.startsWith("context-loom:conversation-metadata:v1:"))
          .map(([, value]) => value)
          .join(" ");

        expect(storedValues).to.contain("Release review");
        expect(storedValues).not.to.contain("message");
        expect(storedValues).not.to.contain("workspace");
      });
    });
  });
});
