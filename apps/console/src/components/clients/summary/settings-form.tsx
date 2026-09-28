"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button, Form, FormControl, FormField, FormItem, FormLabel, FormMessage, Input } from "@nexus/ui";

import { updateClientAction } from "@/app/(console)/clients/actions";
import { useT } from "@/i18n/client";

type Values = { name: string; timezone: string };

/** Las zonas IANA que conoce el navegador. Se calcula una vez por carga:
 *  son ~400 y no cambian mientras la pestaña esté abierta. */
function ianaZones(): string[] {
  try {
    const supported = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf;
    return supported ? supported("timeZone") : [];
  } catch {
    // Un navegador que no la tenga se queda con el campo de texto de
    // siempre: sin sugerencias, pero sin romperse.
    return [];
  }
}

export function SettingsForm({ refId, name, timezone }: { refId: string; name: string; timezone: string }) {
  const zonesId = React.useId();
  const zones = React.useMemo(() => ianaZones(), []);
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const schema = React.useMemo(
    () =>
      z.object({
        name: z.string().min(1, t("validation.required")).max(255, t("validation.tooLong")),
        timezone: z.string().min(1, t("validation.required")).max(64, t("validation.tooLong")),
      }),
    [t],
  );
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { name, timezone } });
  return (
    <Form {...form}>
      <form
        noValidate
        aria-busy={pending}
        // Spec 018 (owner, 2026-09-28): dos campos cortos uno debajo de
        // otro desperdiciaban el ancho entero de la ficha y añadían scroll
        // por nada. En una columna estrecha vuelven a apilarse solos.
        // Tres columnas: los dos campos y el botón en la misma fila. En
        // estrecho vuelven a apilarse solos.
        className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_1fr_auto] sm:items-start"
        onSubmit={form.handleSubmit((values) =>
          startTransition(async () => {
            const res = await updateClientAction({ ref: refId, ...values });
            if (!res.ok) return void toast.error(res.message);
            toast.success(t("clients.settings.saved"));
            router.refresh();
          }),
        )}
      >
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("common.name")}</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="timezone"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("clients.timezone")}</FormLabel>
              <FormControl>
                {/* Elegible, no escrita a mano. La lista es la de zonas IANA
                    que el propio navegador conoce, así que no hay tabla
                    nuestra que se quede vieja ni dependencia nueva; el campo
                    sigue siendo un input, así que se puede teclear y se
                    autocompleta. La validación de la zona no se toca: esto
                    reduce el error humano, no lo sustituye. */}
                <Input className="font-mono" list={zonesId} autoComplete="off" spellCheck={false} {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        {/* El botón arranca a la altura de los inputs, no de las etiquetas.
            El espaciador replica la etiqueta —misma tipografía, mismo hueco
            de la rejilla— en vez de un margen a ojo: así sigue cuadrando si
            cambia el tamaño del texto. Ni `mt-6` ni `self-end` lo lograban:
            el primero se pasaba 2 px y el segundo alineaba con el fondo de
            la fila, que tiene holgura de sobra. */}
        <div className="grid content-start gap-2">
          <span aria-hidden="true" className="hidden text-sm leading-none sm:block">
            &nbsp;
          </span>
          <Button type="submit" disabled={pending || !form.formState.isDirty}>
            {t("common.save")}
          </Button>
        </div>
        <datalist id={zonesId}>
          {zones.map((z) => (
            <option key={z} value={z} />
          ))}
        </datalist>
      </form>
    </Form>
  );
}
