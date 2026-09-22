"use client";

/**
 * Cómo se pinta el texto de un mensaje — spec 013, Requisito 2.
 *
 * **El único sitio del paquete que lo hace**, y por eso todo lo que sigue vale
 * a la vez para la aplicación de escritorio y para la consola.
 *
 * ## Por qué `react-markdown` y no un renderizador que devuelva HTML
 *
 * No es el peso: es que `marked` y `markdown-it` devuelven **una cadena de
 * HTML**, y pintarla en React obliga a `dangerouslySetInnerHTML`. Entonces «no
 * se ejecuta nada de lo que venga dentro del mensaje» (R2.3) pasa a depender de
 * acertar con un sanitizador — una lista negra, y las listas negras se escapan.
 *
 * `react-markdown` construye **elementos de React**. No hay HTML que inyectar,
 * así que el requisito se cumple **por construcción y no por vigilancia**. Sin
 * `rehype-raw`, el HTML que venga dentro se descarta.
 *
 * Y el mensaje puede ser texto de un desconocido por WhatsApp: ésa es la
 * superficie de amenaza real, no una hipótesis.
 *
 * ## Por qué `remend`
 *
 * Mientras el texto llega a trozos la sintaxis está incompleta por definición.
 * `remend` cierra lo que quedó a medias —énfasis, código inline— antes de
 * pintar. Son 4,3 kB sin dependencias; es el mismo motor que `streamdown` lleva
 * dentro, sin el resto de `streamdown`, que por defecto admite HTML crudo e
 * imágenes de cualquier origen.
 *
 * **Lo que no arregla, y está bien así**: un bloque de código abierto no se
 * cierra, porque CommonMark dice que un cercado sin cerrar llega al final del
 * documento. Y una tabla a medias cambia de aspecto al completarse, porque GFM
 * exige la fila delimitadora — eso lo mitiga `Markdown` no repintando los
 * bloques ya cerrados.
 *
 * Licencias declaradas en `apps/desktop/THIRD-PARTY-LICENSES.md` (§VIII).
 */
import * as React from "react";
import ReactMarkdown from "react-markdown";
import remend from "remend";
import remarkGfm from "remark-gfm";

/**
 * Cuánto se pinta de una vez. Un mensaje de decenas de miles de caracteres no
 * puede bloquear la ventana ni obligar a desplazarse un minuto para llegar al
 * final (R2.5). Lo que queda no se esconde: se **dice** y se puede abrir.
 */
export const FIRST_CHUNK_CHARS = 4_000;

/** Protocolos que pueden viajar en un enlace. Todo lo demás se cae. */
const SAFE = /^(https?:|mailto:|#|\/)/i;

/** `javascript:` y `data:` no llegan al documento, vengan como vengan. */
function safeUrl(url: string): string {
  return SAFE.test(url.trim()) ? url : "";
}

function CodeBlock({ children }: { children: React.ReactNode }) {
  const code = React.useMemo(() => extractText(children).replace(/\n$/, ""), [children]);
  const [copiado, setCopiado] = React.useState(false);

  return (
    <div className="relative">
      <pre className="overflow-x-auto rounded border border-border bg-muted p-3 text-xs">{children}</pre>
      <button
        type="button"
        className="absolute top-2 right-2 rounded border border-border bg-background px-2 py-2 text-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        onClick={() => {
          // Lo que se copia es **el código**, no lo que se pintó: con el
          // cercado por medio son dos cosas distintas (R2.2).
          void navigator.clipboard?.writeText(code);
          setCopiado(true);
          window.setTimeout(() => setCopiado(false), 1500);
        }}
      >
        {copiado ? "Copiado" : "Copiar"}
      </button>
    </div>
  );
}

/**
 * El texto llano de un árbol de React, para poder copiarlo.
 *
 * Se quita el salto final **que añade el cercado**, no los del código: pegar en
 * una terminal algo que termina en salto lo ejecuta solo, y nadie espera eso de
 * un botón que dice «copiar».
 */
function extractText(node: React.ReactNode): string {
  if (typeof node === "string") return node;
  if (typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (React.isValidElement(node)) {
    return extractText((node.props as { children?: React.ReactNode }).children);
  }
  return "";
}

export function Markdown({ text }: { text: string }) {
  const [entero, setEntero] = React.useState(false);
  const largo = text.length > FIRST_CHUNK_CHARS;
  const visible = entero || !largo ? text : text.slice(0, FIRST_CHUNK_CHARS);

  // `remend` va sobre el texto, antes de parsear: cierra lo que el streaming
  // dejó a medias.
  const cerrado = React.useMemo(() => remend(visible), [visible]);

  return (
    <div className="flex min-w-0 flex-col gap-2 text-pretty [&_table]:w-full [&_table]:border-collapse [&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-border [&_th]:px-2 [&_th]:py-1 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        urlTransform={safeUrl}
        components={{
          // Ninguna imagen: no se carga nada de fuera (R2.3). No es una
          // limitación pendiente de levantar — es el requisito.
          img: () => null,
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          a: ({ children, href }) => (
            <a href={href} className="underline" rel="noreferrer noopener" target="_blank">
              {children}
            </a>
          ),
        }}
      >
        {cerrado}
      </ReactMarkdown>

      {largo && !entero ? (
        <button
          type="button"
          className="self-start rounded border border-border px-2 py-2 text-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          onClick={() => setEntero(true)}
        >
          Ver el resto
        </button>
      ) : null}
    </div>
  );
}
