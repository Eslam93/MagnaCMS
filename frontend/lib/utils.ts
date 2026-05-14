import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * shadcn/ui standard `cn` helper: merge Tailwind classes intelligently
 * (drops conflicting utilities). Used everywhere component variants
 * need to combine classes.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
