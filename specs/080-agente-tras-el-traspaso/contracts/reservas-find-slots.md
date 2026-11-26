# Contrato: `reservas.find_slots` (spec 080, requisito 3)

## Entrada

| Campo | Antes | Ahora |
|---|---|---|
| `date` | obligatorio | **opcional**. Sin él, se buscan los primeros horarios libres desde ahora. |
| `service_id`, `service_name`, `staff_id`, `staff_name`, `party_size` | igual | igual, también sin fecha |

## Salida con `date`

No cambia. `SlotOut.date` y `SlotOut.weekday` no se emiten.

## Salida sin `date`

```json
{
  "date": null,
  "searched_from": "2026-11-23",
  "searched_to": "2026-11-24",
  "closed": false,
  "why_closed": null,
  "slots": [
    {"date": "2026-11-23", "weekday": "monday", "time": "16:00", "staff": [{"id": "…", "name": "Jennifer"}]},
    {"date": "2026-11-23", "weekday": "monday", "time": "16:30", "staff": [{"id": "…", "name": "Jennifer"}]},
    {"date": "2026-11-24", "weekday": "tuesday", "time": "16:00", "staff": [{"id": "…", "name": "Jennifer"}]}
  ],
  "too_soon": ["2026-11-23 13:30"],
  "first_fit": null,
  "refused": null,
  "services": [],
  "staff": []
}
```

- Los horarios salen en orden cronológico; como máximo, **6**.
- `searched_to` es el último día recorrido: el día en que se llegó al tope o el último de la ventana (`agent_max_days_ahead`).
- Si no hay nada libre en la ventana, devuelve `slots: []`, `closed: false` y `why_closed: "none_in_window"`.
- `hours_missing`, `not_offered`, `not_bookable`, `no_staff`, `too_large` y `refused` se devuelven igual que con fecha, antes de recorrer los días.
- En Aforo, cada horario lleva `left`. `first_fit` queda nulo, porque ya se devuelve lo primero que cabe.

## Descripción para el modelo (resumen)

- **Sin `date`:** cuando el cliente no dice día o pide lo antes posible. Ofrece lo que llegue, en orden.
- **Con `date`:** cuando nombra un día.
- `first_fit` solo se menciona para Aforo.
- El resto (`too_soon`, `refused`) se mantiene.
