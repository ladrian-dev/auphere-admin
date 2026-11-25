"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import {
  Button,
  Callout,
  Checkbox,
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
  Label,
  NativeSelect,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@nexus/ui";
import {
  BusinessHoursPicker,
  type BusinessHoursValue,
} from "@/components/forms/business-hours-picker";
import type { MembershipPayer } from "@/lib/backend";

import { checkSlugAction, createTenantAction, finishSendOnlySetupAction } from "./actions";
import { DIRECT, sendOnlyPlan } from "./send-only-plan";

/** Spec 077: «Con agente» is today's path; «Solo envío por API» has no agent. */
type ClientKind = "agent" | "send";
export type PartnerOption = { id: string; name: string };

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

type SendErrors = { partner?: string; amount?: string; email?: string; payer?: string };

/** Fields only «Con agente» shows: a send-only client is created with their defaults. */
const AGENT_FIELDS = [
  "plan",
  "market",
  "timezone",
  "owner_email",
  "owner_phone",
  "cost_alert_threshold_usd_per_day",
] as const;
type AgentField = (typeof AGENT_FIELDS)[number];

/** Where focus goes for each send-only error, in the order they read on screen. */
const SEND_ERROR_TARGET: [keyof SendErrors, string][] = [
  ["partner", "#send-partner"],
  ["payer", 'input[name="send-payer"]:checked'],
  ["amount", "#send-amount"],
  ["email", "#send-email"],
];

const PARTNERS_UNREAD = "No se pudieron leer los partners: recarga la página antes de crear el cliente.";

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
      <header className="flex flex-col gap-2">
        <h2
          className="text-[10px] font-mono uppercase text-muted-foreground tracking-eyebrow"
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

export function NewTenantWizard({
  partners = [],
  partnersError = false,
}: {
  partners?: PartnerOption[];
  /** The partner list could not be read: a send-only client is not created blind. */
  partnersError?: boolean;
}) {
  const router = useRouter();
  // Spec 077 (T024): the kind of client, and what a send-only one still needs.
  const [kind, setKind] = useState<ClientKind>("agent");
  const [partner, setPartner] = useState<string>(DIRECT);
  const [requireMembership, setRequireMembership] = useState(false);
  const [payer, setPayer] = useState<MembershipPayer>("stripe");
  const [amount, setAmount] = useState("40,00");
  const [billingEmail, setBillingEmail] = useState("");
  // `focus`: the send checks are what stopped the submit, so their first
  // invalid field takes focus once the error is on screen (a screen reader
  // reads them together). When a field above failed too, the form focuses that.
  const [sendCheck, setSendCheck] = useState<{ errors: SendErrors; focus: boolean }>({
    errors: {},
    focus: false,
  });
  const sendErrors = sendCheck.errors;
  const setSendErrors = (errors: SendErrors, focus = false) => setSendCheck({ errors, focus });
  useEffect(() => {
    if (!sendCheck.focus) return;
    const target = SEND_ERROR_TARGET.find(([key]) => sendCheck.errors[key])?.[1];
    if (target) document.querySelector<HTMLElement>(target)?.focus();
  }, [sendCheck]);
  // An edited field drops its own error, like the form's other fields.
  function clearSendError(key: keyof SendErrors) {
    setSendCheck((prev) => {
      if (!prev.errors[key]) return prev;
      const errors = { ...prev.errors };
      delete errors[key];
      return { errors, focus: false };
    });
  }
  // «Con agente» fields typed before switching to «Solo envío»: kept here
  // while hidden (so they never block the submit) and put back on return.
  const agentDraft = useRef<{ values: Partial<FormValues>; hours: BusinessHoursValue | null } | null>(null);
  const isSend = kind === "send";
  const hasPartner = partner !== DIRECT;
  // Once «Recargar» brings the list, the error about not having it goes too.
  const partnerError = partnersError ? sendErrors.partner : undefined;
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

  // Spec 077: what a send-only client saves next is checked before it exists.
  function checkSendOnly() {
    const plan = isSend
      ? sendOnlyPlan({ partner, requireMembership, payer, amount, email: billingEmail })
      : null;
    // Without the partner list, «Auphere (directo)» may only be the one option left.
    const errors: SendErrors = {
      ...(isSend && partnersError ? { partner: PARTNERS_UNREAD } : {}),
      ...(plan && !plan.ok ? plan.errors : {}),
    };
    return { plan, errors };
  }

  // A field above failed: the send errors show in the same round, not after.
  function onInvalid() {
    setSendErrors(checkSendOnly().errors);
  }

  async function onSubmit(values: FormValues) {
    if (slugStatus.kind === "taken") {
      form.setError("slug", { message: "Ese slug ya existe" });
      return;
    }
    const { plan, errors } = checkSendOnly();
    if (Object.keys(errors).length > 0) {
      setSendErrors(errors, true);
      return;
    }
    setSendErrors({});
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
        // Only a send-only client sends the flag: «Con agente» stays as today.
        ...(isSend ? { send_only: true } : {}),
      });
      if (result.kind === "error") {
        toast.error("No se pudo crear el tenant", {
          description: result.message,
        });
        return;
      }
      if (plan?.ok) {
        // The client exists now: whatever fails next is said and finished
        // from its page, never by creating it again (the slug is taken).
        let notSaved: string[];
        try {
          ({ notSaved } = await finishSendOnlySetupAction(result.tenantId, plan.followUp));
        } catch {
          notSaved = ["el partner ni la membresía (la API no respondió)"];
        }
        if (notSaved.length > 0) {
          // Stays until closed: it names what the operator still has to do,
          // on the page where it is done.
          toast.warning(`Cliente ${values.name} creado, pero sin guardar ${notSaved.join(" ni ")}`, {
            description: "Complétalo aquí, en su Facturación.",
            duration: Infinity,
          });
        } else {
          toast.success(`Cliente ${values.name} creado`, {
            description: "Su Resumen dice qué falta para que su API envíe.",
          });
        }
        const next =
          notSaved.length > 0 ? `/tenants/${result.tenantId}/billing` : `/tenants/${result.tenantId}`;
        startTransition(() => {
          router.replace(next);
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
        router.replace(`/tenants/${result.tenantId}/channels/new`);
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
        onSubmit={form.handleSubmit(onSubmit, onInvalid)}
        className="flex flex-col gap-6"
        noValidate
      >
        <Section
          title="Tipo de cliente"
          description="«Con agente» sigue como hoy."
        >
          <fieldset className="col-span-12 grid gap-3 sm:grid-cols-2">
            <legend className="sr-only">Tipo de cliente</legend>
            <ChoiceCard
              name="client-kind"
              value="agent"
              checked={kind === "agent"}
              onSelect={() => {
                if (kind === "agent") return;
                setKind("agent");
                setSendErrors({});
                const draft = agentDraft.current;
                if (draft) {
                  for (const [f, v] of Object.entries(draft.values)) {
                    form.setValue(f as AgentField, v as never);
                  }
                  setBusinessHours(draft.hours);
                }
              }}
              title="Con agente"
              help="Un agente de IA atiende sus conversaciones."
            />
            <ChoiceCard
              name="client-kind"
              value="send"
              checked={kind === "send"}
              onSelect={() => {
                if (kind === "send") return;
                setKind("send");
                agentDraft.current = {
                  values: Object.fromEntries(AGENT_FIELDS.map((f) => [f, form.getValues(f)])),
                  hours: businessHours,
                };
                for (const f of AGENT_FIELDS) {
                  form.resetField(f);
                }
                setBusinessHours(null);
              }}
              title="Solo envío por API"
              help="Su sistema envía plantillas, como códigos. Sin agente."
            />
          </fieldset>
        </Section>

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
                <FormDescription className="flex items-center gap-2">
                  Identificador URL-safe del cliente.
                  {slugStatus.kind === "checking" && (
                    <span className="text-muted-foreground">Verificando…</span>
                  )}
                  {slugStatus.kind === "available" && (
                    <span className="text-primary-deep">
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

        {isSend ? (
          <>
            <Section
              title="Partner"
              description="Como hoy: con partner, va a su recibo; sin él, es cliente directo."
            >
              {partnersError ? (
                <Callout
                  tone="warning"
                  className="col-span-12"
                  action={
                    <Button type="button" variant="outline" size="sm" onClick={() => router.refresh()}>
                      Recargar
                    </Button>
                  }
                >
                  No se pudieron leer los partners; recarga antes de elegir.
                </Callout>
              ) : null}
              <div className="col-span-12 grid gap-2 md:col-span-6">
                <Label htmlFor="send-partner">Partner</Label>
                {/* Native: the closed select shows the partner's name, never its id. */}
                <NativeSelect
                  id="send-partner"
                  wrapperClassName="w-full"
                  aria-invalid={partnerError ? true : undefined}
                  aria-describedby={partnerError ? "send-partner-error" : undefined}
                  value={partner}
                  onChange={(e) => {
                    const next = e.target.value;
                    setPartner(next);
                    clearSendError("partner");
                    clearSendError("payer");
                    // The partner's balance does not exist without a partner.
                    if (next === DIRECT) setPayer("stripe");
                  }}
                >
                  <option value={DIRECT}>Auphere (directo)</option>
                  {partners.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </NativeSelect>
                {partnerError ? (
                  <p id="send-partner-error" role="alert" className="text-sm text-destructive">
                    {partnerError}
                  </p>
                ) : null}
              </div>
            </Section>

            <Section
              title="Membresía"
              description="Opcional. Sin membresía activa, su API no envía."
            >
              <div className="col-span-12 flex flex-col gap-4">
                <label htmlFor="send-require" className="flex min-h-6 items-center gap-2 text-sm font-medium">
                  <Checkbox
                    id="send-require"
                    checked={requireMembership}
                    onCheckedChange={(v) => setRequireMembership(v === true)}
                  />
                  Exigir una membresía mensual
                </label>
                {requireMembership ? (
                  <>
                    <fieldset
                      className="grid gap-3 sm:grid-cols-2"
                      aria-describedby={sendErrors.payer ? "send-payer-error" : undefined}
                    >
                      <legend className="mb-2 text-sm font-medium">Quién la paga</legend>
                      <ChoiceCard
                        name="send-payer"
                        value="stripe"
                        checked={payer === "stripe"}
                        onSelect={() => {
                          setPayer("stripe");
                          clearSendError("payer");
                        }}
                        title="El cliente, con tarjeta"
                        help="Paga por un enlace de Stripe y se renueva cada mes."
                      />
                      {hasPartner ? (
                        <ChoiceCard
                          name="send-payer"
                          value="partner_wallet"
                          checked={payer === "partner_wallet"}
                          onSelect={() => {
                            setPayer("partner_wallet");
                            clearSendError("payer");
                          }}
                          title="Del saldo del partner"
                          help="Se descuenta cada mes. Sin saldo, se corta."
                        />
                      ) : null}
                    </fieldset>
                    {sendErrors.payer ? (
                      <p id="send-payer-error" role="alert" className="text-sm text-destructive">
                        {sendErrors.payer}
                      </p>
                    ) : null}
                    <div className="grid gap-4 sm:grid-cols-[12rem_minmax(0,1fr)]">
                      <div className="grid gap-2">
                        <Label htmlFor="send-amount">Importe mensual (USD)</Label>
                        <Input
                          id="send-amount"
                          inputMode="decimal"
                          value={amount}
                          onChange={(e) => {
                            setAmount(e.target.value);
                            clearSendError("amount");
                          }}
                          aria-invalid={sendErrors.amount ? true : undefined}
                          aria-describedby={sendErrors.amount ? "send-amount-error" : undefined}
                          className="font-mono tabular-nums"
                        />
                        {sendErrors.amount ? (
                          <p id="send-amount-error" role="alert" className="text-sm text-destructive">
                            {sendErrors.amount}
                          </p>
                        ) : null}
                      </div>
                      {payer === "stripe" ? (
                        <div className="grid min-w-0 gap-2">
                          <Label htmlFor="send-email">Correo de facturación</Label>
                          <Input
                            id="send-email"
                            type="email"
                            autoComplete="off"
                            placeholder="facturacion@empresa.com"
                            value={billingEmail}
                            onChange={(e) => {
                              setBillingEmail(e.target.value);
                              clearSendError("email");
                            }}
                            aria-invalid={sendErrors.email ? true : undefined}
                            aria-describedby={sendErrors.email ? "send-email-error" : undefined}
                          />
                          {sendErrors.email ? (
                            <p id="send-email-error" role="alert" className="text-sm text-destructive">
                              {sendErrors.email}
                            </p>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                    <p className="text-sm text-pretty text-muted-foreground">
                      {payer === "partner_wallet"
                        ? "Al crear el cliente se cobra el primer mes del saldo del partner. Lo de Meta lo paga el cliente aparte, en su cuenta."
                        : "El enlace de pago se crea desde su Facturación. Lo de Meta lo paga el cliente aparte, en su cuenta."}
                    </p>
                  </>
                ) : null}
              </div>
            </Section>
          </>
        ) : (
          <>
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
          </>
        )}

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
            {submitting ? "Creando…" : isSend ? "Crear cliente" : "Crear tenant"}
          </Button>
        </div>
      </form>
    </Form>
  );
}

/** A radio drawn as a card: native, so arrows move between the options. */
function ChoiceCard({
  name,
  value,
  checked,
  onSelect,
  title,
  help,
}: {
  name: string;
  value: string;
  checked: boolean;
  onSelect: () => void;
  title: string;
  help: string;
}) {
  return (
    <label className="flex min-w-0 cursor-pointer items-start gap-3 rounded-md border border-input p-3 text-sm transition-colors has-[:checked]:border-primary has-[:checked]:ring-1 has-[:checked]:ring-primary has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring motion-reduce:transition-none">
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={onSelect}
        className="mt-1 size-4 shrink-0 accent-primary"
      />
      <span className="grid min-w-0 gap-1">
        <span className="font-medium">{title}</span>
        <span className="text-xs text-pretty text-muted-foreground">{help}</span>
      </span>
    </label>
  );
}
