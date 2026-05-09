"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRouter } from "next/navigation";

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { SeedTemplate } from "@/lib/backend";

import { applySeedTemplateAction } from "./actions";

const schema = z.object({
  seed_template_ref: z.string().min(1),
  tenant_address: z.string().min(1, "Requerido").max(255),
  business_hours_label: z.string().min(1, "Requerido").max(120),
  agent_name: z.string().max(40).optional().or(z.literal("")),
  agent_tone: z.enum(["casual", "formal", "playful"]).optional(),
});

type FormValues = z.infer<typeof schema>;

export function ApplySeedTemplateButton({
  tenantId,
  tenantName,
  tenantTimezone,
  templates,
  hasActiveConfig,
}: {
  tenantId: string;
  tenantName: string;
  tenantTimezone: string;
  templates: SeedTemplate[];
  hasActiveConfig: boolean;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [, startTransition] = useTransition();

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      seed_template_ref: templates[0]?.name ?? "barbershop_v1",
      tenant_address: "",
      business_hours_label: "",
      agent_name: "",
      agent_tone: "casual",
    },
  });

  if (templates.length === 0) {
    return (
      <Button variant="outline" disabled>
        Sin plantillas disponibles
      </Button>
    );
  }

  async function onSubmit(values: FormValues) {
    setSubmitting(true);
    try {
      const placeholders: Record<string, unknown> = {
        "tenant.name": tenantName,
        "tenant.timezone": tenantTimezone,
        "tenant.address": values.tenant_address,
        "tenant.business_hours_label": values.business_hours_label,
      };
      if (values.agent_name && values.agent_name.length > 0) {
        placeholders["agent.name"] = values.agent_name;
      }
      if (values.agent_tone) {
        placeholders["agent.tone"] = values.agent_tone;
      }
      const result = await applySeedTemplateAction(tenantId, {
        seed_template_ref: values.seed_template_ref,
        placeholders,
      });
      if (!result.ok) {
        toast.error("No se pudo aplicar la plantilla", { description: result.error });
        return;
      }
      toast.success(`Versión ${result.data.version} creada (staged)`, {
        description: "Revisá el prompt y promové cuando esté ok.",
      });
      startTransition(() => {
        setOpen(false);
        form.reset();
        router.refresh();
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button variant={hasActiveConfig ? "outline" : "default"}>
            {hasActiveConfig ? "Aplicar otra plantilla" : "Aplicar plantilla inicial"}
          </Button>
        }
      />
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Aplicar seed template</DialogTitle>
          <DialogDescription>
            Renderea el prompt + tools whitelist + policies de la plantilla con los
            datos del tenant. La nueva versión queda <strong>staged</strong> — revisá
            antes de promover.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="flex flex-col gap-4"
            noValidate
          >
            <FormField
              control={form.control}
              name="seed_template_ref"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Plantilla</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {templates.map((t) => (
                        <SelectItem key={t.name} value={t.name}>
                          {t.display_name} ({t.name} · {t.version})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="tenant_address"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Dirección del local</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      placeholder="Av. Apoquindo 1234, Las Condes"
                      autoComplete="off"
                    />
                  </FormControl>
                  <FormDescription>
                    Aparece en el prompt como ubicación del negocio.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="business_hours_label"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Horario (texto humano)</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      placeholder="Lun-Sáb 10-19, Domingo cerrado"
                      autoComplete="off"
                    />
                  </FormControl>
                  <FormDescription>
                    Cómo el agente debe describir el horario por chat.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="agent_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Nombre del agente (opcional)</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        placeholder="Alex"
                        autoComplete="off"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="agent_tone"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Tono</FormLabel>
                    <Select
                      onValueChange={field.onChange}
                      value={field.value ?? "casual"}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="casual">Casual</SelectItem>
                        <SelectItem value="formal">Formal</SelectItem>
                        <SelectItem value="playful">Playful</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setOpen(false)}
                disabled={submitting}
              >
                Cancelar
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? "Aplicando…" : "Crear versión staged"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
