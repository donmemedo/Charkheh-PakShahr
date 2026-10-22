"use client";
import { useState } from "react";
import { Check, Crown, X } from "lucide-react";
import { api, refresh, useApi, type Catalog, type District, type Mission } from "@/lib/api";
import { useI18n, type Key } from "@/lib/i18n";
import { ErrorBox, Loading, PageHeader, SampleBadge, errKey } from "@/components/ui";

function Quiz({ m, i }: { m: Mission; i: number }) {
  const { t, n, signed, locale } = useI18n();
  const [res, setRes] = useState<{ choice: number; correct: boolean; answer?: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<Key | "">("");
  const q = m[locale];
  const choose = async (choice: number) => {
    if (busy) return;
    setBusy(true); setErr(""); setRes(null); // clearing first lets a repeated "wrong" be announced again
    try {
      const r = await api<{ correct: boolean; answer?: number }>(`/missions/${m.id}/answer`, { choice });
      setRes({ choice, ...r });
      if (r.correct) setTimeout(refresh, 900);
    } catch (e) {
      setErr(errKey(e));
      if ((e as { status?: number }).status === 409) refresh(); // already done (another tab, a double submit): flip the card to Done
    } finally { setBusy(false); }
  };
  const solved = m.done || res?.correct;
  return (
    <article className={`card p-6 ${res && !res.correct ? "shake" : ""}`}>
      <div className="mb-3 flex items-center justify-between text-xs font-bold">
        <span className="text-muted">#{n(i + 1)}</span>
        <span className={`rounded-full px-3 py-1 ${solved ? "bg-brand-fill text-on-brand" : "bg-amber-500/15 text-amber-text"}`}>{solved ? `✓ ${t("done")}` : `${signed(m.pts)} ${t("pts")}`}</span>
      </div>
      <h3 className="text-lg font-bold leading-snug">{q.q}</h3>
      <div className="mt-4 grid gap-2">
        {q.a.map((a, j) => {
          const picked = res?.choice === j, right = solved && (res ? res.answer === j : false);
          return (
            <button key={j} disabled={!!solved || busy} onClick={() => choose(j)}
              className={`press flex items-center justify-between rounded-2xl border px-4 py-3 text-start text-sm font-medium transition-colors
                ${right ? "border-brand bg-brand-soft text-brand-text" : picked ? "border-red-400 bg-red-500/10 text-danger" : "border-line hover:bg-line"} disabled:cursor-default`}>
              {a}
              {right ? <Check size={18} className="pop" /> : picked ? <X size={18} className="pop" /> : null}
            </button>
          );
        })}
      </div>
      <p role="status" className={`mt-3 text-sm font-semibold empty:mt-0 ${res?.correct ? "text-brand-text" : "text-danger"}`}>{res ? (res.correct ? `${t("correct")} ${signed(m.pts)}` : t("wrong")) : ""}</p>
      {err && !solved && <p role="alert" className="mt-3 text-sm font-semibold text-danger">{t(err)}</p>}
      {res && !res.correct && <button className="hit mt-2 text-sm text-muted underline" onClick={() => setRes(null)}>{t("retry")}</button>}
    </article>
  );
}

function League({ rows }: { rows: District[] }) {
  const { t, n, pick } = useI18n();
  const max = rows[0]?.points || 1;
  return (
    <section className="card p-6">
      <div className="flex items-center justify-between gap-3"><h2 className="text-lg font-bold">{t("league")}</h2><SampleBadge /></div>
      <p className="mb-5 text-sm text-muted">{t("league_sub")}</p>
      <ol className="grid gap-3">
        {rows.map((d, i) => (
          <li key={d.id} className={`rounded-2xl p-3 ${d.mine ? "bg-brand-soft ring-1 ring-brand/40" : ""}`}>
            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 font-semibold">
                <span className={`grid size-7 place-items-center rounded-full text-xs ${i === 0 ? "bg-gradient-to-br from-yellow-300 to-amber-500 text-black" : "bg-line"}`}>{i === 0 ? <Crown size={14} /> : n(i + 1)}</span>
                {pick(d)} {d.mine && <span className="text-xs text-brand-text">{t("you")}</span>}
              </span>
              <span className="tnum text-muted">{n(d.points)}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-line">
              <div className="h-full origin-[inline-start] rounded-full bg-gradient-to-r from-brand to-brand-2 transition-[width] duration-1000" style={{ width: `${(d.points / max) * 100}%` }} />
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

export default function Missions() {
  const { t } = useI18n();
  const cat = useApi<Catalog>("/catalog"), lb = useApi<District[]>("/leaderboard");
  if (cat.error || lb.error) return <ErrorBox onRetry={() => { cat.reload(); lb.reload(); }} />;
  if (!cat.data || !lb.data) return <Loading rows={3} />;
  return (
    <>
      <PageHeader title={t("missions_title")} sub={t("missions_sub")} />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-5">
        <div className="stagger grid min-w-0 grid-cols-1 gap-5 md:grid-cols-2 lg:col-span-3 lg:grid-cols-1 xl:grid-cols-2">
          {cat.data.missions.map((m, i) => <Quiz key={m.id} m={m} i={i} />)}
        </div>
        <div className="lg:col-span-2"><div className="lg:sticky lg:top-10"><League rows={lb.data} /></div></div>
      </div>
    </>
  );
}
