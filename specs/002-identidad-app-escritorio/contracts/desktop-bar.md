# Contrato — la barra del puesto: estados, `preload` mínimo y almacén

> **Enmendado el 2026-09-15 por la spec 009**: el `preload` pasa de **seis a
> ocho** — `showApp` con la Historia 1 y `redeemCode` con la Historia 2 — y
> `BarAction` de cuatro a cinco con `volver_a_la_app`. La razón, con el
> precedente en contra que hubo que argumentar, está en
> [`specs/009-volver-y-entrar-desde-la-app/contracts/bar-preload.md`](../../009-volver-y-entrar-desde-la-app/contracts/bar-preload.md).
>
> **Lo que no cambia**: la lista sigue cerrada y declarada aquí, la vista de la
> consola sigue sin `preload`, y ninguna función toca `login`, `session`,
> `cookie` ni `token`.

La única superficie propia de la aplicación (R12). Vive en su propia
`WebContentsView`, partición `auphere-bar` (no persistente), con un `preload`
que la vista de la consola **no tiene**.

## Lo que expone `bar-preload.ts` (y nada más)

```ts
window.auphere = {
  getState(): Promise<BarState>;
  onState(cb: (s: BarState) => void): () => void;
  pair(code: string): Promise<void>;            // canjea; el resultado llega por onState
  unpair(): Promise<void>;                      // olvida la credencial; archivar es de la consola
  pickDirectory(clientRef: string): Promise<void>; // selector nativo + cuatro validaciones + declarar
  openInBrowser(url: string): Promise<void>;    // solo URLs del origen de la consola
  // ── enmienda de la spec 009 ──────────────────────────────────────────────
  showApp(): Promise<void>;                     // vuelve a la pantalla del equipo
  redeemCode(code: string): Promise<void>;      // canjea el código; el resultado llega por onState
};
```

`BarState`:

```ts
type BarState = {
  status: "sin_emparejar" | "emparejando" | "conectada" | "reconectando"
        | "sin_sesion" | "volver_a_emparejar" | "archivada_desde_consola"
        | "version_no_admitida";          // spec 008 — ver §Ampliación
  machine?: { displayName: string; hostname: string };
  pairedByOther?: boolean;               // Historia 5.1
  links: { clientRef: string; clientName: string; needsDirectory: boolean }[];
  lastError?: { code: string };          // se pinta como estado, nunca en rojo
  encryptionAvailable: boolean;          // false → no se guarda nada, y se dice
};
```

## Los siete estados, y qué se ve

| Estado | Texto de la barra | Acción disponible | Herramientas locales |
|---|---|---|---|
| `sin_emparejar` | «Esta máquina no está emparejada» | Introducir código | no |
| `emparejando` | «Comprobando el código…» | — | no |
| `conectada` | «MacBook de Luis · conectada» (+ «falta el directorio de N clientes» si aplica) | Directorios · Desemparejar (olvida la credencial; la barra dice «archívala desde la consola si no vas a volver») | **sí** |
| `reconectando` | «MacBook de Luis · reconectando» | — | no |
| `sin_sesion` | «Sin sesión · el puente está parado» | — | no |
| `volver_a_emparejar` | «Hay que volver a emparejar esta máquina» | Introducir código | no |
| `archivada_desde_consola` | «Archivada desde la consola» | Introducir código | no |
| `version_no_admitida` | «Esta versión ya no se admite · actualiza para seguir» | **Actualizar** | no |

Con `pairedByOther`: «Emparejada por otra persona · empareja la tuya» + Introducir
código. Nunca se muestra el nombre de la otra persona.

## Transiciones

```
sin_emparejar ──pair ok──▶ conectada ◀──latido ok── reconectando
      ▲                       │ red/5xx ────────────────▶ reconectando
      │                       │ cookie fuera ───────────▶ sin_sesion ──cookie misma persona──▶ conectada
      │                       │ 401 / 403 pairing_required ▶ volver_a_emparejar
      │                       │ 403 device_archived ──────▶ archivada_desde_consola
      └────── unpair ─────────┘
```

Fuera de `conectada` **no** se ofrecen herramientas locales (R12.3), y el latido
solo corre en `conectada` y `reconectando`.

## Lo que la cáscara le pide a la consola (y la página no sabe)

`GET /api/session/whoami` — ruta del BFF, mismo origen, con la cookie de la
partición humana, llamada **desde el proceso principal** al arrancar y en cada
cambio de la cookie `nexus-console.session`:

| Respuesta | Significado | Estado de la barra |
|---|---|---|
| `200 {user_id, partner_slug, locale}` | persona con pertenencia; la barra adopta `locale` | arranca si `user_id` tiene credencial guardada; si la tiene otra persona → `pairedByOther`; si nadie → `sin_emparejar` |
| `401` | sin sesión | `sin_sesion`, sin oferta de emparejar |
| `403 {"code": "no_membership"}` | sesión sin partner | `sin_sesion`, sin oferta de emparejar (R2.4) |

No devuelve nada más. La página cargada no participa.

## Almacén

`credential-store.ts`: `safeStorage.encryptString` → `userData/credentials.bin`;
mapa por `user_id`. Sin cifrado disponible, no se escribe y
`encryptionAvailable=false`. Desemparejar borra la entrada y detiene el latido; **no** llama a la plataforma —no hay
sexta operación—: la máquina queda `ausente` hasta que una persona la archive desde
`/workstation` (R11.2 enmendado, `tasks.md` T048).

## Diseño

- Altura 44 px, anclada abajo, hoja expandible para el código y los directorios.
- Tokens de `@nexus/ui` copiados en el build; cero hex; **no** `--color-fg-subtle`
  en texto de estado; **no** `--color-status-warning` con texto claro encima.
- Estética *terminal-bloomberg discreta*: monoespaciada solo para nombre de máquina
  y código; un acento para «conectada»; ningún estado en rojo.
- WCAG 2.2 AA: foco visible ≥ 2 px, objetivos ≥ 24 px, `prefers-reduced-motion`,
  `prefers-color-scheme`. Cinco estados de Hurff por vista de la hoja.

---

## Ampliación de la spec 008 — la actualización

Este contrato nació con **siete** estados y ahora tiene **ocho**. La ampliación
se escribe aquí y no en el código porque un test
(`bar-state.test.ts::son exactamente los del contrato`) compara la enumeración
contra esta lista: añadir uno sin tocar este documento pone el test en rojo, que
es exactamente lo que debe pasar.

### `version_no_admitida`

La plataforma exige una versión más nueva (`403 app_update_required` en el
latido). El puente **para**, pero:

- **La credencial sigue siendo válida.** No se olvida nada, no se desempareja y
  no se ofrece «introducir código»: mandaría a la persona a buscar por la consola
  un código que no arregla su problema. La única acción es **Actualizar**.
- **Se sale solo.** En cuanto la actualización se aplica, el siguiente latido
  pasa y la barra vuelve a `conectada`.
- `requiredVersion` acompaña al estado para poder decir **qué** versión hace
  falta, no sólo que la actual no vale.

Es la diferencia con `archivada_desde_consola` y `volver_a_emparejar`, que sí son
terminales y sí exigen emparejar de nuevo.

### `update`, que **no** es un estado

Además del octavo estado, `BarState` gana un campo `update?: { version, waiting }`
que dice si hay una versión descargada esperando. **Va aparte de `status` a
propósito**: son ortogonales —una máquina puede estar `conectada` **y** tener
una versión esperando— y meterlo en la enumeración obligaría a elegir cuál de las
dos cosas se pinta.

`waiting` distingue «lista, se instala al cerrar» de «esperando a que termine lo
que hay vivo». La segunda existe porque explica **por qué** la aplicación no se
está actualizando, que es la pregunta que alguien se hace cuando le dijeron que
había versión nueva y sigue viendo la vieja.

**Ausente significa que no hay nada que decir**: sin versión esperando, la barra
no pinta indicador apagado ni texto explicando lo que no hay (§V).
