"use client";
import { useEffect, useState } from "react";
import { Cloud, Handshake, Mountain, Percent, Recycle, Users, type LucideIcon } from "lucide-react";
import { useApi, type Catalog, type City } from "@/lib/api";
import { useI18n, type Key } from "@/lib/i18n";
import { Counter, ErrorBox, Loading, PageHeader } from "@/components/ui";

const KPI: { k: keyof City["kpi"]; label: Key; icon: LucideIcon; tint: string; digits?: number; suffix?: string }[] = [
  { k: "tons", label: "k_tons", icon: Recycle, tint: "from-emerald-400 to-green-600" },
  { k: "mau", label: "k_mau", icon: Users, tint: "from-sky-400 to-blue-600" },
  { k: "participation", label: "k_part", icon: Percent, tint: "from-violet-400 to-purple-600", digits: 1, suffix: "٪" },
  { k: "landfillSaved", label: "k_landfill", icon: Mountain, tint: "from-amber-400 to-orange-600" },
  { k: "co2", label: "k_co2", icon: Cloud, tint: "from-cyan-400 to-teal-600" },
  { k: "partners", label: "k_partners", icon: Handshake, tint: "from-pink-400 to-rose-600" },
];

function Area({ data }: { data: City["months"] }) {
  const { locale, n } = useI18n();
  const [on, setOn] = useState(false);
  useEffect(() => { requestAnimationFrame(() => setOn(true)); }, []);
  const W = 600, H = 220, max = Math.max(...data.map((d) => d.tons)) * 1.15;
  const pts = data.map((d, i) => [(i / (data.length - 1)) * W, H - (d.tons / max) * H] as const);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x},${y}`).join(" ");
  const now = new Date();
  const label = (i: number) => new Date(now.getFullYear(), now.getMonth() - (data.length - 1 - i), 15)
    .toLocaleDateString(locale === "fa" ? "fa-IR-u-ca-persian" : "en-US", { month: "short" });
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-56 w-full overflow-visible rtl:-scale-x-100" preserveAspectRatio="none">
        <defs>
          <linearGradient id="fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="var(--brand)" stopOpacity=".45" /><stop offset="1" stopColor="var(--brand)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((g) => <line key={g} x1="0" x2={W} y1={H * g} y2={H * g} stroke="var(--line)" strokeDasharray="4 6" vectorEffect="non-scaling-stroke" />)}
        <path d={`${line} L${W},${H} L0,${H} Z`} fill="url(#fill)" style={{ opacity: on ? 1 : 0, transition: "opacity 1.2s .4s" }} />
        <path d={line} fill="none" stroke="var(--brand)" strokeWidth="3" strokeLinejoin="round" vectorEffect="non-scaling-stroke" pathLength={1}
          strokeDasharray="1" strokeDashoffset={on ? 0 : 1} style={{ transition: "stroke-dashoffset 1.8s cubic-bezier(.2,.8,.2,1)" }} />
        {pts.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="5" fill="var(--bg)" stroke="var(--brand)" strokeWidth="2.5" vectorEffect="non-scaling-stroke" className="cursor-pointer">
            <title>{`${label(i)}: ${n(data[i].tons)}`}</title>
          </circle>
        ))}
      </svg>
      <div className="mt-2 flex justify-between text-[11px] text-muted">{data.map((_, i) => <span key={i} className={i % 2 ? "hidden sm:inline" : ""}>{label(i)}</span>)}</div>
    </div>
  );
}

function Donut({ mix, cat, total }: { mix: City["materials"]; cat: Catalog; total: number }) {
  const { n, pick } = useI18n();
  const r = 70, c = 2 * Math.PI * r;
  let acc = 0;
  return (
    <div className="flex flex-wrap items-center justify-center gap-6">
      <div className="relative">
        <svg width="190" height="190" viewBox="0 0 190 190" className="-rotate-90">
          {mix.map((m) => {
            const len = (m.pct / 100) * c, off = acc;
            acc += len;
            return <circle key={m.id} cx="95" cy="95" r={r} fill="none" stroke={cat.materials[m.id].color} strokeWidth="26" strokeDasharray={`${len - 3} ${c}`} strokeDashoffset={-off} />;
          })}
        </svg>
        <div className="absolute inset-0 grid place-items-center text-center"><div><div className="text-2xl font-extrabold"><Counter value={total} /></div><div className="text-xs text-muted">t</div></div></div>
      </div>
      <ul className="grid gap-2 text-sm">
        {mix.map((m) => (
          <li key={m.id} className="flex items-center gap-2">
            <span className="size-3 rounded-full" style={{ background: cat.materials[m.id].color }} />
            <span className="flex-1">{pick(cat.materials[m.id])}</span>
            <span className="tnum font-bold">{n(m.pct)}٪</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function CityPage() {
  const { t, n, pick } = useI18n();
  const city = useApi<City>("/city"), cat = useApi<Catalog>("/catalog");
  if (city.error || cat.error) return <ErrorBox onRetry={() => { city.reload(); cat.reload(); }} />;
  if (!city.data || !cat.data) return <Loading rows={4} />;
  const { kpi, months, materials, districts } = city.data;
  const max = districts[0].points;
  return (
    <>
      <PageHeader title={t("city_title")} sub={t("city_sub")}>
        <span className="flex items-center gap-2 rounded-full bg-brand-soft px-4 py-2 text-sm font-bold text-brand">
          <span className="relative flex size-2.5"><span className="absolute inline-flex size-full animate-ping rounded-full bg-brand opacity-75" /><span className="relative inline-flex size-2.5 rounded-full bg-brand" /></span> LIVE
        </span>
      </PageHeader>
      <div className="stagger grid grid-cols-1 gap-5">
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
          {KPI.map(({ k, label, icon: Icon, tint, digits, suffix }) => (
            <div key={k} className="card p-5">
              <span className={`grid size-10 place-items-center rounded-xl bg-gradient-to-br ${tint} text-white shadow-lg`}><Icon size={20} /></span>
              <div className="mt-4 text-2xl font-extrabold"><Counter value={kpi[k]} digits={digits} />{suffix}</div>
              <div className="text-xs text-muted">{t(label)}</div>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          <section className="card p-6 lg:col-span-2"><h2 className="mb-4 font-bold">{t("monthly")}</h2><Area data={months} /></section>
          <section className="card p-6"><h2 className="mb-4 font-bold">{t("mix")}</h2><Donut mix={materials} cat={cat.data} total={kpi.tons} /></section>
        </div>
        <section className="card p-6">
          <h2 className="mb-5 font-bold">{t("districts")}</h2>
          <div className="grid gap-x-10 gap-y-4 md:grid-cols-2">
            {districts.map((d, i) => (
              <div key={d.id}>
                <div className="mb-1.5 flex justify-between text-sm"><span className="font-semibold">{n(i + 1)}. {pick(d)}</span><span className="tnum text-muted">{n(d.points)}</span></div>
                <div className="h-2.5 overflow-hidden rounded-full bg-line"><div className="h-full rounded-full bg-gradient-to-r from-sky-400 to-brand" style={{ width: `${(d.points / max) * 100}%` }} /></div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}
