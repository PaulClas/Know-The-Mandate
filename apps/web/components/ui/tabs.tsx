"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

const TabsCtx = createContext<{ value: string; set: (v: string) => void }>({ value: "", set: () => {} });

export function Tabs({ defaultValue, value, onValueChange, children, className }: { defaultValue?: string; value?: string; onValueChange?: (v: string) => void; children: ReactNode; className?: string }) {
  const [inner, setInner] = useState(defaultValue ?? "");
  const v = value ?? inner;
  return (
    <TabsCtx.Provider value={{ value: v, set: (x) => (onValueChange ? onValueChange(x) : setInner(x)) }}>
      <div className={className}>{children}</div>
    </TabsCtx.Provider>
  );
}
export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div role="tablist" className={cn("flex flex-wrap gap-0.5 border-b border-border", className)}>
      {children}
    </div>
  );
}
export function TabsTrigger({ value, children }: { value: string; children: ReactNode }) {
  const c = useContext(TabsCtx);
  const active = c.value === value;
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={() => c.set(value)}
      className={cn(
        "-mb-px cursor-pointer border-b-2 px-3 py-1.5 text-[13px] font-medium transition-colors",
        active ? "border-accent text-foreground" : "border-transparent text-muted hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}
export function TabsContent({ value, children, className }: { value: string; children: ReactNode; className?: string }) {
  const c = useContext(TabsCtx);
  if (c.value !== value) return null;
  return (
    <div role="tabpanel" className={className}>
      {children}
    </div>
  );
}
