"use client";
import { useState } from "react";
import { Bike, BookOpen, Check, Clapperboard, Coffee, Copy, ShoppingBasket, Sparkles, Sprout, TrainFront, Wifi, type LucideIcon } from "lucide-react";
import { api, refresh, useApi, type Catalog, type Reward, type State } from "@/lib/api";
import { useI18n, type Key } from "@/lib/i18n";
import { Confetti, Counter, ErrorBox, Loading, PageHeader, Sheet } from "@/components/ui";

const ICON: Record<string, LucideIcon> = { metro: TrainFront, coffee: Coffee, grocery: ShoppingBasket, book: BookOpen, net: Wifi, tree: Sprout, bike: Bike, cinema: Clapperboard };
const GRAD: Record<string, string> = {
  transport: "from-sky-400 to-indigo-500", food: "from-orange-400 to-rose-500", shopping: "from-fuchsia-400 to-purple-600",
  digital: "from-cyan-400 to-blue-600", impact: "from-lime-400 to-emerald-600",
};

export default function Rewards() {
  const { t, n, pick } = useI18n();
  const cat = useApi<Catalog>("/catalog"), st = useApi<State>("/state");
  const [filter, setFilter] = useState("all");
  const [sel, setSel] = useState<Reward | null>(null);
  const [code, setCode] = useState("");
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);

  if (cat.error || st.error) return <ErrorBox onRetry={() => { cat.reload(); st.reload(); }} />;
  if (!cat.data || !st.data) return <Loading rows={3} />;
  const balance = st.data.balance;
  const cats = ["all", ...new Set(cat.data.rewards.map((r) => r.cat))];
  const list = cat.data.rewards.filter((r) => filter === "all" || r.cat === filter);
  const close = () => { setSel(null); setCode(""); setCopied(false); };
  const redeem = async () => {
    setBusy(true);
    try { setCode((await api<{ code: string }>(`/rewards/${sel!.id}/redeem`, {})).code); refresh(); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title={t("rewards_title")} sub={t("rewards_sub")}>
        <div className="glass flex items-center gap-2 rounded-full px-5 py-2.5 font-bold">
          <Sparkles size={18} className="text-brand" /> <Counter value={balance} /> <span className="text-sm font-normal text-muted">{t("points")}</span>
        </div>
      </PageHeader>

      <div className="-mx-4 mb-6 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none]">
        {cats.map((c) => (
          <button key={c} aria-pressed={filter === c} onClick={() => setFilter(c)} className="chip press shrink-0 px-4 py-2 text-sm font-semibold">{t(`cat_${c}` as Key)}</button>
        ))}
      </div>

      <div key={filter} className="stagger grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {list.map((r) => {
          const Icon = ICON[r.id] ?? Sparkles, can = balance >= r.cost;
          return (
            <article key={r.id} className="card press lift group flex flex-col overflow-hidden">
              <div className={`relative grid h-36 place-items-center bg-gradient-to-br ${GRAD[r.cat]} text-white`}>
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgb(255_255_255/.35),transparent_60%)]" />
                <Icon size={56} strokeWidth={1.6} className="drop-shadow-lg transition-transform duration-500 group-hover:scale-110 group-hover:-rotate-6" />
              </div>
              <div className="flex flex-1 flex-col gap-1 p-5">
                <span className="text-xs text-muted">{pick(r.partner)}</span>
                <h3 className="font-bold leading-snug">{pick(r)}</h3>
                <div className="mt-auto flex items-center justify-between pt-4">
                  <span className="font-extrabold">{n(r.cost)} <span className="text-xs font-normal text-muted">{t("pts")}</span></span>
                  <button disabled={!can} onClick={() => setSel(r)} className="btn btn-primary press h-10 px-4 text-sm">{can ? t("redeem") : t("need_more")}</button>
                </div>
              </div>
            </article>
          );
        })}
      </div>

      <Sheet open={!!sel} onClose={close}>
        {sel && !code && (
          <div className="flex flex-col gap-4 text-center">
            <div className={`mx-auto grid size-20 place-items-center rounded-3xl bg-gradient-to-br ${GRAD[sel.cat]} text-white shadow-xl`}>{(() => { const I = ICON[sel.id] ?? Sparkles; return <I size={36} />; })()}</div>
            <h2 className="text-xl font-extrabold">{t("redeem_q")}</h2>
            <p className="font-semibold">{pick(sel)}</p>
            <p className="text-sm text-muted"><b className="text-fg">{n(sel.cost)} {t("pts")}</b> {t("redeem_cost")}</p>
            <div className="mt-2 grid grid-cols-2 gap-3">
              <button className="btn press bg-line" onClick={close}>{t("cancel")}</button>
              <button className="btn btn-primary press" disabled={busy} onClick={redeem}>{t("redeem")}</button>
            </div>
          </div>
        )}
        {code && (
          <div className="flex flex-col items-center gap-4 text-center">
            <Confetti />
            <span className="pop grid size-16 place-items-center rounded-full bg-brand text-white"><Check size={32} strokeWidth={3} /></span>
            <h2 className="text-xl font-extrabold">{t("redeemed")}</h2>
            <p className="text-sm text-muted">{t("your_code")}</p>
            <button onClick={() => { navigator.clipboard?.writeText(code); setCopied(true); }}
              className="press flex w-full items-center justify-between rounded-2xl border-2 border-dashed border-brand/50 bg-brand-soft px-5 py-4 font-mono text-2xl font-bold tracking-widest" dir="ltr">
              {code} <span className="flex items-center gap-1 font-sans text-sm tracking-normal text-brand">{copied ? <Check size={16} /> : <Copy size={16} />} {copied ? t("copied") : t("copy")}</span>
            </button>
            <button className="btn btn-primary press w-full" onClick={close}>{t("ok")}</button>
          </div>
        )}
      </Sheet>
    </>
  );
}
