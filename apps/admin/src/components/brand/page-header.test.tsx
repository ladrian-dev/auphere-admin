import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PageHeader } from "./page-header";

describe("PageHeader", () => {
  it("renders eyebrow + index + title", () => {
    render(
      <PageHeader
        eyebrow="Tenants"
        eyebrowIndex="01"
        title="Portafolio"
        description="Lorem ipsum"
      />,
    );
    expect(screen.getByText("Portafolio")).toBeInTheDocument();
    expect(screen.getByText("Tenants")).toBeInTheDocument();
    expect(screen.getByText(/01/)).toBeInTheDocument();
    expect(screen.getByText("Lorem ipsum")).toBeInTheDocument();
  });

  it("renders the actions slot when provided", () => {
    render(
      <PageHeader
        title="Hi"
        actions={<button type="button">Promote</button>}
      />,
    );
    expect(screen.getByRole("button", { name: "Promote" })).toBeInTheDocument();
  });
});
