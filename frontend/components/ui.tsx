"use client";
import { useEffect, useRef, useState } from "react";
import { CupSoda, Milk, Newspaper, Smartphone, Wine, type LucideIcon } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import type { MaterialId } from "@/lib/api";

export const MATERIAL_ICON: Record<MaterialId, LucideIcon> = { paper: Newspaper, plastic: Milk, metal: CupSoda, glass: Wine, ewaste: Smartphone };

/** Number that springs to its new value. */
export function Counter({ value, digits = 0 }: { value: number; digits?: number }) {
  const { n } = useI18n();
  const [shown, setShown] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    const start = performance.now(), a = from.current;
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / 1400), e = p === 1 ? 1 : 1 - Math.pow(2, -10 * p);
      setShown(a + (value - a) * e);
      if (p < 1) raf = requestAnimationFrame(tick); else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <span className="tnum">{n(shown, digits)}</span>;
}

/** Apple Watch-style activity rings. values are 0..1. */
export function Rings({ rings, size = 168 }: { rings: { value: number; color: string }[]; size?: number }) {
  const [on, setOn] = useState(false);
  useEffect(() => { const t = setTimeout(() => setOn(true), 150); return () => clearTimeout(t); }, []);
  const stroke = size / 11;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90 shrink-0" aria-hidden>
      {rings.map((r, i) => {
        const rad = size / 2 - stroke / 2 - i * (stroke + 3), c = 2 * Math.PI * rad;
        return (
          <g key={i}>
            <circle cx={size / 2} cy={size / 2} r={rad} fill="none" stroke={r.color} strokeOpacity={0.18} strokeWidth={stroke} />
            <circle className="ring" cx={size / 2} cy={size / 2} r={rad} fill="none" stroke={r.color} strokeWidth={stroke} strokeLinecap="round"
              strokeDasharray={c} strokeDashoffset={on ? c * (1 - Math.min(r.value, 1)) : c} style={{ filter: `drop-shadow(0 0 6px ${r.color}66)` }} />
          </g>
        );
      })}
    </svg>
  );
}

/** Native <dialog>: bottom sheet on phones, centered card on desktop. */
export function Sheet({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current!;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} className="sheet" onClose={onClose} onClick={(e) => e.target === ref.current && onClose()}>
      <div className="glass m-3 rounded-[32px] p-6 pb-[max(1.5rem,env(safe-area-inset-bottom))] shadow-2xl" style={{ background: "var(--glass-strong)" }}>
        <div className="mx-auto -mt-2 mb-4 h-1.5 w-10 rounded-full bg-line md:hidden" />
        {children}
      </div>
    </dialog>
  );
}

const CONFETTI = ["#22c55e", "#06b6d4", "#facc15", "#f97316", "#a855f7", "#ec4899"];
export function Confetti() {
  const [bits] = useState(() => Array.from({ length: 70 }, (_, i) => ({
    left: Math.random() * 100, dx: (Math.random() - 0.5) * 40 + "vw", r: Math.random() * 900 + "deg", delay: Math.random() * 0.4, color: CONFETTI[i % CONFETTI.length],
  })));
  return (
    <div className="confetti pointer-events-none fixed inset-0 z-[60] overflow-hidden" aria-hidden>
      {bits.map((b, i) => <i key={i} style={{ left: `${b.left}%`, background: b.color, animationDelay: `${b.delay}s`, ["--dx" as string]: b.dx, ["--r" as string]: b.r }} />)}
    </div>
  );
}

export function PageHeader({ title, sub, children }: { title: string; sub?: string; children?: React.ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="title-xl">{title}</h1>
        {sub && <p className="mt-2 max-w-xl text-muted">{sub}</p>}
      </div>
      {children}
    </header>
  );
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return <div className="grid gap-4">{Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton h-32" />)}</div>;
}

export function ErrorBox({ onRetry }: { onRetry: () => void }) {
  const { t } = useI18n();
  return (
    <div className="card flex flex-col items-center gap-4 p-10 text-center">
      <p className="text-muted">{t("error")}</p>
      <button className="btn btn-ghost press" onClick={onRetry}>{t("retry")}</button>
    </div>
  );
}

export const TIER_STYLE = {
  bronze: "from-amber-700 to-orange-400",
  silver: "from-slate-400 to-slate-200",
  gold: "from-yellow-500 to-amber-200",
} as const;

/** "08-11" → "۸ تا ۱۱" / "8–11" */
export function Slot({ s }: { s: string }) {
  const { n, locale } = useI18n();
  const [a, b] = s.split("-").map(Number);
  return <span className="tnum">{locale === "fa" ? `${n(a)} تا ${n(b)}` : `${a}:00–${b}:00`}</span>;
}
