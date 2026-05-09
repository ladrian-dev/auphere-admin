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
import { Textarea } from "@/components/ui/textarea";

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
    .regex(SLUG_RE, "Solo minúsculas, números y guiones (ej. cultor-barber)"),
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
    .regex(E164_RE, "Formato E.164 (ej. +56911112222)")
    .optional()
    .or(z.literal("")),
  cost_alert_threshold_usd_per_day: z.coerce
    .number()
    .positive("Debe ser positivo")
    .max(10000, "Cap es 10000"),
  business_hours_json: z
    .string()
    .optional()
    .refine(
      (v) => {
        if (!v || v.trim() === "") return true;
        try {
          JSON.parse(v);
          return true;
        } catch {
          return false;
        }
      },
      { message: "JSON inválido" },
    ),
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

export function NewTenantWizard() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [, startTransition] = useTransition();
  const [slugStatus, setSlugStatus] = useState<SlugStatus>({ kind: "idle" });

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
      business_hours_json: "",
    },
  });

  // Debounced async slug check. The POST has a backstop, but giving the
  // form fast green/red feedback saves Lee from re-typing 6 fields after
  // a 409. ``useWatch`` (vs ``form.watch()``) plays nice with the React
  // Compiler — ``watch()`` returns a non-memoizable function.
  const slugValue = useWatch({ control: form.control, name: "slug" });
  useEffect(() => {
    // The slug status is genuinely derived from a network probe, so the
    // effect's setState calls are intentional. The default lint rule
    // suggests deriving state, but that doesn't apply when the source is
    // an external system (the backend uniqueness check).
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
      const businessHours = values.business_hours_json
        ? (JSON.parse(values.business_hours_json) as Record<string, unknown>)
        : null;
      const result = await createTenantAction({
        slug: values.slug,
        name: values.name,
        plan: values.plan,
        market: values.market ? values.market.toUpperCase() : null,
        timezone: values.timezone,
        owner_email: values.owner_email || null,
        owner_phone: values.owner_phone || null,
        business_hours: businessHours,
        cost_alert_threshold_usd_per_day: values.cost_alert_threshold_usd_per_day,
      });
      if (result.kind === "error") {
        toast.error("No se pudo crear el tenant", { description: result.message });
        return;
      }
      toast.success(`Tenant ${values.name} creado`, {
        description: "Próximo paso: conectar WhatsApp.",
      });
      startTransition(() => {
        router.replace(`/tenants/${result.tenantId}/integrations`);
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
      <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-6" noValidate>
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
                    placeholder="cultor-barber"
                    className="font-mono"
                  />
                </FormControl>
                <FormDescription className="flex items-center gap-2">
                  Identificador URL-safe. {slugStatus.kind === "checking" && "Verificando…"}
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
                  <Input {...field} autoComplete="off" placeholder="Cultor Barber" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

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
                  <Input {...field} maxLength={2} placeholder="CL" className="font-mono" />
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

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <FormField
            control={form.control}
            name="owner_email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Email del owner (opcional)</FormLabel>
                <FormControl>
                  <Input {...field} type="email" placeholder="diego@cultorbarber.cl" />
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
                <FormLabel>WhatsApp del owner (opcional)</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="+56911112222" className="font-mono" />
                </FormControl>
                <FormDescription>Formato E.164 — usado para alertas operativas.</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="cost_alert_threshold_usd_per_day"
          render={({ field }) => (
            <FormItem className="max-w-xs">
              <FormLabel>Alerta de costo (USD/día)</FormLabel>
              <FormControl>
                <Input
                  {...field}
                  type="number"
                  inputMode="decimal"
                  min={0}
                  step={1}
                  className="font-mono"
                />
              </FormControl>
              <FormDescription>Default $40 (Pro tier).</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="business_hours_json"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Horario de atención (opcional, JSON)</FormLabel>
              <FormControl>
                <Textarea
                  {...field}
                  rows={5}
                  className="font-mono text-xs"
                  placeholder={`{\n  "monday": "10:00-19:00",\n  "saturday": "10:00-18:00",\n  "sunday": "closed"\n}`}
                />
              </FormControl>
              <FormDescription>
                Formato libre. El agente lo recibe como string render del template.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="flex items-center justify-end gap-3 pt-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => router.back()}
            disabled={submitting}
          >
            Cancelar
          </Button>
          <Button type="submit" disabled={submitting || slugStatus.kind === "taken"}>
            {submitting ? "Creando…" : "Crear tenant"}
          </Button>
        </div>
      </form>
    </Form>
  );
}
