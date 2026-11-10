# Modelo de datos de la app — spec 044

La app **no guarda nada en disco** de lo que sigue (031: memoria de React Query
y nada más). Es el modelo que ven las pantallas, el que sale del adaptador
(`src/api/reservas.ts`) a partir del contrato (`contracts/app-needs.md`). Todo
pertenece al cliente que entra; quién ve qué lo decide la API (spec 043).

## Tipos

```ts
type Mode = "services" | "capacity";
type ResState = "pending" | "confirmed" | "arrived" | "done" | "noshow" | "cancelled";
type ResAction = "confirm" | "arrived" | "noshow" | "undo" | "cancel";
type Origin = "agent" | "person" | "walkin" | "waitlist";
type Channel = "whatsapp" | "phone" | "in_person";

/** Hora de pared del negocio. */
type LocalDate = `${number}-${number}-${number}`; // YYYY-MM-DD
type Minutes = number; // minutos desde las 00:00

type ResConfig = {
  mode: Mode;
  timezone: string;
  currency: string;          // CLP
  hours: { weekday: 1|2|3|4|5|6|7; open: Minutes; close: Minutes }[];
  hoursLabel: string | null;
  waitlist: { enabled: boolean; leadHours: number; editable: boolean };
  confirmation: { enabled: boolean; when: "24h" | "same_day_12" | "3h"; editable: boolean };
  services: { stepMin: number; team: Pro[]; catalog: Service[] } | null;
  capacity: CapacityConfig | null;
};

type Pro = { id: string; name: string; calendar: "google" | "none" };
type Service = { id: string; name: string; durationMin: number; price: number; proIds: string[] | null };

type CapacityConfig = {
  unit: string;              // «comensales»
  capacity: number;
  stayMin: number;
  maxParty: number;
  walkinReserved: number;
  shifts: { name: string; from: Minutes; to: Minutes; everyMin: number }[];
  closed: { weekday: number; shift: string | null }[];
  blocks: Block[];
  editable: boolean;
};

type Block = { id: string; date: LocalDate; shift: string | null; reason: string };

type Reservation = {
  id: string;
  date: LocalDate;
  start: Minutes;
  end: Minutes;
  state: ResState;
  customer: { name: string; phone: string | null };
  origin: Origin;
  channel: Channel;
  by: string | null;
  createdAt: string;
  arrivedAt: string | null;
  service: { id: string; name: string; durationMin: number; price: number } | null;
  pro: { id: string; name: string } | null;
  partySize: number | null;
  conflict: { source: "google"; label: string } | null;
  history: { at: string; text: string }[];
  actions: ResAction[];
};

type Slot = { date: LocalDate; time: Minutes; inside: number; capacity: number; blocked: string | null; closed: boolean };
type DayOccupancy = { date: LocalDate; pct: number | null; closed: boolean };
type FreeSlot = { time: Minutes; pro: { id: string; name: string } | null; left: number | null; full: boolean };

type WaitEntry = {
  id: string;
  name: string;
  phone: string | null;
  wants: { date: LocalDate | null; time: Minutes | null; partySize: number | null; service: string | null; pro: string | null; text: string | null };
  state: "waiting" | "offered" | "accepted";
  fits: boolean | null;
  offeredUntil: string | null;
  joinedBy: "agent" | "person";
  by: string | null;
  joinedAt: string;
};
```

## Lo que se calcula en el teléfono (puro, con test)

| Cálculo | Entrada | Regla |
|---|---|---|
| «Ahora» del negocio | `now` del servidor + tiempo transcurrido | D3 |
| Día cerrado | `hours` y el día de la semana | sin entrada = cerrado |
| Pasada | `end < ahora` el mismo día, o día anterior | se atenúa |
| Llega tarde | `pending`/`confirmed`, hoy, `ahora − start ≥ 15` y `ahora < start + estancia` | Aforo, R2.9 |
| Resumen del día | reservas del día | «N reservas · N sin confirmar» (sin canceladas) |
| Dentro ahora | `inside` de la franja en curso | Aforo |
| Próxima hora | Σ `partySize` con `start ∈ [ahora, ahora + 60)` y abierta | Aforo |
| Hoy en Reservas | las reservas abiertas de hoy desde ahora, las 3 primeras | R9.4 |
| Atención | reservas de hoy `pending` | R9.1 |
| Nivel de ocupación | `inside / capacity` | < 35, 35–60, 60–85, ≥ 85, lleno |
| Te alcanza hasta | `runs_out_on` o hoy + ⌊`days_left`⌋ | R13.1 |

## Estados de la reserva (vocabulario común de la KB)

| Estado | Píldora Servicios | Píldora Aforo | Tono |
|---|---|---|---|
| `pending` | Sin confirmar | Sin confirmar | aviso, con borde |
| `confirmed` | Confirmada | Confirmada | positivo |
| `arrived` | — | Llegó (o «Sin reserva» si `origin = walkin`) | oscuro (`brandGround`) |
| `done` | Atendida | Vino | neutro |
| `noshow` | No vino | No vino | peligro |
| `cancelled` | Cancelada | Cancelada | neutro, tachado no |
| (calculado) | Choca con Google | Llega tarde · N min | aviso |
