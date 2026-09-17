/** Une clases ignorando falsy. Sin dependencias. */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
