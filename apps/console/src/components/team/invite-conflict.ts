/** QA-18: a 409 from invite (already a member / pending invite) is visible. */
export function inviteConflictMessage(status: number, fallback: string, already: string): string {
  return status === 409 ? already : fallback;
}
