"use client";

import { X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Dialog({ open, onClose, title, children, side = false, wide = false }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; side?: boolean; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div
        className={cn(
          "relative flex max-h-full flex-col border border-border bg-surface shadow-xl",
          side ? "ml-auto h-full w-full max-w-[640px] border-y-0 border-r-0" : "m-auto w-full rounded-lg " + (wide ? "max-w-4xl" : "max-w-xl"),
        )}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button aria-label="Close" onClick={onClose} className="cursor-pointer rounded p-1 text-muted hover:bg-surface2">
            <X size={16} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
      </div>
    </div>
  );
}
