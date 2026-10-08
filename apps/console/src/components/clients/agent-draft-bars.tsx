"use client";

import { useSearchParams } from "next/navigation";

import type { DraftScreen } from "@/lib/backend";

import { DraftBarClient } from "./draft-bar-client";

export type AgentDraft = {
  agentId: string;
  isPrincipal: boolean;
  screens: DraftScreen[];
  /** The newest version; `null` when the agent has none yet. */
  version: number | null;
  activeVersion: number | null;
};

/**
 * Spec 030: with several agents, the draft bar is the one of the agent in
 * `?agent=` — the principal's anywhere else. The layout cannot read the URL
 * (it is shared by every tab), so it hands over every agent's draft and this
 * picks; each agent's bar is its own, undo window included.
 */
export function AgentDraftBars({ refId, drafts, canPublish }: { refId: string; drafts: AgentDraft[]; canPublish: boolean }) {
  const wanted = useSearchParams().get("agent");
  const pick = drafts.find((d) => !d.isPrincipal && d.agentId === wanted) ?? drafts.find((d) => d.isPrincipal);
  if (!pick || pick.version === null) return null;
  return (
    <DraftBarClient
      key={pick.agentId}
      refId={refId}
      agentId={pick.isPrincipal ? undefined : pick.agentId}
      screens={pick.screens}
      version={pick.version}
      activeVersion={pick.activeVersion}
      canPublish={canPublish}
    />
  );
}
