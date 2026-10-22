import { vi } from "vitest";

/**
 * The toasts a Reservas test reads. Its own module, with nothing but vitest:
 * the `sonner` mock factory imports it while `@nexus/ui` (which imports
 * sonner) is still loading, and a factory that pulled the whole harness in
 * deadlocked there.
 */
export const toasts = { success: vi.fn(), error: vi.fn(), message: vi.fn() };
export const sonner = { toast: toasts, Toaster: () => null };
