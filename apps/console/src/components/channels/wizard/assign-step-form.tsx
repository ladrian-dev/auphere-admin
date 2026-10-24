"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";

import { Button, Callout, Label, NativeSelect, cn } from "@nexus/ui";

import { assignChannelAgentAction } from "@/app/(console)/clients/[ref]/agents/actions";
import { setChannelRoleAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import { actionErrorText } from "@/lib/action-error";

import { wizardPaths } from "./steps";

export type AssignNumber = { id: string; label: string; agentId: string | null; agentEnabled: boolean };
export type AssignAgent = { id: string; name: string; published: boolean };
type Purpose = "agent" | "notifications";

/** The API's refusals when a number gets its agent, in words (principle III). */
const AGENT_ERRORS: Record<string, MessageKey> = {
  agent_not_published: "agents.error.agent_not_published",
  channel_send_only: "agents.error.channel_send_only",
  agent_archived: "agents.error.agent_archived",
};

/**
 * Pure: what saving step 3 has to do. The role is always written, so a
 * client never ends with a number nobody said what it was for (the line of
 * notices that received customers, QA of 2026-10-24). The agent is only
 * assigned on a number that serves customers and can answer.
 */
export function assignPlan(input: { purpose: Purpose; number: AssignNumber; agentId: string }): {
  role: Purpose;
  assign: string | null;
} {
  const answers = input.purpose === "agent" && input.number.agentEnabled;
  return { role: input.purpose, assign: answers && input.agentId ? input.agentId : null };
}

/**
 * Spec 046, step 3: what the number is for and who answers on it — the two
 * questions behind most of the silence the QA measured. Two big choices
 * instead of a «role» select, and the agent picker only when it matters.
 */
export function AssignStepForm({
  refId,
  channel,
  numbers,
  agents,
  defaultNumber,
  defaultAgent,
}: {
  refId: string;
  channel: string;
  numbers: AssignNumber[];
  agents: AssignAgent[];
  defaultNumber: string;
  defaultAgent: string;
}) {
  const t = useT();
  const router = useRouter();
  const paths = wizardPaths(refId);
  const [numberId, setNumberId] = React.useState(defaultNumber);
  const [purpose, setPurpose] = React.useState<Purpose>("agent");
  const [agentId, setAgentId] = React.useState(defaultAgent);
  const [error, setError] = React.useState<string | null>(null);
  const [pending, start] = React.useTransition();

  const number = numbers.find((n) => n.id === numberId) ?? numbers[0];
  if (!number) return null;
  const agent = agents.find((a) => a.id === agentId);
  const choosingAgent = purpose === "agent" && number.agentEnabled;
  const blocked = choosingAgent && (!agent || !agent.published);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!number) return;
    setError(null);
    const plan = assignPlan({ purpose, number, agentId });
    start(async () => {
      const role = await setChannelRoleAction({ ref: refId, channelId: number.id, role: plan.role });
      if (!role.ok) return void setError(actionErrorText(role, t));
      if (plan.assign) {
        const res = await assignChannelAgentAction({ ref: refId, channel: number.id, agent: plan.assign });
        if (!res.ok) {
          const key = res.code ? AGENT_ERRORS[res.code] : undefined;
          return void setError(key ? t(key) : actionErrorText(res, t));
        }
      }
      router.push(paths.done(channel, number.id, plan.role));
    });
  }

  return (
    <form className="flex max-w-xl flex-col gap-6" onSubmit={submit} noValidate>
      {numbers.length > 1 ? (
        <div className="flex flex-col gap-2">
          <Label htmlFor="chw-number">{t("chw.agent.number")}</Label>
          <NativeSelect id="chw-number" wrapperClassName="w-full" value={numberId} onChange={(e) => setNumberId(e.target.value)}>
            {numbers.map((n) => (
              <option key={n.id} value={n.id}>
                {n.label}
              </option>
            ))}
          </NativeSelect>
        </div>
      ) : (
        <p className="text-sm">
          <span className="text-muted-foreground">{t("chw.agent.number")}: </span>
          <span className="font-medium tabular-nums">{number.label}</span>
        </p>
      )}

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-3 text-sm font-medium">{t("chw.agent.purpose")}</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          {(["agent", "notifications"] as const).map((p) => (
            <label
              key={p}
              className={cn(
                "flex cursor-pointer flex-col gap-1 rounded-md p-4 ring-1 transition-shadow has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring",
                purpose === p ? "bg-primary/5 ring-primary" : "ring-foreground/10 hover:ring-primary/40",
              )}
            >
              <span className="flex items-center gap-2">
                <input
                  type="radio"
                  name="chw-purpose"
                  value={p}
                  checked={purpose === p}
                  onChange={() => setPurpose(p)}
                  className="size-4 accent-primary"
                />
                <span className="text-sm font-medium">{t(`chw.agent.purpose.${p}`)}</span>
              </span>
              <span className="pl-6 text-sm text-pretty text-muted-foreground">{t(`chw.agent.purpose.${p}.body`)}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {purpose === "agent" && !number.agentEnabled ? (
        <Callout tone="info">{t("chw.agent.sendOnly")}</Callout>
      ) : null}

      {choosingAgent ? (
        <div className="flex flex-col gap-2">
          {agents.length > 1 ? (
            <>
              <Label htmlFor="chw-agent">{t("chw.agent.who")}</Label>
              <NativeSelect id="chw-agent" wrapperClassName="w-full" value={agentId} onChange={(e) => setAgentId(e.target.value)}>
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.published ? a.name : t("agents.switcher.unpublished", { name: a.name })}
                  </option>
                ))}
              </NativeSelect>
            </>
          ) : agent ? (
            <p className="text-sm">
              <span className="text-muted-foreground">{t("chw.agent.who")}: </span>
              <span className="font-medium">{agent.name}</span>
            </p>
          ) : null}
          {agent && !agent.published ? (
            <Callout
              tone="warning"
              action={
                <Button nativeButton={false} size="sm" variant="outline" render={<Link href={`/clients/${encodeURIComponent(refId)}/agent${agent ? `?agent=${encodeURIComponent(agent.id)}` : ""}`} />}>
                  {t("chw.agent.toAgent")}
                </Button>
              }
            >
              {t("chw.agent.unpublished")}
            </Callout>
          ) : null}
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div>
        <Button type="submit" disabled={pending || blocked} aria-busy={pending}>
          {pending ? t("chw.agent.saving") : t("chw.agent.submit")}
        </Button>
      </div>
    </form>
  );
}
