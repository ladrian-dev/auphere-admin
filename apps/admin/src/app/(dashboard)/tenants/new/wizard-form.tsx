"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { Button } from "@/components/ui/button";
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
import {
  BusinessHoursPicker,
  type BusinessHoursValue,
} from "@/components/forms/business-hours-picker";

import { checkSlugAction, createTenantAction } from "./actions";

// Mirror of the backend Pydantic shape (apps/api/.../schemas/tenant.py
// TenantCreateIn). Keep these in sync — the slug regex and phone regex
// are duplicated client-side so the form gives instant feedback.
const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const E164_RE = /^\+[1-9]\d{1,14}$/;

const schema = z.object({
  slug: z
    .string()
    .min(2)
    .max(80)
    .regex(SLUG_RE, "Solo minúsculas, números y guiones (ej. mi-empresa)"),
  name: z.string().min(1).max(255),
  plan: z.enum(["essential", "pro", "business", "internal"]),
  market: z
    .string()
    .regex(/^[A-Za-z]{2}$/, "Código ISO de 2 letras (ej. CL)")
    .optional()
    .or(z.literal("")),
  timezone: z.string().min(1, "Requerido").max(64),
  owner_email: z
    .string()
    .email("Email inválido")
    .optional()
    .or(z.literal("")),
  owner_phone: z
    .string()
    .regex(E164_RE, "Formato E.164 internacional (ej. +56912345678)")
    .optional()
    .or(z.literal("")),
  cost_alert_threshold_usd_per_day: z.coerce
    .number()
    .positive("Debe ser positivo")
    .max(10000, "Cap es 10000"),
});

type FormValues = z.infer<typeof schema>;

const TIMEZONE_OPTIONS = [
  "America/Santiago",
  "America/Argentina/Buenos_Aires",
  "America/Lima",
  "America/Bogota",
  "America/Mexico_City",
  "Europe/Madrid",
  "UTC",
];

const PLAN_OPTIONS: { value: FormValues["plan"]; label: string }[] = [
  { value: "essential", label: "Esencial" },
  { value: "pro", label: "Pro" },
  { value: "business", label: "Business 360" },
  { value: "internal", label: "Internal (canary)" },
];

type SlugStatus =
  | { kind: "idle" }
  | { kind: "checking" }
  | { kind: "available" }
  | { kind: "taken" };

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="grid gap-4 border-t border-border pt-6 first:border-t-0 first:pt-0">
      <div className="grid gap-1">
        <h2
          className="text-[10px] font-mono uppercase text-muted-foreground"
          style={{ letterSpacing: "var(--tracking-eyebrow)" }}
        >
          {title}
        </h2>
        {description ? (
          <p className="text-xs text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

export function NewTenantWizard() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [, startTransition] = useTransition();
  const [slugStatus, setSlugStatus] = useState<SlugStatus>({ kind: "idle" });
  const [businessHours, setBusinessHours] = useState<BusinessHoursValue | null>(
    null,
  );

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      slug: "",
      name: "",
      plan: "pro",
      market: "CL",
      timezone: "America/Santiago",
      owner_email: "",
      owner_phone: "",
      cost_alert_threshold_usd_per_day: 40,
    },
  });

  // Debounced async slug check.
  const slugValue = useWatch({ control: form.control, name: "slug" });
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    if (!slugValue || !SLUG_RE.test(slugValue)) {
      setSlugStatus({ kind: "idle" });
      return;
    }
    setSlugStatus({ kind: "checking" });
    const handle = setTimeout(async () => {
      const result = await checkSlugAction(slugValue);
      setSlugStatus({ kind: result.available ? "available" : "taken" });
    }, 400);
    return () => clearTimeout(handle);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [slugValue]);

  async function onSubmit(values: FormValues) {
    if (slugStatus.kind === "taken") {
      form.setError("slug", { message: "Ese slug ya existe" });
      return;
    }
    setSubmitting(true);
    try {
      const result = await createTenantAction({
        slug: values.slug,
        name: values.name,
        plan: values.plan,
        market: values.market ? values.market.toUpperCase() : null,
        timezone: values.timezone,
        owner_email: values.owner_email || null,
        owner_phone: values.owner_phone || null,
        business_hours: businessHours,
        cost_alert_threshold_usd_per_day:
          values.cost_alert_threshold_usd_per_day,
      });
      if (result.kind === "error") {
        toast.error("No se pudo crear el tenant", {
          description: result.message,
        });
        return;
      }
      toast.success(`Tenant ${values.name} creado`, {
        description: "Próximo paso: conectar el canal de mensajería.",
      });
      startTransition(() => {
        router.replace(`/tenants/${result.tenantId}/connectors`);
        router.refresh();
      });
    } catch (err) {
      toast.error("Error inesperado", {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="flex flex-col gap-6"
        noValidate
      >
        <Section title="Identidad">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <FormField
              control={form.control}
              name="slug"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Slug</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      autoComplete="off"
                      placeholder="mi-empresa"
                      className="font-mono"
                    />
                  </FormControl>
                  <FormDescription className="flex items-center gap-2">
                    Identificador URL-safe del cliente.{" "}
                    {slugStatus.kind === "checking" && "Verificando…"}
                    {slugStatus.kind === "available" && (
                      <span className="text-green-700">Disponible.</span>
                    )}
                    {slugStatus.kind === "taken" && (
                      <span className="text-destructive">Ya existe.</span>
                    )}
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Nombre comercial</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      autoComplete="off"
                      placeholder="Mi Empresa S.A."
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        </Section>

        <Section
          title="Plan y localización"
          description="El plan determina el tier de costo. Mercado y zona horaria se usan para reportes y para el agente."
        >
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <FormField
              control={form.control}
              name="plan"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Plan</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Plan" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {PLAN_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
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
              name="market"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Mercado</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      maxLength={2}
                      placeholder="CL"
                      className="font-mono uppercase"
                    />
                  </FormControl>
                  <FormDescription>Código ISO 3166 (2 letras).</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="timezone"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Zona horaria</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Timezone" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {TIMEZONE_OPTIONS.map((tz) => (
                        <SelectItem key={tz} value={tz}>
                          {tz}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        </Section>

        <Section
          title="Contacto del owner"
          description="Opcionales. El email se usa para notificaciones; el WhatsApp para alertas y para mandar el link de consent OAuth."
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <FormField
              control={form.control}
              name="owner_email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email del owner</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      type="email"
                      placeholder="owner@empresa.com"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="owner_phone"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>WhatsApp del owner</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      placeholder="+56912345678"
                      className="font-mono"
                    />
                  </FormControl>
                  <FormDescription>
                    Formato E.164 internacional, con código de país y sin
                    espacios.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        </Section>

        <Section
          title="Operación"
          description="Umbral diario de gasto que dispara una alerta operativa al equipo de Auphere."
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <FormField
              control={form.control}
              name="cost_alert_threshold_usd_per_day"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Alerta de costo</FormLabel>
                  <FormControl>
                    <div className="relative">
                      <span
                        className="pointer-events-none absolute inset-y-0 left-3 grid place-items-center text-xs text-muted-foreground"
                        aria-hidden="true"
                      >
                        USD
                      </span>
                      <Input
                        {...field}
                        type="number"
                        inputMode="decimal"
                        min={0}
                        step={1}
                        className="font-mono pl-12"
                      />
                      <span
                        className="pointer-events-none absolute inset-y-0 right-3 grid place-items-center text-xs text-muted-foreground"
                        aria-hidden="true"
                      >
                        /día
                      </span>
                    </div>
                  </FormControl>
                  <FormDescription>Por defecto $40 (Pro tier).</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        </Section>

        <Section
          title="Horario de atención"
          description="Opcional. El agente lo recibe interpolado en su prompt cuando aplicás una plantilla."
        >
          <BusinessHoursPicker
            value={businessHours}
            onChange={setBusinessHours}
          />
        </Section>

        <div className="flex items-center justify-end gap-3 pt-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => router.back()}
            disabled={submitting}
          >
            Cancelar
          </Button>
          <Button
            type="submit"
            disabled={submitting || slugStatus.kind === "taken"}
          >
            {submitting ? "Creando…" : "Crear tenant"}
          </Button>
        </div>
      </form>
    </Form>
  );
}
