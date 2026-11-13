"use client";

import { X } from "lucide-react";

import type { AttachedImage } from "@/lib/images";
import { cn } from "@/lib/utils";

/**
 * Small previews of attached images: in the composer (removable) and in a sent message
 * (click to open full size). The alt text is what the vision model saw, when known.
 */
export function ImageThumbnails({
  images,
  onRemove,
  className,
}: {
  images: AttachedImage[];
  onRemove?: (id: string) => void;
  className?: string;
}) {
  if (images.length === 0) return null;
  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {images.map((image) => (
        <div key={image.id} className="relative">
          <a href={image.url} target="_blank" rel="noreferrer" title={image.description ?? "Attached image"}>
            {/* eslint-disable-next-line @next/next/no-img-element -- data URLs and API images, no optimisation needed */}
            <img
              src={image.url}
              alt={image.description ?? "Attached image"}
              className="h-20 max-w-40 rounded-lg border object-cover"
            />
          </a>
          {onRemove && (
            <button
              type="button"
              onClick={() => onRemove(image.id)}
              aria-label="Remove image"
              className="absolute -top-2 -right-2 flex size-5 cursor-pointer items-center justify-center rounded-full border bg-background text-muted-foreground shadow-sm hover:text-foreground"
            >
              <X className="size-3" />
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
