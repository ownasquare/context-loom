import { mount } from "cypress/react";
import { TokenMetricCard } from "../../src/components/ui/TokenMetricCard";

describe("TokenMetricCard", () => {
  it("keeps projected, observed, and verified confidence tiers explicit", () => {
    mount(
      <div className="metric-grid">
        <TokenMetricCard detail="Local baseline comparison" kind="projected" value={30_820} />
        <TokenMetricCard detail="Harness readback" kind="observed" value={18_412} />
        <TokenMetricCard detail="Measured control" kind="verified" value={28_904} />
      </div>,
    );

    cy.contains("Expected savings").should("be.visible");
    cy.contains("Local estimate").should("be.visible");
    cy.contains("Actual input used").should("be.visible");
    cy.contains("Provider report").should("be.visible");
    cy.contains("Measured savings").should("be.visible");
    cy.contains("Direct comparison").should("be.visible");
  });

  it("renders missing provider usage as unknown rather than zero", () => {
    mount(<TokenMetricCard detail="No provider readback" kind="observed" value={null} />);
    cy.contains("Unknown").should("be.visible");
    cy.contains(/^0 tokens$/).should("not.exist");
  });
});
