"use client";
import Link from "next/link";
import { useState } from "react";
import { Check, MapPin, Minus, Plus } from "lucide-react";
import { api, refresh, useApi, type Catalog, type MaterialId, type Pickup } from "@/lib/api";
import { formatDay, useI18n, type Key } from "@/lib/i18n";
import { Confetti, Counter, ErrorBox, Loading, MATERIAL_ICON, PageHeader, Sheet, Slot, errKey } from "@/components/ui";

// the API validates the day on Tehran's calendar (UTC+3:30, no DST since 2022), not the device's
const tehranDay = (i: number) => new Date(Date.now() + 126e5 + i * 864e5).toISOString().slice(0, 10);
const MAX_KG = 50; // the API's cap, per material and for the whole pickup

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
  const { t, n, signed, pick, locale } = useI18n();
  const cat = useApi<Catalog>("/catalog"), hist = useApi<Pickup[]>("/pickups?limit=1");
  const [qty, setQty] = useState<Partial<Record<MaterialId, number>>>({});
  const [day, setDay] = useState(0);
  const [slot, setSlot] = useState("17-20");
  const [address, setAddress] = useState<string>();
  const [touched, setTouched] = useState(false);
  const [err, setErr] = useState<Key | "">("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<Pickup | null>(null);
  const days = Array.from({ length: 7 }, (_, i) => tehranDay(i)); // per render: a tab left open past midnight moves on to the new day

  if (cat.error) return <ErrorBox onRetry={cat.reload} />;
  if (!cat.data) return <Loading rows={4} />;
  const mats = cat.data.materials;
  const addr = address ?? hist.data?.[0]?.address ?? "";
  const addrKey: Key | "" = !addr.trim() ? "address_err" : addr.trim().length < 3 ? "address_short" : "";
  const addrBad = touched && !!addrKey;
  const items = Object.fromEntries(Object.entries(qty).filter(([, kg]) => kg! > 0)) as Record<MaterialId, number>;
  const kg = Object.values(items).reduce((a, b) => a + b, 0);
  const full = kg >= MAX_KG;
  const est = Object.entries(items).reduce((a, [m, k]) => a + mats[m as MaterialId].pts * k, 0);
  // clamp each material and the total to MAX_KG (0.5 kg steps are exact in binary, so the sums carry no float error)
  const bump = (m: MaterialId, d: number) => setQty((q) => {
    const cur = q[m] ?? 0, total = Object.values(q).reduce((a, b) => a + (b ?? 0), 0);
    return { ...q, [m]: Math.max(0, Math.min(MAX_KG, cur + d, cur + MAX_KG - total)) };
  });

  const submit = async () => {
    if (addrKey) { setTouched(true); return setErr(addrKey); }
    setBusy(true); setErr("");
    try {
      setDone(await api<Pickup>("/pickups", { items, day: days[day], slot, address: addr }));
      setQty({});
      refresh();
    } catch (e) { setErr(errKey(e, { 409: "day_cap", 422: "pickup_invalid" })); } finally { setBusy(false); }
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
                      <button aria-label={`${pick(mats[m])}: ${t("less")}`} onClick={() => bump(m, -0.5)} disabled={!on} className="press hit grid size-8 place-items-center rounded-full bg-bg disabled:opacity-40"><Minus size={14} /></button>
                      <span className="tnum text-sm font-bold" aria-live="polite">{n(v, 1)} <span className="text-xs font-normal text-muted">{t("kg")}</span></span>
                      <button aria-label={`${pick(mats[m])}: ${t("more")}`} onClick={() => bump(m, 0.5)} disabled={full} className="press hit grid size-8 place-items-center rounded-full bg-bg disabled:opacity-40"><Plus size={14} /></button>
                    </div>
                  </div>
                );
              })}
            </div>
            <p aria-live="polite" className="mt-3 text-xs font-semibold text-amber-text empty:mt-0">{full ? t("kg_cap") : ""}</p>
          </Section>
          <Section n={2} title={t("step_when")}>
            {/* a scroller (edge-faded from md, so a cut day reads as "more"); from xl all 7 fit in a grid */}
            <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 [scrollbar-width:none] md:max-xl:[mask-image:linear-gradient(to_right,#000_85%,transparent)] md:max-xl:rtl:[mask-image:linear-gradient(to_left,#000_85%,transparent)] xl:grid xl:grid-cols-7">
              {days.map((d, i) => (
                <button key={d} aria-pressed={day === i} onClick={() => setDay(i)} className="chip press flex min-w-20 flex-col items-center px-4 py-3 xl:min-w-0 xl:px-1">
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
                <button key={s} aria-pressed={slot === s} onClick={() => setSlot(s)} className={`press hit rounded-xl py-2.5 text-sm font-semibold ${slot === s ? "bg-bg shadow-md" : "text-muted"}`}><Slot s={s} /></button>
              ))}
            </div>
          </Section>
          <Section n={4} title={t("step_where")}>
            <label className={`flex items-start gap-3 rounded-2xl border bg-bg/60 p-4 focus-within:ring-4 ${addrBad ? "border-red-400 focus-within:ring-red-500/15" : "border-line focus-within:border-brand focus-within:ring-brand/15"}`}>
              <MapPin size={20} className="mt-0.5 shrink-0 text-brand" />
              <textarea id="address" name="address" autoComplete="street-address" rows={2} value={addr} onChange={(e) => { setAddress(e.target.value); setErr(""); }} onBlur={() => setTouched(true)} placeholder={t("address_ph")} maxLength={200}
                className="w-full resize-none bg-transparent outline-none placeholder:text-muted" aria-label={t("step_where")} aria-invalid={addrBad} aria-describedby={addrBad ? "addr-err" : undefined} />
            </label>
            {addrBad && <p id="addr-err" role="alert" className="mt-2 text-xs text-danger">{t(addrKey)}</p>}
          </Section>
        </div>

        {/* summary: sticky on desktop, pinned above the tab bar on phones (no entrance there: pinned chrome stays put) */}
        <aside className="max-lg:animate-none lg:col-span-2">
          <div className={`panel fixed inset-x-3 bottom-24 z-20 rounded-[28px] p-4 lg:sticky lg:inset-x-auto lg:top-10 lg:bottom-auto lg:p-6 ${err ? "shake" : ""}`}>
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
                <div className="text-xs text-muted">{n(kg, 1)} {t("kg")}{t("sep")}{t("est")}</div>
                <div className="grad-text text-3xl font-extrabold"><Counter value={est} /> <span className="text-base font-bold">{t("pts")}</span></div>
              </div>
              <button className="btn btn-primary press lg:hidden" disabled={!kg || busy} onClick={submit}>{busy ? t("sending") : t("confirm")}</button>
            </div>
            <button className="btn btn-primary press mt-5 hidden w-full lg:flex" disabled={!kg || busy} onClick={submit}>{busy ? t("sending") : t("confirm")}</button>
            {(err || !kg) && <p role={err ? "alert" : undefined} className={`mt-2 text-xs ${err ? "text-danger" : "text-muted"}`}>{t(err || "select_one")}</p>}
          </div>
        </aside>
      </div>
      <div className="h-28 lg:hidden" />

      <Sheet open={!!done} onClose={() => setDone(null)} labelledBy="pickup-done-title">
        {done && <Confetti />}
        <div className="flex flex-col items-center gap-4 py-4 text-center">
          <span className="pop grid size-20 place-items-center rounded-full bg-gradient-to-br from-brand-fill to-brand-fill-2 text-on-brand shadow-xl shadow-brand/40"><Check size={40} strokeWidth={3} /></span>
          <h2 id="pickup-done-title" className="text-2xl font-extrabold">{t("done_title")}</h2>
          {done && <p className="text-sm font-semibold text-brand-text">{formatDay(done.day, locale)}{t("sep")}<Slot s={done.slot} />{t("sep")}{signed(done.est)} {t("est")}</p>}
          <p className="text-sm text-muted">{t("done_sub")}</p>
          <Link href="/" className="btn btn-primary press mt-2 w-full">{t("back_home")}</Link>
        </div>
      </Sheet>
    </>
  );
}
