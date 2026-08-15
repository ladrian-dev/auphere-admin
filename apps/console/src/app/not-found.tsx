import { EmptyState } from "@nexus/ui";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-lg p-8">
      <EmptyState title="404" description="No existe o no es tuyo." readonly />
    </main>
  );
}
