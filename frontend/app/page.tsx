"use client";
import Link from "next/link";
import { useState } from "react";
import { ArrowUpRight, CalendarDays, Clock, Gift, Mountain, Plus, Sparkles, Target, TreePine, Truck } from "lucide-react";
import { api, refresh, useApi, type Catalog, type Pickup, type State } from "@/lib/api";
import { formatDay, useI18n, type Key } from "@/lib/i18n";
import { Confetti, Counter, ErrorBox, Loading, MATERIAL_ICON, Rings, Slot, TIER_STYLE, errKey } from "@/components/ui";

function Wallet({ s }: { s: State }) {
  const { t } = useI18n();
  const move = (e: React.PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
    const st = e.currentTarget.style;
    st.setProperty("--ry", `${(x - 0.5) * 10}deg`); st.setProperty("--rx", `${(0.5 - y) * 10}deg`);
    st.setProperty("--mx", `${x * 100}%`); st.setProperty("--my", `${y * 100}%`);
  };
  const reset = (e: React.PointerEvent<HTMLDivElement>) => { e.currentTarget.style.setProperty("--rx", "0deg"); e.currentTarget.style.setProperty("--ry", "0deg"); };
  const progress = s.next ? (s.lifetime - s.tierFloor) / (s.next.at - s.tierFloor) : 1;
  return (
    <div className="wallet flex min-h-64 flex-col p-7 md:col-span-2" onPointerMove={move} onPointerLeave={reset}>
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-sm font-semibold text-white/80"><Sparkles size={16} /> {t("balance")}</span>
        <span className={`rounded-full bg-gradient-to-r ${TIER_STYLE[s.tier]} px-3 py-1 text-xs font-bold text-black/80 shadow`}>{t(`tier_${s.tier}` as Key)}</span>
      </div>
      <div className="mt-4 flex items-baseline gap-3">
        <span className="text-6xl font-extrabold ltr:tracking-tight md:text-7xl"><Counter value={s.balance} /></span>
        <span className="text-lg text-white/75">{t("points")}</span>
      </div>
      <div className="mt-auto pt-8">
        <div className="h-2 overflow-hidden rounded-full bg-white/20">
          <div className="h-full rounded-full bg-white shadow-[0_0_12px_white] transition-[width] duration-[1.6s] ease-out" style={{ width: `${Math.max(4, progress * 100)}%` }} />
        </div>
        <p className="mt-3 text-sm text-white/80">
          {s.next ? <><Counter value={s.next.at - s.lifetime} /> {t("pts")} {t("to_next")} {t(`tier_${s.next.tier}` as Key)}</> : t("max_tier")}
        </p>
      </div>
    </div>
  );
}

function Impact({ s, c }: { s: State; c: Catalog }) {
  const { t } = useI18n();
  const done = c.missions.filter((m) => m.done).length;
  // rings keep the bright colours; the figures use the matching text tokens (the bright ones are 2-3.5:1 on white)
  const rows = [
    { v: s.impact.kg, max: 50, color: "#30d158", text: "text-brand-text", label: t("kg_recycled"), d: 1 },
    { v: s.impact.co2, max: 80, color: "#0ea5e9", text: "text-sky-text", label: t("co2_saved"), d: 1 },
    { v: done, max: c.missions.length, color: "#ff375f", text: "text-rose-text", label: t("missions_done"), d: 0 },
  ];
  return (
    <div className="card flex flex-col p-6">
      <h2 className="font-bold">{t("impact")}</h2>
      <div className="mt-4 flex flex-1 items-center gap-5">
        <Rings rings={rows.map((r) => ({ value: r.v / r.max, color: r.color }))} size={132} />
        <ul className="grid gap-3">
          {rows.map((r) => (
            <li key={r.label}>
              <div className={`text-2xl font-bold ${r.text}`}><Counter value={r.v} digits={r.d} /></div>
              <div className="text-xs text-muted">{r.label}</div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function Upcoming({ p, c, onDelivered }: { p: Pickup | null; c: Catalog; onDelivered: (pts: number) => void }) {
  const { t, n, signed, pick, locale } = useI18n();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<Key | "">("");
  const act = async (path: string) => {
    setBusy(true); setErr("");
    try {
      const r = await api<Pickup | { ok: true }>(path, {});
      if ("points" in r) onDelivered(r.points);
      refresh();
    } catch (e) { setErr(errKey(e)); refresh(); } finally { setBusy(false); }
  };
  if (!p) return (
    <div className="card flex flex-col items-start gap-4 p-6">
      <span className="grid size-12 place-items-center rounded-2xl bg-brand-soft text-brand"><Truck /></span>
      <div>
        <h2 className="font-bold">{t("upcoming")}</h2>
        <p className="text-sm text-muted">{t("no_upcoming")}</p>
      </div>
      <Link href="/pickup" className="btn btn-primary press mt-auto"><Plus size={18} /> {t("quick_pickup")}</Link>
    </div>
  );
  return (
    <div className="card flex flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-bold"><Truck size={18} className="text-brand" /> {t("upcoming")}</h2>
        <span className="rounded-full bg-brand-soft px-3 py-1 text-xs font-bold text-brand-text">{signed(p.est)} {t("est")}</span>
      </div>
      <div className="flex flex-wrap gap-4 text-sm">
        <span className="flex items-center gap-1.5"><CalendarDays size={16} className="text-muted" /> {formatDay(p.day, locale)}</span>
        <span className="flex items-center gap-1.5"><Clock size={16} className="text-muted" /> <Slot s={p.slot} /></span>
      </div>
      <div className="flex flex-wrap gap-2">
        {Object.entries(p.items).map(([m, kg]) => {
          const Icon = MATERIAL_ICON[m as keyof typeof MATERIAL_ICON], mat = c.materials[m as keyof typeof c.materials];
          return <span key={m} className="chip flex items-center gap-1.5 px-3 py-1.5 text-sm"><Icon size={15} style={{ color: mat.color }} /> {pick(mat)}{t("sep")}{n(kg!, 1)} {t("kg")}</span>;
        })}
      </div>
      {c.demo && <p className="text-xs text-muted">{t("simulate_d")}</p>}
      <div className="flex flex-wrap gap-2">
        {c.demo && <button disabled={busy} onClick={() => act(`/pickups/${p.id}/complete`)} className="btn btn-primary press h-11 flex-1">{t("simulate")}</button>}
        <button disabled={busy} onClick={() => act(`/pickups/${p.id}/cancel`)} className="btn press h-11 text-muted hover:text-danger">{t("cancel_req")}</button>
      </div>
      {err && <p role="alert" className="text-sm font-semibold text-danger">{t(err)}</p>}
    </div>
  );
}

export default function Home() {
  const { t, signed, pick, locale } = useI18n();
  const st = useApi<State>("/state"), cat = useApi<Catalog>("/catalog");
  const [toast, setToast] = useState<number | null>(null);
  if (st.error || cat.error) return <ErrorBox onRetry={() => { st.reload(); cat.reload(); }} />;
  if (!st.data || !cat.data) return <Loading rows={4} />;
  const s = st.data;
  const quick = [
    { href: "/rewards", icon: Gift, label: t("quick_rewards"), tint: "text-amber-500 bg-amber-500/12" },
    { href: "/missions", icon: Target, label: t("quick_missions"), tint: "text-rose-500 bg-rose-500/12" },
  ];
  return (
    <div className="stagger grid grid-cols-1 gap-5 md:grid-cols-3">
      <div className="md:col-span-3">
        <p className="text-sm text-muted">{new Date().toLocaleDateString(locale === "fa" ? "fa-IR-u-ca-persian" : "en-US", { weekday: "long", day: "numeric", month: "long" })}</p>
        <h1 className="title-xl mt-1">{t("hello")} <span className="grad-text">{pick(s.name)}</span></h1>
      </div>
      <Wallet s={s} />
      <Impact s={s} c={cat.data} />
      <Upcoming p={s.upcoming} c={cat.data} onDelivered={(p) => { setToast(p); setTimeout(() => setToast(null), 2600); }} />
      <div className="grid gap-5 md:col-span-2 md:grid-cols-2">
        <Link href="/pickup" className="card press lift group relative overflow-hidden p-6 md:col-span-2">
          <div className="absolute -end-10 -top-10 size-40 rounded-full bg-gradient-to-br from-brand to-brand-2 opacity-20 blur-2xl transition-opacity group-hover:opacity-40" />
          <div className="flex items-center justify-between">
            <span className="grid size-12 place-items-center rounded-2xl bg-gradient-to-br from-brand-fill to-brand-fill-2 text-on-brand shadow-lg shadow-brand/30"><Truck /></span>
            <ArrowUpRight className="text-muted transition-transform group-hover:-translate-y-1 rtl:-scale-x-100" />
          </div>
          <h3 className="mt-4 text-lg font-bold">{t("quick_pickup")}</h3>
          <p className="text-sm text-muted">{t("quick_pickup_d")}</p>
        </Link>
        {quick.map(({ href, icon: Icon, label, tint }) => (
          <Link key={href} href={href} className="card press lift flex items-center gap-4 p-5">
            <span className={`grid size-12 place-items-center rounded-2xl ${tint}`}><Icon /></span>
            <span className="font-semibold">{label}</span>
          </Link>
        ))}
        <div className="card flex items-center gap-4 p-5">
          <span className="grid size-12 place-items-center rounded-2xl bg-emerald-500/12 text-emerald-500"><TreePine /></span>
          <div><div className="text-xl font-bold"><Counter value={s.impact.trees} digits={2} /></div><div className="text-xs text-muted">{t("trees")}</div></div>
        </div>
        <div className="card flex items-center gap-4 p-5">
          <span className="grid size-12 place-items-center rounded-2xl bg-sky-500/12 text-sky-500"><Mountain /></span>
          <div><div className="text-xl font-bold"><Counter value={s.impact.landfill} /></div><div className="text-xs text-muted">{t("landfill")}</div></div>
        </div>
      </div>
      {toast !== null && (
        <>
          <Confetti />
          <div aria-hidden className="pop glass fixed inset-x-0 top-24 z-[70] mx-auto w-fit rounded-full px-6 py-3 text-lg font-bold shadow-2xl">{signed(toast)} {t("points")} 🎉</div>
        </>
      )}
      {/* completion feedback: a live region must already exist before its text changes to be announced */}
      <p role="status" className="sr-only">{toast !== null ? `${signed(toast)} ${t("points")}` : ""}</p>
    </div>
  );
}
