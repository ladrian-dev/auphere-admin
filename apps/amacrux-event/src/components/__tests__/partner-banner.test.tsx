import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import "./test-utils";
import { Footer } from "../layout/Footer";
import { PartnerSticker } from "../ui/PartnerSticker";

describe("sello de partner oficial de Auphere", () => {
  it("es un enlace accesible a auphere.com con el texto fuera del sticker", () => {
    render(<PartnerSticker />);
    const link = screen.getByRole("link", { name: /amacrux es partner oficial de auphere/i });
    expect(link).toHaveAttribute("href", "https://auphere.com");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.getByText(/partner oficial de/i)).toBeInTheDocument();
    expect(link.querySelector("img")).toHaveAttribute("src", expect.stringContaining("partner-sticker"));
  });
  it("el pie lo incluye en todas las páginas", () => {
    render(<Footer />);
    expect(screen.getByRole("link", { name: /partner oficial de auphere/i })).toBeInTheDocument();
  });
});
