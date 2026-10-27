import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Combine class names, letting later Tailwind classes override earlier ones.
 * e.g. cn("px-2 text-sm", isActive && "px-4") -> "text-sm px-4"
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
