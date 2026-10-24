import type { MessageKey } from "@/i18n/messages";

/**
 * Spec 046: the four steps of «Añadir canal», the same as the operator
 * panel's (spec 035). The path says the step:
 * `/channels/new` · `/new/{c}` · `/new/{c}/agent` · `/new/{c}/done`.
 */
export const WIZARD_STEPS: ReadonlyArray<{ title: MessageKey; body: MessageKey }> = [
  { title: "chw.step.choose", body: "chw.step.choose.body" },
  { title: "chw.step.connect", body: "chw.step.connect.body" },
  { title: "chw.step.agent", body: "chw.step.agent.body" },
  { title: "chw.step.done", body: "chw.step.done.body" },
];

export function stepOf(pathname: string): number {
  const rest = pathname.split("/channels/new")[1] ?? "";
  const parts = rest.split("/").filter(Boolean);
  if (parts.length === 0) return 0;
  if (parts[1] === "agent") return 2;
  if (parts[1] === "done") return 3;
  return 1;
}

/** The wizard's paths for one client, so no page spells them by hand. */
export function wizardPaths(ref: string) {
  const base = `/clients/${encodeURIComponent(ref)}/channels`;
  return {
    channels: base,
    choose: `${base}/new`,
    connect: (channel: string) => `${base}/new/${encodeURIComponent(channel)}`,
    agent: (channel: string, channelId?: string) =>
      `${base}/new/${encodeURIComponent(channel)}/agent${channelId ? `?channel=${encodeURIComponent(channelId)}` : ""}`,
    done: (channel: string, channelId: string, role: "agent" | "notifications") =>
      `${base}/new/${encodeURIComponent(channel)}/done?channel=${encodeURIComponent(channelId)}${role === "notifications" ? "&role=notifications" : ""}`,
  };
}
