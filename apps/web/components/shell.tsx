"use client";

import { BookOpen, Bot, Building2, FileCheck2, FlaskConical, Gauge, GitBranch, Moon, Network, PlayCircle, ReceiptText, Scale, ScrollText, ShieldCheck, Sun, Swords, UserRound, Wand2 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useSession } from "./providers";
import { Badge } from "./ui/badge";
import { Select } from "./ui/input";

const NAV = [
  { group: "Overview", items: [{ href: "/", label: "Executive overview", icon: Gauge }] },
  {
    group: "Govern",
    items: [
      { href: "/agents", label: "Agents", icon: Bot },
      { href: "/studio", label: "Mandate studio", icon: Wand2 },
      { href: "/portal", label: "Customer portal", icon: Building2 },
      { href: "/delegation", label: "Delegation graph", icon: GitBranch },
    ],
  },
  {
    group: "Enforce",
    items: [
      { href: "/playground", label: "Playground", icon: FlaskConical },
      { href: "/sandbox", label: "Agent sandbox", icon: Swords },
      { href: "/scenarios", label: "Scenarios", icon: PlayCircle },
      { href: "/transactions", label: "Transactions", icon: ReceiptText },
    ],
  },
  {
    group: "Evidence",
    items: [
      { href: "/ledger", label: "Ledger", icon: ScrollText },
      { href: "/disputes", label: "Disputes", icon: Scale },
    ],
  },
  {
    group: "Knowledge",
    items: [
      { href: "/ontology", label: "Ontology", icon: Network },
      { href: "/standards", label: "Standards & regulation", icon: BookOpen },
    ],
  },
];

export function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const { users, user, switchUser, error } = useSession();
  const [dark, setDark] = useState(false);

  useEffect(() => setDark(document.documentElement.classList.contains("dark")), []);
  const toggle = () => {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("kym.theme", next ? "dark" : "light");
    setDark(next);
  };

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-[232px] shrink-0 flex-col border-r border-border bg-surface md:flex">
        <Link href="/" className="flex items-center gap-2 px-4 py-3.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-navy text-white dark:bg-accent dark:text-accentfg">
            <FileCheck2 size={15} />
          </span>
          <span className="leading-tight">
            <span className="block text-[13px] font-semibold">KYM</span>
            <span className="block text-[11px] text-muted">Know Your Mandate</span>
          </span>
        </Link>
        <nav className="flex-1 overflow-y-auto px-2 pb-2">
          {NAV.map((g) => (
            <div key={g.group} className="mb-3">
              <div className="px-2 pb-1 text-[10.5px] font-semibold uppercase tracking-wider text-muted">{g.group}</div>
              {g.items.map((i) => {
                const active = i.href === "/" ? path === "/" : path.startsWith(i.href);
                return (
                  <Link
                    key={i.href}
                    href={i.href}
                    className={cn(
                      "flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] transition-colors",
                      active ? "bg-surface2 font-medium text-foreground" : "text-muted hover:bg-surface2/70 hover:text-foreground",
                    )}
                  >
                    <i.icon size={15} className={cn(active && "text-accent")} />
                    {i.label}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="border-t border-border p-3 text-[11px] leading-snug text-muted">
          <Badge tone="warn" className="mb-1.5">
            EXPERIMENTAL · SYNTHETIC
          </Badge>
          <p>Proof of concept with synthetic data and sandbox security. Not compliant or certified. Not legal advice.</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-border bg-surface/90 px-4 backdrop-blur">
          <div className="hidden items-center gap-2 text-xs text-muted lg:flex">
            <ShieldCheck size={14} className="text-accent" />
            <span>Meridian Bank · synthetic demo</span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <UserRound size={14} className="text-muted" />
            <Select aria-label="Demo user" data-testid="user-switcher" className="h-7 w-auto max-w-[280px] text-xs" value={user?.id ?? ""} onChange={(e) => switchUser(e.target.value)}>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name} · {u.role}
                </option>
              ))}
            </Select>
            <button onClick={toggle} aria-label="Toggle dark mode" className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-md border border-border hover:bg-surface2">
              {dark ? <Sun size={14} /> : <Moon size={14} />}
            </button>
          </div>
        </header>
        <MobileNav path={path} />
        {error && <div className="bg-badbg px-4 py-2 text-[13px] text-bad">Could not start a demo session: {error}. Is the API running on :8000?</div>}
        <main className="mx-auto w-full max-w-[1480px] flex-1 p-4 lg:p-6">{children}</main>
        <footer className="border-t border-border px-6 py-3 text-[11px] text-muted">
          KYM is an experimental, synthetic proof of concept. Nothing here is legal advice, a compliance claim, or a certification.
        </footer>
      </div>
    </div>
  );
}

function MobileNav({ path }: { path: string }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-border bg-surface px-2 py-1.5 md:hidden">
      {NAV.flatMap((g) => g.items).map((i) => (
        <Link key={i.href} href={i.href} className={cn("whitespace-nowrap rounded px-2 py-1 text-xs", path === i.href ? "bg-surface2 font-medium" : "text-muted")}>
          {i.label}
        </Link>
      ))}
    </div>
  );
}
