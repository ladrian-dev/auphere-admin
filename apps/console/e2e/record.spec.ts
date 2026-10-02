import { expect, test, type Page } from "@playwright/test";

/**
 * Spec 017 · iteración 1 — la ficha de cliente, recorrida sobre la app real.
 *
 * Lo que fija esta suite es lo que un partner ve y puede hacer: qué falta
 * para que el cliente atienda, un solo botón que lo resuelve, las diez
 * pestañas en tres grupos, el menú «Más» y el borrador publicable desde
 * cualquier pestaña.
 *
 * El reparto por rol está clavado en los módulos puros (`client-nav-model`,
 * `client-header-model`, `lifecycle-status`), que los cubren todos sin
 * montar React. Aquí se recorre con el propietario, que es el único login
 * que el arnés siembra, y con los otros dos **solo si** el entorno trae sus
 * credenciales: `E2E_BUILDER_EMAIL`/`_PASSWORD` y `E2E_ANALYST_EMAIL`/
 * `_PASSWORD`. Sin ellas el caso se salta en voz alta, nunca en silencio.
 */

async function firstClientRef(page: Page): Promise<string> {
  await page.goto("/clients");
  const link = page.locator('a[href^="/clients/"]:not([href="/clients/new"])').first();
  await expect(link).toBeVisible();
  const href = await link.getAttribute("href");
  const ref = href?.split("/clients/")[1]?.split("/")[0];
  if (!ref) throw new Error("no client to walk — seed one first");
  return decodeURIComponent(ref);
}

/** Entra con otras credenciales en un contexto limpio. */
async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByRole("textbox", { name: /correo|e-mail|email/i }).fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: /entrar|sign in|iniciar/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 90_000 });
}

const GROUPS = [/observar|observe/i, /configurar|configure/i, /conectar|connect/i];

test.describe("spec 017 · la ficha de cliente", () => {
  test("la cabecera dice qué falta y ofrece un solo botón", async ({ page }) => {
    const ref = await firstClientRef(page);
    await page.goto(`/clients/${encodeURIComponent(ref)}`);
    await expect(page.locator("main#main")).toBeVisible();
    // La rama depende de si el cliente ya atiende, así que hay que esperar a
    // que la página esté entera antes de decidirla: contar antes de hidratar
    // es contar otra cosa.
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await expect(page.getByRole("navigation", { name: /sección de la ficha|record section/i })).toBeVisible();

    const setup = page.getByRole("navigation", { name: /puesta en marcha|getting started/i });
    const serving = (await setup.count()) === 0;

    if (serving) {
      // Ya atiende: la puesta en marcha desaparece, que es la regla.
      await expect(page.getByText(/siguiente paso|next step/i)).toHaveCount(0);
    } else {
      // Los cuatro pasos, cada uno con su nombre, y ninguno como ordinal:
      // se pueden hacer en cualquier orden.
      for (const step of [/agente|agent/i, /canal|channel/i, /saldo|balance/i, /activación|activation/i]) {
        await expect(setup.getByText(step).first()).toBeVisible();
      }
      // Un solo botón primario en el bloque, el del paso pendiente.
      const section = page.locator("section", { has: setup });
      await expect(section.getByText(/siguiente paso|next step/i)).toBeVisible();
    }

    // El crédito está en la cabecera, como barra o como su ausencia dicha.
    await expect(
      page.getByText(/quedan .* US\$|left|sin saldo asignado|no balance assigned/i).first(),
    ).toBeVisible();
  });

  test("las pestañas viven en tres grupos y ninguna desaparece", async ({ page }) => {
    const ref = await firstClientRef(page);
    await page.goto(`/clients/${encodeURIComponent(ref)}`);
    const nav = page.getByRole("navigation", { name: /sección de la ficha|record section/i });
    await expect(nav).toBeVisible();
    for (const group of GROUPS) await expect(nav.getByText(group)).toBeVisible();

    // Nueve. El recuento y las redirecciones que lo explican tienen su
    // propio caso más abajo; aquí lo que importa son los tres grupos.
    const links = nav.getByRole("link");
    await expect(links).toHaveCount(9);
    // Exactamente una es la actual.
    await expect(nav.locator('a[aria-current="page"]')).toHaveCount(1);
  });

  test("«Más» es el mismo control en el mismo sitio, y no ofrece eliminar antes de archivar", async ({ page }) => {
    const ref = await firstClientRef(page);
    await page.goto(`/clients/${encodeURIComponent(ref)}`);
    const more = page.getByRole("button", { name: /más acciones|more actions/i });
    await expect(more).toBeVisible();
    await more.click();
    const menu = page.getByRole("menu");
    await expect(menu.getByText(/archivar|archive/i).first()).toBeVisible();
    await expect(menu.getByText(/copiar referencia|copy reference/i)).toBeVisible();
    // Eliminar solo se ofrece archivado: un botón que contesta «archiva
    // primero» es una trampa, no una afordancia.
    const status = await page.getByRole("main").innerText();
    if (!/archivado|archived/i.test(status.slice(0, 400))) {
      await expect(menu.getByText(/^eliminar|^delete/i)).toHaveCount(0);
    }
    await page.keyboard.press("Escape");
  });

  test("el borrador se ve y se revisa desde cualquier pestaña", async ({ page }) => {
    const ref = await firstClientRef(page);
    const base = `/clients/${encodeURIComponent(ref)}`;
    await page.goto(base);
    const bar = page.getByTestId("draft-bar");
    test.skip((await bar.count()) === 0, "este cliente no tiene borrador pendiente");

    // La barra vive en el layout: sigue ahí en una pestaña que no es Agente.
    await page.goto(`${base}/conversations`);
    await expect(page.getByTestId("draft-bar")).toBeVisible();
    await expect(page.getByTestId("draft-bar")).toContainText(/cambios sin publicar|unpublished changes/i);

    // Y la pestaña donde vive el cambio lo dice con su punto.
    const nav = page.getByRole("navigation", { name: /sección de la ficha|record section/i });
    await expect(nav.getByRole("img", { name: /cambios sin publicar|unpublished changes/i }).first()).toBeVisible();

    // Revisar abre la hoja, que trae el diff de verdad y no publica sola.
    await page.getByRole("button", { name: /revisar y publicar|review and publish/i }).click();
    const sheet = page.getByRole("dialog");
    await expect(sheet).toBeVisible();
    await expect(sheet).toContainText(/publicar la versión|publish version/i);
    // Una tabla por pantalla que cambió, así que puede haber varias: desde
    // la iteración 2, tocar Ajustes y Capacidades da dos bloques. Lo que se
    // afirma es que el diff está, no cuántos grupos trae.
    await expect(sheet.getByRole("columnheader", { name: /antes|before/i }).first()).toBeVisible();
    await expect(sheet.getByRole("columnheader", { name: /ahora|now/i }).first()).toBeVisible();
    await page.getByRole("button", { name: /^cancelar$|^cancel$/i }).click();
    await expect(sheet).toHaveCount(0);
  });

  for (const destino of ["capabilities", "integrations"] as const) {
    test(`«${destino}» es su propia pantalla`, async ({ page }) => {
      const ref = await firstClientRef(page);
      await page.goto(`/clients/${encodeURIComponent(ref)}/${destino}`);
      await expect(page).toHaveURL(new RegExp(`/clients/${ref}/${destino}$`));
      await expect(page.locator("main#main")).toBeVisible();
    });
  }

  test("el Resumen contesta las cuatro preguntas sin abrir nada", async ({ page }) => {
    // Spec 018 (R1): lo que el owner pidió — saber cómo va un cliente sin
    // recorrer la ficha. Se comprueba que las cuatro respuestas están en la
    // misma pantalla, no que estén bonitas.
    const ref = await firstClientRef(page);
    await page.goto(`/clients/${encodeURIComponent(ref)}`);
    const main = page.locator("main#main");
    for (const bloque of [
      /Atendiendo|Sin atender|Answering|Not answering/,
      /Saldo y consumo|Balance and usage/,
      /Conversaciones|Conversations/,
      /Lo que tiene conectado|What it has connected/,
      /Datos del cliente|Client details/,
    ]) {
      await expect(main.getByText(bloque).first()).toBeVisible();
    }
  });

  test("la ficha tiene nueve pestañas, y las dos retiradas siguen llevando a alguna parte", async ({ page }) => {
    const ref = await firstClientRef(page);
    const nav = page.getByRole("navigation", { name: /sección de la ficha|record section/i });

    await page.goto(`/clients/${encodeURIComponent(ref)}`);
    await expect(nav.getByRole("link")).toHaveCount(9);

    // Spec 018 (R2.3, R3.3): las URLs viejas están en correos y marcadores.
    // La redirección la resuelve el servidor y puede abortar la navegación
    // inicial, así que lo que se afirma es dónde se acaba.
    for (const [vieja, destino] of [
      ["settings", ""],
      ["agent/settings", "/agent"],
    ] as const) {
      await page
        .goto(`/clients/${encodeURIComponent(ref)}/${vieja}`, { waitUntil: "commit" })
        .catch(() => undefined);
      await page.waitForURL(new RegExp(`/clients/${ref}${destino}$`), { timeout: 30_000 });
      await expect(page.locator("main#main")).toBeVisible();
    }
    // Y los ajustes del agente se leen dentro de «Agente».
    await expect(page.getByText(/Identidad|Identity/).first()).toBeVisible();
  });

  test("buscar, filtrar y compartir el enlace lleva a lo mismo", async ({ page }) => {
    // Spec 018 (R4.1–R4.4), el recorrido entero de la iteración 2. Lo que
    // se comprueba no es que el filtro funcione —eso lo cubren los tests de
    // componente— sino que **el estado está en la dirección**: que copiar el
    // enlace y abrirlo en otra pestaña enseña lo mismo, y que «atrás»
    // deshace el filtro en vez de salir de la pantalla.
    const ref = await firstClientRef(page);
    const base = `/clients/${encodeURIComponent(ref)}/capabilities`;
    await page.goto(base);
    await expect(page.locator("main#main")).toBeVisible();

    // 1 · Buscar. El contador se mueve y la dirección recoge lo tecleado,
    // sin apilar una entrada de historia por letra.
    const buscador = page.getByRole("searchbox", { name: /Buscar en la lista|Search the list/ });
    await buscador.fill("cita");
    await page.waitForURL(/[?&]q=cita/, { timeout: 15_000 });

    // 2 · Filtrar por categoría: eso sí es una navegación.
    const pastilla = page.getByRole("link", { name: /·\s\d+$/ }).first();
    const nombrePastilla = (await pastilla.textContent())?.split(" ·")[0] ?? "";
    await pastilla.click();
    await page.waitForURL(/[?&]cat=/, { timeout: 15_000 });
    await expect(pastilla).toHaveAttribute("aria-current", "true");

    // 3 · Compartir el enlace: otra pestaña, la misma pantalla.
    const compartido = page.url();
    const otra = await page.context().newPage();
    await otra.goto(compartido);
    await expect(otra.locator("main#main")).toBeVisible();
    await expect(otra.getByRole("searchbox", { name: /Buscar en la lista|Search the list/ })).toHaveValue("cita");
    await expect(otra.getByRole("link", { name: new RegExp(`^${nombrePastilla} ·`) })).toHaveAttribute(
      "aria-current",
      "true",
    );
    await otra.close();

    // 4 · Atrás deshace **el filtro**, no la búsqueda letra a letra.
    await page.goBack();
    await page.waitForURL((url) => !url.search.includes("cat="), { timeout: 15_000 });
    await expect(page.locator("main#main")).toBeVisible();
  });

  for (const vieja of ["tools", "skills"] as const) {
    test(`«${vieja}» sigue llevando a alguna parte: redirige a Capacidades`, async ({ page }) => {
      // Spec 017 (R5.1): las dos pantallas se fundieron, pero sus URLs están
      // en correos, marcadores y capturas. Quien abra una tiene que acabar
      // donde está lo que buscaba, no en un 404.
      //
      // La redirección la resuelve el servidor y puede abortar la navegación
      // inicial —comportamiento normal de Next—, así que lo que se afirma es
      // dónde se acaba, no qué devolvió el primer `goto`.
      const ref = await firstClientRef(page);
      await page
        .goto(`/clients/${encodeURIComponent(ref)}/${vieja}`, { waitUntil: "commit" })
        .catch(() => undefined);
      await page.waitForURL(new RegExp(`/clients/${ref}/capabilities$`), { timeout: 30_000 });
      await expect(page.locator("main#main")).toBeVisible();
    });
  }

  test("encender una capacidad se guarda sola y la barra de borrador lo recoge", async ({ page }) => {
    // Spec 017 (R5.4): el recorrido entero de la iteración 2 — un clic
    // guarda, sin botón «Guardar», y el cambio aparece en la barra que
    // lleva a publicar desde cualquier pestaña.
    const ref = await firstClientRef(page);
    await page.goto(`/clients/${encodeURIComponent(ref)}/capabilities`);

    const conmutadores = page.getByRole("switch");
    const primero = conmutadores.first();
    await expect(primero).toBeVisible();
    const antes = await primero.getAttribute("aria-checked");

    await primero.click();
    // Un solo clic basta: no hay que buscar un «Guardar» después. El nombre
    // va anclado por los dos lados porque una **habilidad** puede llamarse
    // «Guardar las preferencias del cliente», y su tarjeta es un botón: sin
    // el ancla, el caso se cae según qué cliente salga primero.
    await expect(page.getByRole("button", { name: /^(Guardar|Save)$/ })).toHaveCount(0);
    await expect(primero).toHaveAttribute("aria-checked", antes === "true" ? "false" : "true");

    // Y el cambio no se queda en esta pantalla: la barra de borrador lo dice
    // y ofrece publicar.
    await expect(
      page.getByRole("button", { name: /revisar y publicar|review and publish/i }),
    ).toBeVisible({ timeout: 15_000 });

    // Se deja como estaba: este cliente lo comparten los demás tests.
    await primero.click();
    await expect(primero).toHaveAttribute("aria-checked", antes ?? "false");
  });

  for (const role of ["builder", "analyst"] as const) {
    test(`la ficha vista por un ${role}`, async ({ browser }) => {
      const email = process.env[`E2E_${role.toUpperCase()}_EMAIL`];
      const password = process.env[`E2E_${role.toUpperCase()}_PASSWORD`];
      test.skip(!email || !password, `sin credenciales de ${role}: define E2E_${role.toUpperCase()}_EMAIL y _PASSWORD`);

      const context = await browser.newContext({ storageState: undefined });
      const page = await context.newPage();
      try {
        await signIn(page, email!, password!);
        const ref = await firstClientRef(page);
        await page.goto(`/clients/${encodeURIComponent(ref)}`);
        const nav = page.getByRole("navigation", { name: /sección de la ficha|record section/i });
        await expect(nav).toBeVisible();

        // El menú existe para todos, en el mismo sitio.
        await expect(page.getByRole("button", { name: /más acciones|more actions/i })).toBeVisible();

        if (role === "analyst") {
          // Sin Playground, y sin un botón que contestaría 403.
          await expect(nav.getByRole("link", { name: /playground/i })).toHaveCount(0);
          await expect(page.getByRole("button", { name: /revisar y publicar|review and publish/i })).toHaveCount(0);
        } else {
          await expect(nav.getByRole("link", { name: /playground/i })).toHaveCount(1);
        }
      } finally {
        await context.close();
      }
    });
  }
});
