"use client";

import { Upload } from "lucide-react";
import { type DragEvent, useRef, useState } from "react";

import { cn } from "@/lib/utils";

interface Props {
  extensions: string[];
  maxFileMb: number;
  uploading: boolean;
  onFiles: (files: File[]) => void;
}

/** Drop files here or click to pick them. The backend re-checks type and size. */
export function UploadDropzone({ extensions, maxFileMb, uploading, onFiles }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length > 0) onFiles([...event.dataTransfer.files]);
  };

  return (
    <button
      type="button"
      disabled={uploading}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cn(
        "flex w-full cursor-pointer flex-col items-center gap-1.5 rounded-lg border border-dashed px-4 py-6 text-center transition-colors hover:bg-muted/50 disabled:cursor-wait disabled:opacity-60",
        dragging && "border-primary bg-muted/50",
      )}
    >
      <Upload className="size-5 text-muted-foreground" aria-hidden />
      <span className="text-sm font-medium">{uploading ? "Uploading…" : "Drop files here, or click to choose"}</span>
      <span className="text-xs text-muted-foreground">
        {extensions.join(", ")} · up to {maxFileMb} MB each
      </span>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={extensions.join(",")}
        className="hidden"
        onChange={(e) => {
          if (e.target.files?.length) onFiles([...e.target.files]);
          e.target.value = ""; // picking the same file again should upload it again
        }}
      />
    </button>
  );
}
