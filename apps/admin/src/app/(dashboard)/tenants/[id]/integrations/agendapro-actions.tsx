"use client";

import { useState, useTransition } from "react";
import { Activity, KeyRound } from "lucide-react";
import { toast } from "sonner";

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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type BootstrapResult =
  | { ok: true; data: { context_id: string; audit_log_id: string } }
  | { ok: false; error: string };

type HealthResult =
  | {
      ok: true;
      data: { healthy: boolean; needs_reauth: boolean; notes: string | null };
    }
  | { ok: false; error: string };

type BootstrapAction = (
  tenantId: string,
  body: { login: string; password: string; business_url?: string | null },
) => Promise<BootstrapResult>;

type HealthCheckAction = (tenantId: string) => Promise<HealthResult>;

export function AgendaProActions({
  tenantId,
  bootstrap,
  healthCheck,
}: {
  tenantId: string;
  bootstrap: BootstrapAction;
  healthCheck: HealthCheckAction;
}) {
  const [open, setOpen] = useState(false);
  const [pending, startTransition] = useTransition();

  function runHealthCheck() {
    startTransition(async () => {
      const result = await healthCheck(tenantId);
      if (!result.ok) {
        toast.error("Health check falló", { description: result.error });
        return;
      }
      const { healthy, needs_reauth, notes } = result.data;
      if (healthy) {
        toast.success("AgendaPro saludable", {
          description: notes ?? "Sesión válida.",
        });
      } else if (needs_reauth) {
        toast.warning("Re-auth requerida", {
          description: notes ?? "El re-login automático falló. Re-bootstrap manual.",
        });
      } else {
        toast.info("Health check completado", {
          description: notes ?? "Revisa el detalle en el log.",
        });
      }
    });
  }

  return (
    <div className="flex items-center gap-2">
      <Button
        variant="ghost"
        onClick={runHealthCheck}
        disabled={pending}
      >
        <Activity className="size-4" />
        {pending ? "Verificando…" : "Verificar"}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger
          render={
            <Button>
              <KeyRound className="size-4" />
              Bootstrap
            </Button>
          }
        />
        <DialogContent>
          <BootstrapForm
            tenantId={tenantId}
            bootstrap={bootstrap}
            onClose={() => setOpen(false)}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}

function BootstrapForm({
  tenantId,
  bootstrap,
  onClose,
}: {
  tenantId: string;
  bootstrap: BootstrapAction;
  onClose: () => void;
}) {
  const [pending, startTransition] = useTransition();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [businessUrl, setBusinessUrl] = useState("");

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!login || !password) {
      toast.error("Faltan datos", { description: "Email + contraseña requeridos." });
      return;
    }
    startTransition(async () => {
      const result = await bootstrap(tenantId, {
        login,
        password,
        business_url: businessUrl || null,
      });
      if (!result.ok) {
        toast.error("Bootstrap falló", { description: result.error });
        return;
      }
      toast.success("AgendaPro conectado", {
        description: `context_id ${result.data.context_id.slice(0, 12)}…`,
      });
      onClose();
    });
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-5">
      <DialogHeader>
        <DialogTitle>Bootstrap AgendaPro</DialogTitle>
        <DialogDescription>
          Una sola vez. Stagehand abre una sesión Browserbase con estas credenciales y guarda el
          context. Las credenciales viajan cifradas con Fernet.
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-2">
        <Label htmlFor="ap-login">Email</Label>
        <Input
          id="ap-login"
          type="email"
          autoComplete="off"
          value={login}
          onChange={(e) => setLogin(e.target.value)}
          required
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="ap-password">Contraseña</Label>
        <Input
          id="ap-password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="ap-url">
          URL del negocio <span className="text-muted-foreground text-xs">(opcional)</span>
        </Label>
        <Input
          id="ap-url"
          type="url"
          inputMode="url"
          placeholder="https://miempresa.agendapro.com"
          value={businessUrl}
          onChange={(e) => setBusinessUrl(e.target.value)}
        />
      </div>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose} disabled={pending}>
          Cancelar
        </Button>
        <Button type="submit" disabled={pending}>
          {pending ? "Conectando…" : "Conectar"}
        </Button>
      </DialogFooter>
    </form>
  );
}
