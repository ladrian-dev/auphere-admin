import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { CommentPost } from "../comment-post";

const ID = "22222222-2222-4222-8222-222222222222";

function view(data: unknown, ok = true) {
  const load = vi.fn().mockResolvedValue(ok ? { ok: true, data } : { ok: false, status: 500, message: "" });
  const out = render(
    <LocaleProvider locale="es">
      <CommentPost messageId={ID} load={load} />
    </LocaleProvider>,
  );
  return { ...out, load };
}

/** Owner, 2026-11-02: the post a comment was left on, above the comment. */
describe("CommentPost", () => {
  it("shows the caption, the picture and the link to the post", async () => {
    const { load, container } = view({ text: "Nuestra carta", image_url: "https://x.fbcdn.net/a.jpg", permalink: "https://facebook.com/p/1" });
    expect(await screen.findByText("Nuestra carta")).toBeInTheDocument();
    expect(load).toHaveBeenCalledWith(ID);
    expect(screen.getByText("Comentó en esta publicación")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver la publicación" })).toHaveAttribute("href", "https://facebook.com/p/1");
    expect(container.querySelector("img")).toHaveAttribute("src", "https://x.fbcdn.net/a.jpg");
  });

  it.each([
    ["Meta gives nothing", null, true],
    ["the read fails", null, false],
  ])("%s: nothing shows", async (_name, data, ok) => {
    const { load, container } = view(data, ok);
    await waitFor(() => expect(load).toHaveBeenCalled());
    expect(container.querySelector("[data-slot=comment-post]")).toBeNull();
  });
});
