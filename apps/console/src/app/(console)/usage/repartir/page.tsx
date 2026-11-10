import { redirect } from "next/navigation";

import { ErrorState, PageHeader } from "@nexus/ui";

import { MigrationWizard } from "@/components/money/migration-wizard";
import { resolveConsoleVersion } from "@/components/shell/console-version";
import { getT } from "@/i18n/server";
import { backendFor, callFor } from "@/lib/backend";
import { moneyApi } from "@/lib/backend/money";
import { can, requirePartnerPrincipal } from "@/lib/principal";
import { ShellBackButton } from "@/components/shell/shell-back-button";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("money.migration.title") };
}

/**
 * «Repartir tu saldo en bolsas» (spec 047, T160, requisito 55.3): la primera vez
 * que un partner con topes mensuales entra en la consola nueva. La propuesta es
 * lo que le queda este mes a cada cliente; al confirmarla pasa a su bolsa. Solo
 * con la consola nueva: con la de hoy, los topes siguen como están.
 */
export default async function MigrationPage() {
  const principal = await requirePartnerPrincipal("/usage/repartir");
  if (!can(principal.role, "usage:read")) redirect("/");
  const api = backendFor(principal);
  if (resolveConsoleVersion(await api.me().catch(() => null)) !== "v2") redirect("/usage");
  const { t } = await getT(principal.locale);
  const money = moneyApi(callFor(principal));
  const [proposal, summary, account] = await Promise.all([
    money.getMigration().catch(() => null),
    money.usageSummary().catch(() => null),
    money.getAccount().catch(() => null),
  ]);
  const names = Object.fromEntries((summary?.clients ?? []).map((c) => [c.ref, c.name ?? c.ref]));
  return (
    <>
      <PageHeader size="display" back={<ShellBackButton />} title={t("money.migration.title")} description={t("money.migration.description")} />
      {proposal ? (
        <MigrationWizard proposal={proposal} names={names} canConfirm={can(principal.role, "usage:write")} currency={account?.account_currency ?? null} />
      ) : (
        <ErrorState title={t("money.migration.error")} />
      )}
    </>
  );
}
