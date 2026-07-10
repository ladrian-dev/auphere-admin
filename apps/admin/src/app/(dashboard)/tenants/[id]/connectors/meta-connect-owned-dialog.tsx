"use client";

/**
 * "Conectar número propio" dialog — the manual WhatsApp connect for a
 * number under the portfolio that owns the Auphere app (Facelad).
 *
 * Meta's Embedded Signup only onboards *client* portfolios, so it refuses
 * Facelad's own number/catalog. Instead the operator pastes a permanent
 * System User token (with whatsapp_business_messaging +
 * whatsapp_business_management + catalog_management) plus the WABA / phone
 * / catalog ids, and the backend subscribes the webhook, persists the
 * token and upserts the channel with the catalog linked.
 *
 * The token is a secret: it goes straight to the backend (Fernet-encrypted)
 * and is never echoed back or kept client-side.
 */

import { Plug } from "lucide-react";
import { useState } from "react";
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

import { connectMetaOwnedNumberAction } from "./setup-actions";

export function MetaConnectOwnedDialog({ tenantId }: { tenantId: string }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState("");
  const [wabaId, setWabaId] = useState("");
  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [catalogId, setCatalogId] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token.trim() || !wabaId.trim()) {
      toast.error("Faltan datos", {
        description: "El System User token y el WABA ID son obligatorios.",
      });
      return;
    }
    setBusy(true);
    try {
      const result = await connectMetaOwnedNumberAction(tenantId, {
        system_user_token: token.trim(),
        waba_id: wabaId.trim(),
        phone_number_id: phoneNumberId.trim() || undefined,
        catalog_id: catalogId.trim() || undefined,
      });
      if (!result.ok) {
        toast.error("No se pudo conectar", { description: result.error });
        return;
      }
      // Clear the secret from component state immediately after use.
      setToken("");
      toast.success("WhatsApp conectado", {
        description: `Número ${result.data.display_phone_number}${
          result.data.catalog_id ? ` · catálogo ${result.data.catalog_id}` : ""
        }`,
      });
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (busy) return;
        setOpen(next);
      }}
    >
      <DialogTrigger
        render={
          <Button size="sm" variant="outline">
            <Plug className="h-3.5 w-3.5" strokeWidth={1.75} />
            Conectar número propio
          </Button>
        }
      />
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Conectar número propio (System User token)</DialogTitle>
          <DialogDescription>
            Para números bajo el portafolio dueño de la app (Facelad), donde el
            Embedded Signup no aplica. Pega un <strong>System User token</strong>{" "}
            permanente con permisos <code>whatsapp_business_messaging</code>,{" "}
            <code>whatsapp_business_management</code> y{" "}
            <code>catalog_management</code>. El token se guarda cifrado y no se
            vuelve a mostrar.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="owned-token">System User token</Label>
            <Input
              id="owned-token"
              type="password"
              placeholder="EAAxxxxxxxx…"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              autoComplete="off"
              disabled={busy}
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="owned-waba">WABA ID</Label>
              <Input
                id="owned-waba"
                placeholder="1012345…"
                value={wabaId}
                onChange={(e) => setWabaId(e.target.value)}
                autoComplete="off"
                disabled={busy}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="owned-pn">Phone number ID</Label>
              <Input
                id="owned-pn"
                placeholder="opcional — se deriva"
                value={phoneNumberId}
                onChange={(e) => setPhoneNumberId(e.target.value)}
                autoComplete="off"
                disabled={busy}
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="owned-catalog">Catalog ID (catálogo de Meta)</Label>
            <Input
              id="owned-catalog"
              placeholder="opcional — para tarjetas de producto"
              value={catalogId}
              onChange={(e) => setCatalogId(e.target.value)}
              autoComplete="off"
              disabled={busy}
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={busy}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Conectando…" : "Conectar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
