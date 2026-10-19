/**
 * Spec 040: pages a business owner opens from a link, with no account. The
 * frame is the auth pages' — the brand, one column — without the login words.
 */
export default function ConnectLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto flex min-h-svh w-full max-w-md flex-col justify-center gap-8 px-6 py-12">
      <span className="font-mono text-sm font-semibold tracking-tight text-primary-deep">auphere</span>
      {children}
    </main>
  );
}
