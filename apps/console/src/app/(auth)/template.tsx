/**
 * Cada página de `(auth)` entra con un fundido corto — spec 066, R6.1.
 *
 * Un `template` se vuelve a montar en cada navegación (un `layout` no), así que
 * la animación de `.auth-page` se repite al pasar de una página a otra mientras
 * el líquido del layout sigue quieto en su sitio.
 */
export default function AuthTemplate({ children }: { children: React.ReactNode }) {
  return <div className="auth-page">{children}</div>;
}
