import { ProfileTabs, type ProfileTabGroup } from "@/components/shell/profile-tabs";

/** The partner's tabs, grouped the same way as the client's (spec 035). */
export const PARTNER_TAB_GROUPS: ProfileTabGroup[] = [
  {
    key: "observe",
    label: "Observar",
    tabs: [
      { seg: "", label: "Resumen" },
      { seg: "clients", label: "Clientes" },
      { seg: "audit", label: "Auditoría" },
    ],
  },
  {
    key: "configure",
    label: "Configurar",
    tabs: [
      // Spec 032: which console views and services this partner has.
      { seg: "modules", label: "Módulos" },
      { seg: "settings", label: "Configuración" },
      { seg: "knowledge", label: "Conocimiento" },
      // Spec 047 (T172, 55.2): the dry run and the switch of the new console.
      { seg: "console-v2", label: "Consola nueva" },
    ],
  },
  {
    key: "account",
    label: "Cuenta",
    tabs: [
      { seg: "team", label: "Equipo" },
      { seg: "money", label: "Facturas" },
      // Spec 047 (T172; 43.1, 46.5): «Construcción y pruebas» and the account currency.
      { seg: "limits", label: "Tope y moneda" },
    ],
  },
];

export function PartnerTabs({ partnerId }: { partnerId: string }) {
  return <ProfileTabs base={`/partners/${partnerId}`} label="Secciones del partner" groups={PARTNER_TAB_GROUPS} />;
}
