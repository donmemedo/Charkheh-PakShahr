"use client";
import { useEffect, useRef, useState } from "react";
import { Bike, BookOpen, Check, Clapperboard, Coffee, Copy, ShoppingBasket, Sparkles, Sprout, TrainFront, Wifi, X, type LucideIcon } from "lucide-react";
import { api, refresh, useApi, type Catalog, type Reward, type State } from "@/lib/api";
import { formatDay, useI18n, type Key } from "@/lib/i18n";
import { Confetti, Counter, ErrorBox, Loading, PageHeader, Sheet, errKey } from "@/components/ui";

const ICON: Record<string, LucideIcon> = { metro: TrainFront, coffee: Coffee, grocery: ShoppingBasket, book: BookOpen, net: Wifi, tree: Sprout, bike: Bike, cinema: Clapperboard };
const GRAD: Record<string, string> = {
  transport: "from-sky-400 to-indigo-500", food: "from-orange-400 to-rose-500", shopping: "from-fuchsia-400 to-purple-600",
  digital: "from-cyan-400 to-blue-600", impact: "from-lime-400 to-emerald-600",
};

/** The code plus a Copy button that says "Copied" only once the copy happened; with no clipboard API
 *  (plain HTTP) or a denied permission it selects the code and tries the legacy copy command. */
function CopyCode({ code, small }: { code: string; small?: boolean }) {
  const { t } = useI18n();
  const el = useRef<HTMLElement>(null);
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(code); setCopied(true); }
    catch { getSelection()?.selectAllChildren(el.current!); if (document.execCommand("copy")) setCopied(true); }
  };
  return (
    <div dir="ltr" className={`flex items-center justify-between gap-3 rounded-2xl border-2 border-dashed border-brand/50 bg-brand-soft ${small ? "px-3 py-1.5" : "w-full flex-col px-3 py-4"}`}>
      <code ref={el} className={`select-all font-mono font-bold tracking-wider whitespace-nowrap ${small ? "text-sm" : "text-xl"}`}>{code}</code>
      <button onClick={copy} className="press hit flex items-center gap-1 text-sm font-semibold text-brand-text">
        {copied ? <Check size={16} /> : <Copy size={16} />} {copied ? t("copied") : t("copy")}
      </button>
    </div>
  );
}

// ponytail: codes live in this browser only (newest 20), until accounts exist and the server can list a citizen's codes
type Saved = { code: string; rid: string; ts: string };
const CODES = "sabz:codes";
// storage is shared with anything else on this origin: keep only well-formed entries, or one bad value breaks the page
const readCodes = (): Saved[] => {
  try {
    const v = JSON.parse(localStorage.getItem(CODES) ?? "[]");
    return Array.isArray(v) ? v.filter((c): c is Saved => typeof c?.code === "string" && typeof c.rid === "string" && typeof c.ts === "string").slice(0, 20) : [];
  } catch { return []; }
};
const writeCodes = (v: Saved[]) => { try { localStorage.setItem(CODES, JSON.stringify(v)); } catch {} return v; };

export default function Rewards() {
  const { t, n, pick, locale } = useI18n();
  const cat = useApi<Catalog>("/catalog"), st = useApi<State>("/state");
  const [filter, setFilter] = useState("all");
  const [sel, setSel] = useState<Reward | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<Key | "">("");
  const [codes, setCodes] = useState<Saved[]>([]);
  useEffect(() => { // after hydration (the server render has no storage); re-read when another tab writes, so a save there is not lost here
    const sync = () => setCodes(readCodes());
    sync(); addEventListener("storage", sync);
    return () => removeEventListener("storage", sync);
  }, []);
  const keep = (f: (v: Saved[]) => Saved[]) => setCodes((v) => writeCodes(f(v))); // the list still works when storage is blocked

  if (cat.error || st.error) return <ErrorBox onRetry={() => { cat.reload(); st.reload(); }} />;
  if (!cat.data || !st.data) return <Loading rows={3} />;
  const balance = st.data.balance;
  const cats = ["all", ...new Set(cat.data.rewards.map((r) => r.cat))];
  const list = cat.data.rewards.filter((r) => filter === "all" || r.cat === filter);
  const close = () => { setSel(null); setCode(""); setErr(""); };
  const redeem = async () => {
    setBusy(true); setErr("");
    try {
      const { code } = await api<{ code: string }>(`/rewards/${sel!.id}/redeem`, {});
      setCode(code);
      keep((v) => [{ code, rid: sel!.id, ts: new Date().toISOString() }, ...v].slice(0, 20));
      refresh();
    } catch (e) { setErr(errKey(e, { 409: "need_more" })); refresh(); } finally { setBusy(false); }
  };
  const forget = (c: string) => keep((v) => v.filter((x) => x.code !== c));

  return (
    <>
      <PageHeader title={t("rewards_title")} sub={t("rewards_sub")}>
        <div className="chip flex items-center gap-2 rounded-full px-5 py-2.5 font-bold">
          <Sparkles size={18} className="text-brand" /> <Counter value={balance} /> <span className="text-sm font-normal text-muted">{t("points")}</span>
        </div>
      </PageHeader>

      {codes.length > 0 && (
        <section aria-labelledby="my-codes" className="card mb-6 p-5">
          <h2 id="my-codes" className="font-bold">{t("my_codes")}</h2>
          <p className="mb-3 text-xs text-muted">{t("my_codes_sub")}</p>
          <ul className="divide-y divide-line">
            {codes.map((c) => {
              const r = cat.data!.rewards.find((x) => x.id === c.rid);
              return (
                <li key={c.code} className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3">
                  <div className="min-w-40 flex-1">
                    <div className="truncate text-sm font-semibold">{r ? pick(r) : c.rid}</div>
                    <div className="text-xs text-muted">{formatDay(c.ts, locale, { day: "numeric", month: "long", year: "numeric" })}</div>
                  </div>
                  <CopyCode code={c.code} small />
                  <button onClick={() => forget(c.code)} aria-label={`${t("remove")}: ${c.code}`} title={t("remove")} className="press hit grid size-8 place-items-center rounded-full text-muted hover:bg-line hover:text-fg"><X size={16} /></button>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* py-1: the scroller clips overflow, so the chips' 44 px touch area needs the room */}
      <div className="-mx-4 mb-5 flex gap-2 overflow-x-auto px-4 py-1 [scrollbar-width:none]">
        {cats.map((c) => (
          <button key={c} aria-pressed={filter === c} onClick={() => setFilter(c)} className="chip press hit shrink-0 px-4 py-2 text-sm font-semibold">{t(`cat_${c}` as Key)}</button>
        ))}
      </div>

      <div key={filter} className="stagger grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {list.map((r) => {
          const Icon = ICON[r.id] ?? Sparkles, can = balance >= r.cost;
          return (
            <article key={r.id} className="card press lift group flex flex-col overflow-hidden">
              <div className={`relative grid h-24 place-items-center bg-gradient-to-br sm:h-36 ${GRAD[r.cat]} text-white`}>
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgb(255_255_255/.35),transparent_60%)]" />
                <Icon size={56} strokeWidth={1.6} className="drop-shadow-lg transition-transform duration-500 group-hover:scale-110 group-hover:-rotate-6" />
              </div>
              <div className="flex flex-1 flex-col gap-1 p-5">
                <span className="text-xs text-muted">{pick(r.partner)}</span>
                {/* U+2060 after a hyphen: "top-up" never splits across lines */}
                <h3 className="font-bold leading-snug text-balance">{pick(r).replaceAll("-", "-\u2060")}</h3>
                <div className="mt-auto flex items-center justify-between pt-4">
                  <span className="font-extrabold">{n(r.cost)} <span className="text-xs font-normal text-muted">{t("pts")}</span></span>
                  <button disabled={!can} onClick={() => setSel(r)} className="btn btn-primary press hit h-10 px-4 text-sm">{can ? t("redeem") : t("need_more")}</button>
                </div>
              </div>
            </article>
          );
        })}
      </div>

      <Sheet open={!!sel} onClose={close} labelledBy="reward-sheet-title">
        {sel && !code && (
          <div className="flex flex-col gap-4 text-center">
            <div className={`mx-auto grid size-20 place-items-center rounded-3xl bg-gradient-to-br ${GRAD[sel.cat]} text-white shadow-xl`}>{(() => { const I = ICON[sel.id] ?? Sparkles; return <I size={36} />; })()}</div>
            <h2 id="reward-sheet-title" className="text-xl font-extrabold">{t("redeem_q")}</h2>
            <p className="font-semibold">{pick(sel)}</p>
            <p className="text-sm text-muted"><b className="text-fg">{n(sel.cost)} {t("pts")}</b> {t("redeem_cost")}</p>
            {err && <p role="alert" className="text-sm font-semibold text-danger">{t(err)}</p>}
            <div className="mt-2 grid grid-cols-2 gap-3">
              <button className="btn press bg-line" onClick={close}>{t("cancel")}</button>
              <button className="btn btn-primary press" disabled={busy} onClick={redeem}>{t("redeem")}</button>
            </div>
          </div>
        )}
        {code && (
          <div className="flex flex-col items-center gap-4 text-center">
            <Confetti />
            <span className="pop grid size-16 place-items-center rounded-full bg-brand-fill text-on-brand"><Check size={32} strokeWidth={3} /></span>
            <h2 id="reward-sheet-title" className="text-xl font-extrabold">{t("redeemed")}</h2>
            <p className="text-sm text-muted">{t("your_code")}</p>
            <CopyCode code={code} />
            <button className="btn btn-primary press w-full" onClick={close}>{t("ok")}</button>
          </div>
        )}
      </Sheet>
    </>
  );
}
