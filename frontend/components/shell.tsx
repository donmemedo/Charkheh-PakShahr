"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Gift, House, Landmark, Monitor, Moon, Plus, Receipt, Recycle, Sun, Target, type LucideIcon } from "lucide-react";
import { useI18n, type Key } from "@/lib/i18n";

const NAV: { href: string; key: Key; icon: LucideIcon }[] = [
  { href: "/", key: "nav_home", icon: House },
  { href: "/rewards", key: "nav_rewards", icon: Gift },
  { href: "/pickup", key: "nav_pickup", icon: Plus },
  { href: "/missions", key: "nav_missions", icon: Target },
  { href: "/activity", key: "nav_activity", icon: Receipt },
];

type Pref = "system" | "light" | "dark";
const THEME_ICON = { system: Monitor, light: Sun, dark: Moon };

/** Swap with a circular reveal from the tapped button when the browser supports View Transitions. */
function reveal(e: React.MouseEvent, change: () => void) {
  const doc = document as Document & { startViewTransition?: (cb: () => void) => { ready: Promise<void> } };
  if (!doc.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) return change();
  const { clientX: x, clientY: y } = e, r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  doc.startViewTransition(change).ready.then(() =>
    document.documentElement.animate({ clipPath: [`circle(0 at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
      { duration: 650, easing: "cubic-bezier(.2,.8,.2,1)", pseudoElement: "::view-transition-new(root)" }),
    () => {}); // a skipped transition (a second tap mid-flight, a hidden tab) rejects `ready`; the change itself still ran
}

/** One theme state for both toggle bars (sidebar and top bar are both mounted; CSS hides one). */
function useTheme() {
  const [saved, setPref] = useState<Pref | null>(null); // null until read: applying "system" first would flash the OS theme
  useEffect(() => { let p: Pref = "system"; try { const v = localStorage.getItem("theme"); if (v === "light" || v === "dark") p = v; } catch {} setPref(p); }, []);
  useEffect(() => {
    if (!saved) return; // the inline script in layout.tsx already set the saved theme before paint
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => (document.documentElement.dataset.theme = saved === "system" ? (mq.matches ? "dark" : "light") : saved);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [saved]);
  const choose = (p: Pref) => { setPref(p); try { localStorage.setItem("theme", p); } catch {} };
  return [saved ?? "system", choose] as const;
}

function Toggles({ pref, choose }: { pref: Pref; choose: (p: Pref) => void }) {
  const { t, locale, setLocale } = useI18n();
  const Icon = THEME_ICON[pref];
  const next: Pref = pref === "system" ? "light" : pref === "light" ? "dark" : "system";
  const btn = "chip press hit grid h-10 min-w-10 place-items-center rounded-full px-3 text-sm font-semibold"; // solid: these sit on glass bars
  return (
    <div className="flex gap-2">
      {/* named after the target language, in that language: the name contains the visible "EN"/"فا" */}
      <button className={btn} lang={locale === "fa" ? "en" : "fa"} aria-label={locale === "fa" ? "English" : "فارسی"} title={t("lang")} onClick={(e) => reveal(e, () => setLocale(locale === "fa" ? "en" : "fa"))}>
        {locale === "fa" ? "EN" : "فا"}
      </button>
      <button className={btn} aria-label={`${t("theme")}: ${t(`theme_${pref}`)}`} title={`${t("theme")}: ${t(`theme_${pref}`)}`}
        onClick={(e) => reveal(e, () => choose(next))}>
        <Icon size={18} />
      </button>
    </div>
  );
}

function Logo() {
  const { t } = useI18n();
  return (
    <Link href="/" className="hit flex items-center gap-3">
      <span className="grid size-10 place-items-center rounded-2xl bg-gradient-to-br from-brand to-brand-2 text-white shadow-lg shadow-brand/30">
        <Recycle size={22} strokeWidth={2.4} />
      </span>
      <span className="text-xl font-extrabold ltr:tracking-tight max-[359px]:text-lg">{t("brand")}</span>
    </Link>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const path = usePathname();
  const [pref, choose] = useTheme();
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));
  return (
    <>
      <a href="#main" className="sr-only z-50 rounded-full bg-fg px-5 py-3 font-semibold text-bg focus:not-sr-only focus:fixed focus:start-3 focus:top-3">{t("skip")}</a>
      <div className="aurora" aria-hidden><i /><i /><i /></div>

      {/* desktop sidebar */}
      <aside className="glass fixed inset-y-3 start-3 z-30 hidden w-64 flex-col rounded-[32px] p-5 md:flex">
        <Logo />
        <nav className="mt-10 grid gap-1">
          {[...NAV, { href: "/city", key: "nav_city" as Key, icon: Landmark }].map(({ href, key, icon: Icon }) => (
            <Link key={href} href={href} aria-current={active(href) ? "page" : undefined}
              className={`press flex items-center gap-3 rounded-2xl px-4 py-3 font-medium ${active(href) ? "bg-fg text-bg shadow-lg" : "text-muted hover:bg-line hover:text-fg"}`}>
              <Icon size={20} /> {t(key)}
            </Link>
          ))}
        </nav>
        <div className="mt-auto"><Toggles pref={pref} choose={choose} /></div>
      </aside>

      {/* mobile top bar */}
      <header className="glass sticky top-0 z-30 flex items-center justify-between gap-3 border-x-0 border-t-0 px-4 py-3 md:hidden">
        <Logo />
        <div className="flex items-center gap-2">
          <Link href="/city" aria-label={t("nav_city")} className="chip press hit grid size-10 place-items-center rounded-full"><Landmark size={18} /></Link>
          <Toggles pref={pref} choose={choose} />
        </div>
      </header>

      <main id="main" tabIndex={-1} className="px-4 pb-36 pt-6 outline-none md:ps-[19rem] md:pe-8 md:pt-10 md:pb-12"><div className="mx-auto max-w-6xl">{children}</div></main>

      {/* mobile tab bar */}
      <nav className="glass fixed inset-x-3 bottom-[max(.75rem,env(safe-area-inset-bottom))] z-30 flex items-center justify-around rounded-[28px] px-2 py-2 shadow-2xl md:hidden">
        {NAV.map(({ href, key, icon: Icon }) =>
          href === "/pickup" ? (
            <Link key={href} href={href} aria-label={t(key)}
              className="press -mt-9 grid size-16 shrink-0 place-items-center rounded-full bg-gradient-to-br from-brand-fill to-brand-fill-2 text-on-brand shadow-xl shadow-brand/40 ring-4 ring-bg">
              <Icon size={30} strokeWidth={2.6} />
            </Link>
          ) : (
            <Link key={href} href={href} aria-current={active(href) ? "page" : undefined}
              className={`press flex w-16 min-w-0 flex-col items-center gap-1 rounded-2xl py-1.5 text-[11px] font-medium max-[359px]:text-[10px] ${active(href) ? "text-brand-text" : "text-muted"}`}>
              <Icon size={22} strokeWidth={active(href) ? 2.5 : 2} /> <span className="max-w-full truncate">{t(key)}</span>
            </Link>
          ),
        )}
      </nav>
    </>
  );
}
