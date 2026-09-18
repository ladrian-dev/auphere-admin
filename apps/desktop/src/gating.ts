/**
 * Los cinco topes, y a dónde lleva cada uno — spec 010, Requisito 9.
 *
 * El hallazgo que esto cierra: **ninguno llevaba a ninguna parte**. Sin plan
 * decía «cambia de plan, en Cuenta» y Cuenta no tenía plan; el pago salía al
 * navegador y acababa en un 404; un cobro fallido no se mencionaba en toda la
 * aplicación; y «Actualizar» abría el directorio crudo del canal.
 *
 * La regla: cada tope termina en **una acción con destino exacto** o en el
 * **nombre del rol** a quien pedirla. Nunca en las dos, y nunca en ninguna —
 * que es lo que distingue llevar a la acción de explicar por qué no se puede.
 *
 * Puro: quién puede contratar lo dicen los permisos que ya viajan con la
 * sesión, y a dónde lleva cada tope es una tabla. Nada de esto necesita red.
 */

export const CAPS = ["sin_plan", "plan_lleno", "pool_agotado", "cobro_fallido", "version_no_admitida"] as const;
export type Cap = (typeof CAPS)[number];

/** A dónde lleva. Una sección del armazón, o una salida declarada al navegador. */
export type Destination =
  | { kind: "section"; section: "cuenta" | "puesto" | "teammate" }
  | { kind: "console"; path: string };

export type Gate =
  | {
      kind: "action";
      destination: Destination;
      /**
       * Si el tope se dice **antes** de rellenar nada (R9.3). Sin plan y con el
       * plan lleno, el formulario no se llega a ofrecer: descubrir el tope al
       * pulsar «Crear» después de escribir nombre, oficio y permisos es
       * exactamente lo que el requisito prohíbe.
       */
      before: boolean;
      /** Si resolverlo pasa por el navegador (R9.4). Nunca hay tarjeta aquí. */
      handoff: boolean;
      /** La clave del texto. Aquí no se incrusta copy. */
      clave: string;
    }
  | { kind: "ask"; role: string; clave: string };

/**
 * Quién puede resolver un tope de dinero. El nombre del **rol**, no «un
 * administrador»: en un partner con seis personas, «pídeselo a un
 * administrador» no dice a cuál.
 */
export function whoToAsk(cap: Cap): string {
  // Los cuatro topes de dinero los resuelve quien lleva la facturación.
  return cap === "version_no_admitida" ? "owner" : "billing";
}

/** ¿Esta persona puede contratar o comprar? */
function canPay(permissions: readonly string[]): boolean {
  return permissions.includes("billing:manage");
}

export function gateFor(cap: Cap, permissions: readonly string[]): Gate {
  // Actualizar la aplicación no es una compra: es la aplicación de esta persona
  // en su máquina, y no depende del permiso de facturación de nadie.
  if (cap === "version_no_admitida") {
    return {
      kind: "action",
      destination: { kind: "section", section: "puesto" },
      before: false,
      handoff: false,
      clave: "cap.version_no_admitida",
    };
  }

  // R9.2: sin permiso **no se ofrece la acción**. Un botón que va a rebotar en
  // un 403 es peor que decir a quién pedírselo.
  if (!canPay(permissions)) return { kind: "ask", role: whoToAsk(cap), clave: `cap.${cap}.ask` };

  return {
    kind: "action",
    destination: { kind: "section", section: "cuenta" },
    // Crear un teammate con el pool agotado es legítimo; lo que no se puede es
    // ponerlo a trabajar. Confundirlos sería bloquear de más.
    before: cap === "sin_plan" || cap === "plan_lleno",
    handoff: true,
    clave: `cap.${cap}`,
  };
}
