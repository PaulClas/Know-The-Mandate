import type { ReactNode } from "react";

export function Tooltip({ text, children }: { text: string; children: ReactNode }) {
  return (
    <span className="group relative inline-flex">
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-40 mb-1 hidden w-max max-w-xs -translate-x-1/2 rounded bg-foreground px-2 py-1 text-[11px] font-normal text-background group-hover:block"
      >
        {text}
      </span>
    </span>
  );
}
