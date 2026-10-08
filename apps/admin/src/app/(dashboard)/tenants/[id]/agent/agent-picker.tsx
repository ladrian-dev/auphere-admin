"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { usePathname, useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import type { TenantAgent } from "@/lib/backend";

import { createTenantAgentAction } from "./actions";

const schema = z.object({
  name: z.string().trim().min(1, "Poné un nombre.").max(80, "Máximo 80 caracteres."),
});
type FormValues = z.infer<typeof schema>;

/**
 * Spec 030 (R14.1, R14.5): de qué agente del cliente es lo que se edita en
 * esta pestaña, en `?agent=` para que un enlace diga lo que enseña. Con un
 * solo agente no hay nada que elegir: solo «Nuevo agente». Un agente nuevo
 * nace sin versiones; su primera se guarda desde el editor o desde una
 * plantilla, y no contesta en ningún número hasta que se le asigne uno.
 */
export function AgentPicker({
  tenantId,
  agents,
  selectedId,
}: {
  tenantId: string;
  agents: TenantAgent[];
  /** The agent on screen; the principal when the URL names none. */
  selectedId: string | null;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const principal = agents.find((a) => a.is_principal) ?? null;
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { name: "" } });

  function go(id: string) {
    router.push(id && id !== principal?.id ? `${pathname}?agent=${encodeURIComponent(id)}` : pathname);
  }

  async function onSubmit(values: FormValues) {
    const result = await createTenantAgentAction(tenantId, values.name);
    if (!result.ok) {
      // The form keeps what was typed: only the reason changes.
      if (result.error === "name_taken") {
        form.setError("name", { message: "Ya hay un agente activo con ese nombre." });
      } else {
        toast.error("No se pudo crear el agente", { description: result.error });
      }
      return;
    }
    toast.success(`Agente «${result.data.name}» creado`, {
      description: "Aplicá una plantilla o guardá su primera versión desde el editor.",
    });
    setOpen(false);
    form.reset();
    go(result.data.id);
  }

  return (
    <div className="flex flex-wrap items-end gap-2" data-slot="agent-picker">
      {agents.length > 1 ? (
        <label className="grid gap-2 text-sm">
          <span className="text-muted-foreground">Agente</span>
          {/* Same height, border and focus ring as the admin's Input. */}
          <select
            value={selectedId ?? principal?.id ?? ""}
            onChange={(e) => go(e.target.value)}
            className="h-8 max-w-64 min-w-0 rounded-md border border-input bg-transparent px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 dark:bg-input/30"
          >
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
                {a.is_principal ? " · principal" : ""}
                {a.active_version === null ? " · sin publicar" : ""}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) form.reset();
        }}
      >
        <DialogTrigger render={<Button variant="outline">Nuevo agente</Button>} />
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Nuevo agente</DialogTitle>
            <DialogDescription>
              Con su propio prompt, herramientas y versiones. Nace sin versiones:
              guardá la primera desde el editor o aplicá una plantilla, y asignale
              un número para que conteste.
            </DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Nombre</FormLabel>
                    <FormControl>
                      <Input autoComplete="off" maxLength={80} {...field} />
                    </FormControl>
                    <FormDescription>Lo ven el partner y el cliente, por ejemplo «Ventas».</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <DialogFooter>
                <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
                  Cancelar
                </Button>
                <Button type="submit" disabled={form.formState.isSubmitting}>
                  {form.formState.isSubmitting ? "Creando…" : "Crear agente"}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
