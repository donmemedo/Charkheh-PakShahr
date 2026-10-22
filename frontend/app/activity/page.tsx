"use client";
import Link from "next/link";
import { useState } from "react";
import { Gift, MapPin, Plus, Target, Truck } from "lucide-react";
import { useApi, type Catalog, type MaterialId, type Pickup, type Txn } from "@/lib/api";
import { formatDay, useI18n, type Key } from "@/lib/i18n";
import { ErrorBox, Loading, MATERIAL_ICON, PageHeader, Slot } from "@/components/ui";

const STATUS = { scheduled: "bg-amber-500/15 text-amber-text", delivered: "bg-brand-soft text-brand-text", canceled: "bg-line text-muted" };
const TX = { pickup: { icon: Truck, tint: "bg-brand-soft text-brand" }, redeem: { icon: Gift, tint: "bg-fuchsia-500/12 text-fuchsia-500" }, mission: { icon: Target, tint: "bg-rose-500/12 text-rose-500" } };

function Empty({ text }: { text: Key }) {
  const { t } = useI18n();
  return (
    <div className="card flex flex-col items-center gap-4 p-10 text-center md:col-span-2">
      <p className="text-muted">{t(text)}</p>
      <Link href="/pickup" className="btn btn-primary press"><Plus size={18} /> {t("quick_pickup")}</Link>
    </div>
  );
}

export default function Activity() {
  const { t, n, signed, pick, locale } = useI18n();
  const [tab, setTab] = useState<"pickups" | "txns">("pickups");
  // ponytail: newest 200 (the API maximum), no load-more; add one with ?before=<last id> when histories get that long
  const ps = useApi<Pickup[]>("/pickups?limit=200"), tx = useApi<Txn[]>("/transactions"), cat = useApi<Catalog>("/catalog");
  if (ps.error || tx.error || cat.error) return <ErrorBox onRetry={() => { ps.reload(); tx.reload(); cat.reload(); }} />;
  if (!ps.data || !tx.data || !cat.data) return <Loading rows={4} />;
  const reward = (id: string) => cat.data!.rewards.find((r) => r.id === id);

  return (
    <>
      <PageHeader title={t("activity_title")}>
        {/* two tabs: either arrow key moves to the other one (roving tabindex) */}
        <div role="tablist" className="grid grid-cols-2 gap-1 rounded-full bg-line p-1" onKeyDown={(e) => {
          if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
          const k = tab === "pickups" ? "txns" : "pickups";
          setTab(k); document.getElementById(`tab-${k}`)?.focus();
        }}>
          {(["pickups", "txns"] as const).map((k) => (
            <button key={k} role="tab" id={`tab-${k}`} aria-selected={tab === k} aria-controls="activity-panel" tabIndex={tab === k ? 0 : -1} onClick={() => setTab(k)} className={`press hit rounded-full px-5 py-2 text-sm font-semibold ${tab === k ? "bg-bg shadow-md" : "text-muted"}`}>{t(`tab_${k}`)}</button>
          ))}
        </div>
      </PageHeader>

      {tab === "pickups" ? (
        <div key="p" id="activity-panel" role="tabpanel" aria-labelledby="tab-pickups" tabIndex={0} className="stagger grid grid-cols-1 gap-3 md:grid-cols-2">
          {ps.data.length === 0 && <Empty text="empty_pickups" />}
          {ps.data.map((p) => (
            <article key={p.id} className="card p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-bold">{formatDay(p.day, locale, { weekday: "long", day: "numeric", month: "long" })}</h3>
                  <p className="text-sm text-muted"><Slot s={p.slot} /></p>
                </div>
                <span className={`shrink-0 rounded-full px-3 py-1 text-xs font-bold ${STATUS[p.status]}`}>{t(`st_${p.status}` as Key)}</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {Object.entries(p.items).map(([m, kg]) => {
                  const Icon = MATERIAL_ICON[m as MaterialId], mat = cat.data!.materials[m as MaterialId];
                  return <span key={m} className="chip flex items-center gap-1.5 px-2.5 py-1 text-xs"><Icon size={13} style={{ color: mat.color }} /> {pick(mat)}{t("sep")}{n(kg!, 1)} {t("kg")}</span>;
                })}
              </div>
              <div className="mt-4 flex items-center justify-between border-t border-line pt-3 text-sm">
                <span className="flex min-w-0 items-center gap-1 text-muted"><MapPin size={14} className="shrink-0" /> <span className="truncate">{p.address}</span></span>
                <span className="tnum shrink-0 font-bold text-brand-text">{p.status === "delivered" ? signed(p.points) : p.status === "scheduled" ? signed(p.est, "~") : "—"}</span>
              </div>
            </article>
          ))}
        </div>
      ) : tx.data.length === 0 ? (
        <div key="t" id="activity-panel" role="tabpanel" aria-labelledby="tab-txns" tabIndex={0} className="grid"><Empty text="empty_txns" /></div>
      ) : (
        <ul key="t" id="activity-panel" role="tabpanel" aria-labelledby="tab-txns" tabIndex={0} className="card stagger divide-y divide-line overflow-hidden">
          {tx.data.map((x) => {
            const { icon: Icon, tint } = TX[x.kind];
            const title = x.kind === "redeem" ? pick(reward(x.ref) ?? { fa: t("tx_redeem"), en: t("tx_redeem") }) : t(`tx_${x.kind}`);
            return (
              <li key={x.id} className="flex items-center gap-4 px-5 py-4">
                <span className={`grid size-11 shrink-0 place-items-center rounded-2xl ${tint}`}><Icon size={20} /></span>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-semibold">{title}</div>
                  <div className="text-xs text-muted">{formatDay(x.ts.slice(0, 10), locale, { day: "numeric", month: "long", year: "numeric" })}</div>
                </div>
                <span className={`tnum font-bold ${x.points > 0 ? "text-brand-text" : "text-fg"}`}>{signed(x.points)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
