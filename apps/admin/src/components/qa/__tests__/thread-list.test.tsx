import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { QAThread } from "@/lib/qa-api";

import { ThreadList } from "../thread-list";

function thread(over: Partial<QAThread> = {}): QAThread {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    tenant_id: "tn",
    operator_id: "op",
    external_id: null,
    title: "Thread A",
    archived_at: null,
    last_run_at: null,
    message_count: 0,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...over,
  };
}

describe("ThreadList", () => {
  it("shows an empty state when no threads exist", () => {
    render(
      <ThreadList
        threads={[]}
        activeThreadId={null}
        onSelect={() => {}}
        onCreate={async () => {}}
      />,
    );
    expect(
      screen.getByText(/Sin conversaciones. Creá una/),
    ).toBeInTheDocument();
  });

  it("renders threads and highlights the active one", () => {
    const a = thread({ id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", title: "A" });
    const b = thread({ id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", title: "B" });
    render(
      <ThreadList
        threads={[a, b]}
        activeThreadId={a.id}
        onSelect={() => {}}
        onCreate={async () => {}}
      />,
    );
    const aBtn = screen.getByRole("button", { name: /A/ });
    expect(aBtn).toHaveAttribute("aria-current", "page");
    const bBtn = screen.getByRole("button", { name: /^B/ });
    expect(bBtn).not.toHaveAttribute("aria-current");
  });

  it("fires onCreate when '+ nueva' is clicked", async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    render(
      <ThreadList
        threads={[]}
        activeThreadId={null}
        onSelect={() => {}}
        onCreate={onCreate}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /\+ nueva/ }));
    expect(onCreate).toHaveBeenCalled();
  });

  it("fires onSelect with the thread row", async () => {
    const onSelect = vi.fn();
    const a = thread({ title: "Clickable" });
    render(
      <ThreadList
        threads={[a]}
        activeThreadId={null}
        onSelect={onSelect}
        onCreate={async () => {}}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Clickable/ }));
    expect(onSelect).toHaveBeenCalledWith(a);
  });
});
