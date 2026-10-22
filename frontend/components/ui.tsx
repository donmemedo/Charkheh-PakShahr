"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { CupSoda, Milk, Newspaper, Smartphone, Wine, type LucideIcon } from "lucide-react";
import { useI18n, type Key } from "@/lib/i18n";
import type { MaterialId } from "@/lib/api";

export const MATERIAL_ICON: Record<MaterialId, LucideIcon> = { paper: Newspaper, plastic: Milk, metal: CupSoda, glass: Wine, ewaste: Smartphone };

/** Copy key for a failed api() call; `map` overrides per status (e.g. {409: "need_more"}).
 *  Callers store the key and translate at render, so a language switch also switches a visible error. */
export function errKey(e: unknown, map: Partial<Record<number, Key>> = {}): Key {
  const s = (e as { status?: number })?.status ?? 0;
  return map[s] ?? (s === 409 ? "conflict" : s === 429 ? "slow_down" : s === 400 || s === 422 ? "invalid" : "error");
}

/** Number that springs to its new value. Writes the DOM directly: no React render per frame. */
export function Counter({ value, digits = 0 }: { value: number; digits?: number }) {
  const { n } = useI18n();
  const el = useRef<HTMLSpanElement>(null);
  const fmt = useRef(n), from = useRef(0);
  useLayoutEffect(() => { fmt.current = n; }); // a count in flight switches locale with the page
  useLayoutEffect(() => {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) { from.current = value; el.current!.textContent = fmt.current(value, digits); return; }
    const start = performance.now(), a = from.current;
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, Math.max(0, now - start) / 1400), e = p === 1 ? 1 : 1 - Math.pow(2, -10 * p);
      from.current = a + (value - a) * e; // a new value restarts from what is on screen, not from the old start
      el.current!.textContent = fmt.current(from.current, digits);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    tick(start); // before paint: the first frame already shows the start value
    return () => cancelAnimationFrame(raf);
  }, [value, digits]);
  return <span ref={el} className="tnum">{n(value, digits)}</span>;
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

const DECEL = 0.998; // scroll-like deceleration for momentum projection
const RESPONSE = 0.3; // spring response (s), Apple sheet: damping ratio .8 after a flick, 1 (no bounce) otherwise

/** Native <dialog>: bottom sheet on phones, centered card on desktop. On phones it tracks the finger 1:1 and springs home or away.
 *  `labelledBy` is the id of the heading inside, which names the dialog. */
export function Sheet({ open, onClose, labelledBy, children }: { open: boolean; onClose: () => void; labelledBy: string; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  const g = useRef({ id: -1, drag: false, y: 0, v: 0, start: 0, grab: 0, hist: [] as [number, number][], raf: 0 });
  useEffect(() => {
    const d = ref.current!;
    if (open && !d.open) { cancelAnimationFrame(g.current.raf); d.style.transform = d.style.transition = ""; g.current.y = g.current.v = 0; d.showModal(); }
    if (!open && d.open) { cancelAnimationFrame(g.current.raf); d.close(); }
  }, [open]);
  useEffect(() => { const s = g.current; return () => cancelAnimationFrame(s.raf); }, []); // no frame outlives the sheet
  const set = (y: number) => { const d = ref.current!; g.current.y = y; d.style.transition = "none"; d.style.transform = `translateY(${y}px)`; };
  const spring = (to: number, done?: () => void) => {
    const s = g.current, k = (2 * Math.PI / RESPONSE) ** 2, c = (4 * Math.PI * (Math.abs(s.v) > 300 ? 0.8 : 1)) / RESPONSE;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.032, Math.max(0, now - last) / 1000); last = now;
      s.v += (-k * (s.y - to) - c * s.v) * dt; set(s.y + s.v * dt);
      if (Math.abs(s.y - to) > 0.5 || Math.abs(s.v) > 20) s.raf = requestAnimationFrame(tick);
      else if (done) done(); else { ref.current!.style.transform = ref.current!.style.transition = ""; s.y = s.v = 0; }
    };
    s.raf = requestAnimationFrame(tick);
  };
  // take over from the live on-screen position (a running spring or the CSS entrance), then follow the finger 1:1
  const grab = (e: React.PointerEvent<HTMLDivElement>) => {
    const s = g.current;
    e.currentTarget.setPointerCapture(e.pointerId);
    s.y = new DOMMatrix(getComputedStyle(ref.current!).transform).m42; s.grab = e.clientY - s.y; s.hist = [[e.timeStamp, s.y]]; s.drag = true;
  };
  const down = (e: React.PointerEvent<HTMLDivElement>) => {
    const s = g.current;
    if (!e.isPrimary || e.button || matchMedia("(min-width: 768px), (prefers-reduced-motion: reduce)").matches) return;
    cancelAnimationFrame(s.raf); // a touch catches the sheet mid-flight
    s.id = e.pointerId; s.drag = false; s.start = e.clientY; s.v = 0; s.hist = [[e.timeStamp, s.y]];
    if ((e.target as Element).closest("[data-handle]")) grab(e); // the handle drags at once; elsewhere taps stay taps
  };
  const move = (e: React.PointerEvent<HTMLDivElement>) => {
    const s = g.current, el = e.currentTarget;
    if (e.pointerId !== s.id || !e.buttons) return;
    if (!s.drag) { // not hasPointerCapture: a touch is implicitly captured by the element it lands on, the panel's padding included
      if (Math.abs(e.clientY - s.start) < 10) return; // 10 px hysteresis so buttons inside (copy code, OK) still get their click
      grab(e);
    }
    const h = el.offsetHeight, raw = e.clientY - s.grab;
    set(raw < 0 ? -(-raw * h * 0.55) / (h + 0.55 * -raw) : raw); // rubber-band past the top
    s.hist.push([e.timeStamp, s.y]); while (s.hist.length > 1 && e.timeStamp - s.hist[0][0] > 100) s.hist.shift();
  };
  const up = (e: React.PointerEvent<HTMLDivElement>) => {
    const s = g.current, el = e.currentTarget;
    if (e.pointerId !== s.id) return;
    s.id = -1;
    if (!s.drag && !s.y) return; // a tap on a resting sheet: leave it alone (capture ends by itself after pointerup)
    // release velocity from the last 100 ms (0 when a tap merely caught the sheet), projected to where a flick would stop
    const [t0, y0] = s.hist[0], dt = e.timeStamp - t0, h = el.offsetHeight;
    s.v = dt > 0 ? ((s.y - y0) / dt) * 1000 : 0;
    const rest = s.y + (s.v / 1000) * DECEL / (1 - DECEL);
    spring(rest > h / 2 ? h + 24 : 0, rest > h / 2 ? onClose : undefined);
  };
  // the dialog hands focus back to its opener; if that is gone or disabled (a redeem that spent the last points), focus
  // stays on a button inside the sheet (still rendered for its exit transition) or drops to <body>: use <main> then
  const closed = () => {
    const a = document.activeElement;
    if (!a || a === document.body || ref.current!.contains(a)) document.getElementById("main")?.focus({ preventScroll: true });
    onClose();
  };
  return (
    <dialog ref={ref} className="sheet" aria-labelledby={labelledBy} onClose={closed} onClick={(e) => e.target === ref.current && onClose()}>
      <div className="panel m-3 rounded-[32px] p-6 pb-[max(1.5rem,env(safe-area-inset-bottom))]" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}>
        <div data-handle aria-hidden className="-mx-6 -mt-6 mb-2 flex justify-center pt-4 pb-2 md:hidden"><span className="h-1.5 w-10 rounded-full bg-line" /></div>
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

/** Marks figures from the seeded demo generator. Say "live" again only once they come from real per-user data. */
export function SampleBadge() {
  const { t } = useI18n();
  return (
    <span className="flex shrink-0 items-center gap-2 rounded-full bg-amber-500/15 px-3 py-1.5 text-xs font-bold text-amber-text">
      <span aria-hidden className="size-2 rounded-full bg-amber-500" /> {t("sample")}
    </span>
  );
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return <div className="grid gap-4">{Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton h-32" />)}</div>;
}

export function ErrorBox({ onRetry, text = "error" }: { onRetry: () => void; text?: Key }) {
  const { t } = useI18n();
  return (
    <div className="card flex flex-col items-center gap-4 p-10 text-center">
      <p className="text-muted">{t(text)}</p>
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
