"use client";
import { useCallback, useEffect, useState } from "react";
import type { L10n } from "./i18n";

export type Material = L10n & { pts: number; co2: number; color: string };
export type MaterialId = "paper" | "plastic" | "metal" | "glass" | "ewaste";
export type Pickup = { id: number; day: string; slot: string; address: string; items: Partial<Record<MaterialId, number>>; status: "scheduled" | "delivered" | "canceled"; est: number; points: number; weight: number };
export type State = { name: L10n; balance: number; lifetime: number; tier: "bronze" | "silver" | "gold"; tierFloor: number; next: { tier: string; at: number } | null; impact: { kg: number; co2: number; trees: number; landfill: number }; upcoming: Pickup | null };
export type Reward = L10n & { id: string; cat: string; cost: number; partner: L10n };
export type Mission = { id: string; pts: number; fa: { q: string; a: string[] }; en: { q: string; a: string[] }; done: boolean };
/** `demo` is false in production, where only a collector (with its key) may complete a pickup. */
export type Catalog = { materials: Record<MaterialId, Material>; slots: string[]; rewards: Reward[]; missions: Mission[]; demo: boolean };
export type Txn = { id: number; ts: string; kind: "pickup" | "redeem" | "mission"; ref: string; points: number };
export type District = L10n & { id: string; points: number; mine: boolean };
export type City = { kpi: Record<"tons" | "mau" | "participation" | "landfillSaved" | "co2" | "partners", number>; months: { m: number; tons: number; users: number }[]; materials: { id: MaterialId; pct: number }[]; districts: District[] };

// GET cache: stale-while-revalidate across client navigations. Only ever filled in the browser.
const cache = new Map<string, unknown>();

export async function api<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, body === undefined
    ? { cache: "no-store" }
    : { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(res.statusText), { status: res.status }); // useErr() maps the status to localized copy
  if (body === undefined) cache.set(path, data);
  return data as T;
}

/** GET: cached data first (if any), then revalidates; refetches whenever any mutation calls refresh(). */
export function useApi<T>(path: string) {
  const [data, setData] = useState<T | undefined>(() => cache.get(path) as T | undefined);
  const [error, setError] = useState(false);
  const load = useCallback(() => api<T>(path).then((d) => { setData(d); setError(false); }, () => setError(true)), [path]);
  useEffect(() => {
    load();
    window.addEventListener("sabz:refresh", load);
    return () => window.removeEventListener("sabz:refresh", load);
  }, [load]);
  return { data, error, reload: load };
}

export const refresh = () => { cache.clear(); window.dispatchEvent(new Event("sabz:refresh")); };
