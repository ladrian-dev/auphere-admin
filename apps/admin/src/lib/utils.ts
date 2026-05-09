import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * shadcn-standard className composition: merges Tailwind classes
 * (last-wins) and falsy-conditional values (clsx).
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
