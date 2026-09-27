"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Check, MapPin, Minus, Plus } from "lucide-react";
import { api, refresh, useApi, type Catalog, type MaterialId, type Pickup } from "@/lib/api";
import { formatDay, useI18n } from "@/lib/i18n";
import { Confetti, Counter, ErrorBox, Loading, MATERIAL_ICON, PageHeader, Sheet, Slot } from "@/components/ui";

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function Section({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  const { n: num } = useI18n();
  return (
    <section className="card p-5 md:p-6">
      <h2 className="mb-4 flex items-center gap-3 font-bold">
        <span className="grid size-7 place-items-center rounded-full bg-fg text-sm text-bg">{num(n)}</span>{title}
      </h2>
      {children}
    </section>
  );
}

export default function PickupPage() {
  const { t, n, pick, locale } = useI18n();
  const cat = useApi<Catalog>("/catalog"), hist = useApi<Pickup[]>("/pickups");
  const [qty, setQty] = useState<Partial<Record<MaterialId, number>>>({});
  const [day, setDay] = useState(0);
  const [slot, setSlot] = useState("17-20");
  const [address, setAddress] = useState<string>();
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<Pickup | null>(null);
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => { const d = new Date(); d.setDate(d.getDate() + i); return iso(d); }), []);

  if (cat.error) return <ErrorBox onRetry={cat.reload} />;
  if (!cat.data) return <Loading rows={4} />;
  const mats = cat.data.materials;
  const addr = address ?? hist.data?.[0]?.address ?? "";
  const items = Object.fromEntries(Object.entries(qty).filter(([, kg]) => kg! > 0)) as Record<MaterialId, number>;
  const kg = Object.values(items).reduce((a, b) => a + b, 0);
  const est = Object.entries(items).reduce((a, [m, k]) => a + mats[m as MaterialId].pts * k, 0);
  const bump = (m: MaterialId, d: number) => setQty((q) => ({ ...q, [m]: Math.min(100, Math.max(0, (q[m] ?? 0) + d)) }));

  const submit = async () => {
    if (addr.trim().length < 3) return setErr(t("address_err"));
    setBusy(true); setErr("");
    try {
      setDone(await api<Pickup>("/pickups", { items, day: days[day], slot, address: addr }));
      setQty({});
      refresh();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title={t("pickup_title")} sub={t("pickup_sub")} />
      <div className="stagger grid grid-cols-1 gap-5 lg:grid-cols-5">
        <div className="grid min-w-0 grid-cols-1 gap-5 lg:col-span-3">
          <Section n={1} title={t("step_what")}>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {(Object.keys(mats) as MaterialId[]).map((m) => {
                const Icon = MATERIAL_ICON[m], v = qty[m] ?? 0, on = v > 0;
                return (
                  <div key={m} className="chip press relative overflow-hidden p-4 transition-all" style={on ? { borderColor: mats[m].color, boxShadow: `0 10px 30px -12px ${mats[m].color}` } : undefined}>
                    <button className="block w-full text-start" onClick={() => !on && bump(m, 1)} aria-label={pick(mats[m])}>
                      <span className="grid size-11 place-items-center rounded-2xl transition-transform" style={{ background: `${mats[m].color}22`, color: mats[m].color, transform: on ? "scale(1.08) rotate(-6deg)" : undefined }}>
                        <Icon size={22} />
                      </span>
                      <div className="mt-3 text-sm font-semibold leading-tight">{pick(mats[m])}</div>
                      <div className="text-xs text-muted">{n(mats[m].pts)} {t("per_kg")}</div>
                    </button>
                    <div className="mt-3 flex items-center justify-between rounded-full bg-line p-1">
                      <button aria-label="−" onClick={() => bump(m, -0.5)} disabled={!on} className="press grid size-8 place-items-center rounded-full bg-bg disabled:opacity-40"><Minus size={14} /></button>
                      <span className="tnum text-sm font-bold">{n(v, 1)} <span className="text-xs font-normal text-muted">{t("kg")}</span></span>
                      <button aria-label="+" onClick={() => bump(m, 0.5)} className="press grid size-8 place-items-center rounded-full bg-bg"><Plus size={14} /></button>
                    </div>
                  </div>
                );
              })}
            </div>
          </Section>
          <Section n={2} title={t("step_when")}>
            <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 [scrollbar-width:none]">
              {days.map((d, i) => (
                <button key={d} aria-pressed={day === i} onClick={() => setDay(i)} className="chip press flex min-w-20 flex-col items-center px-4 py-3">
                  <span className="text-xs opacity-70">{i === 0 ? t("today") : formatDay(d, locale, { weekday: "short" })}</span>
                  <span className="text-2xl font-bold">{formatDay(d, locale, { day: "numeric" })}</span>
                  <span className="text-xs opacity-70">{formatDay(d, locale, { month: "short" })}</span>
                </button>
              ))}
            </div>
          </Section>
          <Section n={3} title={t("step_slot")}>
            <div className="grid grid-cols-2 gap-1 rounded-2xl bg-line p-1 sm:grid-cols-4">
              {cat.data.slots.map((s) => (
                <button key={s} onClick={() => setSlot(s)} className={`press rounded-xl py-2.5 text-sm font-semibold ${slot === s ? "bg-bg shadow-md" : "text-muted"}`}><Slot s={s} /></button>
              ))}
            </div>
          </Section>
          <Section n={4} title={t("step_where")}>
            <label className="flex items-start gap-3 rounded-2xl border border-line bg-bg/60 p-4 focus-within:border-brand focus-within:ring-4 focus-within:ring-brand/15">
              <MapPin size={20} className="mt-0.5 shrink-0 text-brand" />
              <textarea rows={2} value={addr} onChange={(e) => { setAddress(e.target.value); setErr(""); }} placeholder={t("address_ph")} maxLength={200}
                className="w-full resize-none bg-transparent outline-none placeholder:text-muted" aria-label={t("step_where")} />
            </label>
          </Section>
        </div>

        {/* summary: sticky on desktop, pinned above the tab bar on phones */}
        <aside className="lg:col-span-2">
          <div className={`glass fixed inset-x-3 bottom-24 z-20 rounded-[28px] p-4 shadow-2xl lg:sticky lg:inset-x-auto lg:top-10 lg:bottom-auto lg:p-6 ${err ? "shake" : ""}`} style={{ background: "var(--glass-strong)" }}>
            <div className="hidden lg:block">
              <h2 className="mb-3 font-bold">{t("total")}</h2>
              <ul className="mb-4 grid gap-2 text-sm">
                {Object.entries(items).map(([m, k]) => (
                  <li key={m} className="flex justify-between"><span>{pick(mats[m as MaterialId])}</span><span className="tnum text-muted">{n(k, 1)} {t("kg")}</span></li>
                ))}
              </ul>
            </div>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs text-muted">{n(kg, 1)} {t("kg")} · {t("est")}</div>
                <div className="grad-text text-3xl font-extrabold"><Counter value={est} /></div>
              </div>
              <button className="btn btn-primary press lg:hidden" disabled={!kg || busy} onClick={submit}>{busy ? t("sending") : t("confirm")}</button>
            </div>
            <button className="btn btn-primary press mt-5 hidden w-full lg:flex" disabled={!kg || busy} onClick={submit}>{busy ? t("sending") : t("confirm")}</button>
            {(err || !kg) && <p className={`mt-2 text-xs ${err ? "text-red-500" : "text-muted"}`}>{err || t("select_one")}</p>}
          </div>
        </aside>
      </div>
      <div className="h-28 lg:hidden" />

      <Sheet open={!!done} onClose={() => setDone(null)}>
        {done && <Confetti />}
        <div className="flex flex-col items-center gap-4 py-4 text-center">
          <span className="pop grid size-20 place-items-center rounded-full bg-gradient-to-br from-brand to-brand-2 text-white shadow-xl shadow-brand/40"><Check size={40} strokeWidth={3} /></span>
          <h2 className="text-2xl font-extrabold">{t("done_title")}</h2>
          {done && <p className="text-sm font-semibold text-brand">{formatDay(done.day, locale)} · <Slot s={done.slot} /> · +{n(done.est)} {t("est")}</p>}
          <p className="text-sm text-muted">{t("done_sub")}</p>
          <Link href="/" className="btn btn-primary press mt-2 w-full">{t("back_home")}</Link>
        </div>
      </Sheet>
    </>
  );
}
