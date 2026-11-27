"use client";

import { QueryClient, QueryClientProvider, useQuery, type QueryKey } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, session } from "@/lib/api";
import type { DemoUser } from "@/lib/types";

interface SessionCtx {
  users: DemoUser[];
  user: DemoUser | null;
  ready: boolean;
  error: string | null;
  switchUser: (id: string) => Promise<void>;
}
const Ctx = createContext<SessionCtx>({ users: [], user: null, ready: false, error: null, switchUser: async () => {} });
export const useSession = () => useContext(Ctx);

const FALLBACK_USERS: DemoUser[] = [
  { id: "admin_001", role: "admin", name: "Meridian Bank Operator" },
  { id: "investigator_001", role: "investigator", name: "Dispute Investigator" },
  { id: "customer_001", role: "customer", name: "Alice Tremblay" },
  { id: "customer_002", role: "customer", name: "Ben Carter" },
];

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        staleTime: 5_000,
        retry: (n, err) => !(err instanceof ApiError && err.status >= 400 && err.status < 600 && err.status !== 0) && n < 1,
      },
    },
  });
}

function SessionProvider({ children }: { children: ReactNode }) {
  const [users, setUsers] = useState<DemoUser[]>([]);
  const [user, setUser] = useState<DemoUser | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [qc] = useState(() => makeClient());

  useEffect(() => {
    (async () => {
      try {
        const list = await api.users().catch(() => FALLBACK_USERS);
        setUsers(list);
        const wanted = session.userId && list.some((u) => u.id === session.userId) ? session.userId : "admin_001";
        if (!session.token || session.userId !== wanted) await api.login(wanted);
        setUser(list.find((u) => u.id === wanted) ?? null);
        setReady(true);
      } catch (e) {
        setError((e as Error).message);
        setReady(true);
      }
    })();
  }, []);

  const switchUser = useCallback(
    async (id: string) => {
      await api.login(id);
      setUser(users.find((u) => u.id === id) ?? null);
      qc.clear();
      qc.invalidateQueries();
    },
    [users, qc],
  );

  const value = useMemo(() => ({ users, user, ready, error, switchUser }), [users, user, ready, error, switchUser]);
  return (
    <QueryClientProvider client={qc}>
      <Ctx.Provider value={value}>{children}</Ctx.Provider>
    </QueryClientProvider>
  );
}

export function Providers({ children }: { children: ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}

/** useQuery scoped to the signed-in demo user; waits for the session to be ready. */
export function useQ<T>(key: QueryKey, fn: () => Promise<T>, opts: { enabled?: boolean; refetchInterval?: number } = {}) {
  const { user, ready } = useSession();
  return useQuery<T, ApiError>({
    queryKey: [user?.id ?? "anon", ...key],
    queryFn: fn,
    enabled: ready && !!user && (opts.enabled ?? true),
    refetchInterval: opts.refetchInterval,
  });
}
