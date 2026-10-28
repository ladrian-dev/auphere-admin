import { router, Stack } from "expo-router";
import { useState } from "react";

import { useBusiness } from "@/api/hooks";
import { BusinessHome } from "@/features/business/business-home";
import { useSectionWrite } from "@/features/business/use-section-write";
import { useLocale, useT } from "@/i18n/t";
import { clock } from "@/lib/format";
import { usePullRefresh } from "@/lib/use-pull-refresh";
import { ScrollScreen } from "@/ui/screen";
import { ErrorState, OfflineBanner, Skeleton } from "@/ui/states";

/**
 * Negocio (spec 047, T169, 50.1): the way into the hours, the services and
 * the locations, opened from Inicio and from Ajustes. Its own stack above the
 * tabs: each section is a screen pushed from here.
 */
export default function Negocio() {
  const t = useT();
  const locale = useLocale();
  const business = useBusiness();
  const write = useSectionWrite(["hours", "special_dates", "services", "locations"]);
  const [undoing, setUndoing] = useState(false);
  const pull = usePullRefresh(() => business.refetch());

  return (
    <>
      <Stack.Screen options={{ title: t("negocio.title") }} />
      <ScrollScreen refreshing={pull.refreshing} onRefresh={pull.onRefresh} testID="negocio">
        {!write.online && business.data ? <OfflineBanner since={clock(new Date(business.dataUpdatedAt), locale)} /> : null}
        {business.data ? (
          <BusinessHome
            data={business.data}
            online={write.online}
            undoing={undoing}
            onHours={() => router.push("/negocio/horario")}
            onServices={() => router.push("/negocio/servicios")}
            onLocations={() => router.push("/negocio/sedes")}
            onUndo={(c) => {
              setUndoing(true);
              void write.undo(c.id).finally(() => setUndoing(false));
            }}
            t={t}
            locale={locale}
          />
        ) : business.isError ? (
          <ErrorState body={t("business.section.error")} onRetry={() => void business.refetch()} />
        ) : (
          <Skeleton rows={3} label={t("negocio.loading")} />
        )}
      </ScrollScreen>
    </>
  );
}
