/**
 * Spec 030: when the session expired or the operator took the Inbox away
 * mid-use, the API answers 401/403. Reloading lets the page guard decide
 * where the person belongs (login, keeping `from`; or their first module) —
 * instead of a screen that keeps saying «that didn't work». Its own module
 * so tests can replace it (jsdom's `location.reload` cannot be spied on).
 */
export function reloadPage(): void {
  window.location.reload();
}
