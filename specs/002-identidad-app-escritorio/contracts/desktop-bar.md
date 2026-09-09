# Contrato — la barra del puesto: estados, `preload` mínimo y almacén

La única superficie propia de la aplicación (R12). Vive en su propia
`WebContentsView`, partición `auphere-bar` (no persistente), con un `preload`
que la vista de la consola **no tiene**.

## Lo que expone `bar-preload.ts` (y nada más)

```ts
window.auphere = {
  getState(): Promise<BarState>;
  onState(cb: (s: BarState) => void): () => void;
  pair(code: string): Promise<void>;            // canjea; el resultado llega por onState
  unpair(): Promise<void>;                      // olvida la credencial y archiva
  pickDirectory(clientRef: string): Promise<void>; // selector nativo + cuatro validaciones + declarar
  openInBrowser(url: string): Promise<void>;    // solo URLs del origen de la consola
};
```

`BarState`:

```ts
type BarState = {
  status: "sin_emparejar" | "emparejando" | "conectada" | "reconectando"
        | "sin_sesion" | "volver_a_emparejar" | "archivada_desde_consola";
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
| `conectada` | «MacBook de Luis · conectada» (+ «falta el directorio de N clientes» si aplica) | Directorios · Desemparejar | **sí** |
| `reconectando` | «MacBook de Luis · reconectando» | — | no |
| `sin_sesion` | «Sin sesión · el puente está parado» | — | no |
| `volver_a_emparejar` | «Hay que volver a emparejar esta máquina» | Introducir código | no |
| `archivada_desde_consola` | «Archivada desde la consola» | Introducir código | no |

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

## Almacén

`credential-store.ts`: `safeStorage.encryptString` → `userData/credentials.bin`;
mapa por `user_id`. Sin cifrado disponible, no se escribe y
`encryptionAvailable=false`. Desemparejar borra la entrada.

## Diseño

- Altura 44 px, anclada abajo, hoja expandible para el código y los directorios.
- Tokens de `@nexus/ui` copiados en el build; cero hex; **no** `--color-fg-subtle`
  en texto de estado; **no** `--color-status-warning` con texto claro encima.
- Estética *terminal-bloomberg discreta*: monoespaciada solo para nombre de máquina
  y código; un acento para «conectada»; ningún estado en rojo.
- WCAG 2.2 AA: foco visible ≥ 2 px, objetivos ≥ 24 px, `prefers-reduced-motion`,
  `prefers-color-scheme`. Cinco estados de Hurff por vista de la hoja.
