"use client";

import { useEffect, useState } from "react";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, type ModelInfo } from "@/lib/api";

const STORAGE_KEY = "atlas:model";

interface Props {
  value: string | null;
  onChange: (modelId: string) => void;
  disabled?: boolean;
}

/** Model dropdown, filled from GET /api/models. Unavailable models are shown but disabled. */
export function ModelSwitcher({ value, onChange, disabled }: Props) {
  const [models, setModels] = useState<ModelInfo[]>([]);

  useEffect(() => {
    let cancelled = false;
    api
      .models()
      .then(({ models, default_model }) => {
        if (cancelled) return;
        setModels(models);
        const saved = readSaved();
        const usable = (id: string | null) => models.some((m) => m.id === id && m.available);
        onChange(usable(saved) ? (saved as string) : default_model);
      })
      .catch(() => setModels([]));
    return () => {
      cancelled = true;
    };
    // Load once on mount; onChange identity changes don't need a refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function select(modelId: string) {
    onChange(modelId);
    try {
      localStorage.setItem(STORAGE_KEY, modelId); // remembered per browser
    } catch {
      // storage blocked (private mode): the choice just isn't remembered
    }
  }

  return (
    <Select value={value ?? undefined} onValueChange={select} disabled={disabled || models.length === 0}>
      <SelectTrigger size="sm" className="w-[270px] max-w-[55vw]" aria-label="Model">
        <SelectValue placeholder="Loading models…" />
      </SelectTrigger>
      <SelectContent align="end">
        {models.map((m) => (
          <SelectItem key={m.id} value={m.id} disabled={!m.available}>
            <span className="flex flex-col">
              <span>{m.label}</span>
              {!m.available && <span className="text-xs text-muted-foreground">{m.unavailable_reason}</span>}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function readSaved(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}
