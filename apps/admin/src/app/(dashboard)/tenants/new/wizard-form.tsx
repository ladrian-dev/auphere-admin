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

/**
 * Form section with a Stripe-style two-column layout on wide screens:
 * the title + description on the left, the fields on the right inside a
 * 12-column grid. On mobile the header stacks above the fields. The
 * single 12-col module is what keeps every input/select aligned across
 * sections regardless of column count (2, 3, or mixed).
 */
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
    <section className="grid gap-6 border-t border-border pt-8 first:border-t-0 first:pt-0 md:grid-cols-[minmax(0,200px)_1fr] md:gap-x-10">
      <header className="flex flex-col gap-1.5">
        <h2
          className="text-[10px] font-mono uppercase text-muted-foreground"
          style={{ letterSpacing: "var(--tracking-eyebrow)" }}
        >
          {title}
        </h2>
        {description ? (
          <p className="text-xs leading-snug text-muted-foreground">
            {description}
          </p>
        ) : null}
      </header>
      <div className="grid grid-cols-12 gap-x-4 gap-y-5">{children}</div>
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
      // BUG-E2E-03: navigate to the new tenant's connectors page.
      // Calling ``router.refresh()`` right after ``router.replace()``
      // used to cancel the navigation — the refresh re-fetched the
      // CURRENT URL (still /tenants/new while the navigation was
      // in-flight) and overrode the route change. Replace alone fetches
      // the new route's RSC payload, so refresh is redundant AND
      // harmful. Drop the refresh and let Next.js handle it.
      startTransition(() => {
        router.replace(`/tenants/${result.tenantId}/connectors`);
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
          <FormField
            control={form.control}
            name="slug"
            render={({ field }) => (
              <FormItem className="col-span-12 md:col-span-6">
                <FormLabel>Slug</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    autoComplete="off"
                    placeholder="mi-empresa"
                    className="font-mono"
                  />
                </FormControl>
                <FormDescription className="flex items-center gap-1.5">
                  Identificador URL-safe del cliente.
                  {slugStatus.kind === "checking" && (
                    <span className="text-muted-foreground">Verificando…</span>
                  )}
                  {slugStatus.kind === "available" && (
                    <span className="text-[color:var(--color-primary-deep)]">
                      Disponible.
                    </span>
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
              <FormItem className="col-span-12 md:col-span-6">
                <FormLabel>Nombre comercial</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    autoComplete="off"
                    placeholder="Mi Empresa S.A."
                  />
                </FormControl>
                <FormDescription>Como aparece comercialmente.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </Section>

        <Section
          title="Plan y localización"
          description="El plan determina el tier de costo. Mercado y zona horaria se usan para reportes y para el agente."
        >
          <FormField
            control={form.control}
            name="plan"
            render={({ field }) => (
              <FormItem className="col-span-12 sm:col-span-6 md:col-span-4">
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
                <FormDescription>Tier de costo y features.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="market"
            render={({ field }) => (
              <FormItem className="col-span-6 sm:col-span-3 md:col-span-2">
                <FormLabel>Mercado</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    maxLength={2}
                    placeholder="CL"
                    className="font-mono uppercase"
                  />
                </FormControl>
                <FormDescription>ISO 3166.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="timezone"
            render={({ field }) => (
              <FormItem className="col-span-6 sm:col-span-3 md:col-span-6">
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
                <FormDescription>Reportes y prompt del agente.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </Section>

        <Section
          title="Contacto del owner"
          description="Opcionales. El email se usa para notificaciones; el WhatsApp para alertas y para mandar el link de consent OAuth."
        >
          <FormField
            control={form.control}
            name="owner_email"
            render={({ field }) => (
              <FormItem className="col-span-12 md:col-span-6">
                <FormLabel>Email del owner</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    type="email"
                    placeholder="owner@empresa.com"
                  />
                </FormControl>
                <FormDescription>Notificaciones operativas.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="owner_phone"
            render={({ field }) => (
              <FormItem className="col-span-12 md:col-span-6">
                <FormLabel>WhatsApp del owner</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    placeholder="+56912345678"
                    className="font-mono"
                  />
                </FormControl>
                <FormDescription>
                  E.164 con código de país, sin espacios.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </Section>

        <Section
          title="Operación"
          description="Umbral diario de gasto que dispara una alerta operativa al equipo de Auphere."
        >
          <FormField
            control={form.control}
            name="cost_alert_threshold_usd_per_day"
            render={({ field }) => (
              <FormItem className="col-span-12 md:col-span-5">
                <FormLabel>Alerta de costo</FormLabel>
                <FormControl>
                  <div className="relative">
                    <span
                      className="pointer-events-none absolute inset-y-0 left-3 grid place-items-center text-xs font-mono uppercase tracking-wide text-muted-foreground"
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
                      className="font-mono pl-12 pr-12"
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
        </Section>

        <Section
          title="Horario de atención"
          description="Opcional. El agente lo recibe interpolado en su prompt cuando aplicás una plantilla."
        >
          <div className="col-span-12">
            <BusinessHoursPicker
              value={businessHours}
              onChange={setBusinessHours}
            />
          </div>
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
