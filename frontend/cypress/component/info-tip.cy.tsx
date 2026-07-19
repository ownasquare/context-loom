import { mount } from "cypress/react";
import { InfoTip } from "../../src/components/ui/InfoTip";

describe("InfoTip", () => {
  it("reveals compact help for keyboard and touch without occupying the page", () => {
    mount(
      <div>
        <button type="button">Outside tooltip</button>
        <InfoTip label="Context style">Balanced context prefers concise cited evidence.</InfoTip>
      </div>,
    );

    cy.contains("button", "Outside tooltip").click();
    cy.get("[role='tooltip']").should("not.be.visible");
    cy.get("button[aria-label='About Context style']").should("have.css", "width", "28px").focus();
    cy.get("[role='tooltip']").should("be.visible").and("contain.text", "concise cited evidence");
    cy.get("button[aria-label='About Context style']").type("{esc}");
    cy.get("[role='tooltip']").should("not.be.visible");
    cy.get("button[aria-label='About Context style']").should("be.focused");
    cy.get("button[aria-label='About Context style']").click();
    cy.get("[role='tooltip']").should("be.visible");
  });
});
