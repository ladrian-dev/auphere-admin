import { AppShell } from "@/components/layout/AppShell";
import { Welcome } from "@/components/welcome/Welcome";

export default function HomePage() {
  return (
    <AppShell tone="dark" themeToggle={false} sticker={false}>
      <Welcome />
    </AppShell>
  );
}
