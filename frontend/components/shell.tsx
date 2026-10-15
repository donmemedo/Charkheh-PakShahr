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
      { duration: 650, easing: "cubic-bezier(.2,.8,.2,1)", pseudoElement: "::view-transition-new(root)" }));
}

function Toggles() {
  const { t, locale, setLocale } = useI18n();
  const [pref, setPref] = useState<Pref>("system");
  useEffect(() => { try { setPref((localStorage.getItem("theme") as Pref) || "system"); } catch {} }, []);
  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const apply = () => (document.documentElement.dataset.theme = pref === "system" ? (mq.matches ? "dark" : "light") : pref);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [pref]);
  const Icon = THEME_ICON[pref];
  const next: Pref = pref === "system" ? "light" : pref === "light" ? "dark" : "system";
  const btn = "chip press grid h-10 min-w-10 place-items-center rounded-full px-3 text-sm font-semibold"; // solid: these sit on glass bars
  return (
    <div className="flex gap-2">
      <button className={btn} aria-label={t("lang")} onClick={(e) => reveal(e, () => setLocale(locale === "fa" ? "en" : "fa"))}>
        {locale === "fa" ? "EN" : "فا"}
      </button>
      <button className={btn} aria-label={`${t("theme")}: ${pref}`} title={pref}
        onClick={(e) => reveal(e, () => { setPref(next); try { localStorage.setItem("theme", next); } catch {} })}>
        <Icon size={18} />
      </button>
    </div>
  );
}

function Logo() {
  const { t } = useI18n();
  return (
    <Link href="/" className="flex items-center gap-3">
      <span className="grid size-10 place-items-center rounded-2xl bg-gradient-to-br from-brand to-brand-2 text-white shadow-lg shadow-brand/30">
        <Recycle size={22} strokeWidth={2.4} />
      </span>
      <span className="text-xl font-extrabold ltr:tracking-tight">{t("brand")}</span>
    </Link>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const path = usePathname();
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));
  // decorative background motion: off on weak devices (see globals.css); hidden tabs skip rendering it anyway
  useEffect(() => {
    const nav = navigator as Navigator & { deviceMemory?: number };
    document.documentElement.classList.toggle("low-power", (nav.hardwareConcurrency ?? 8) <= 4 || (nav.deviceMemory ?? 8) <= 4);
  }, []);
  return (
    <>
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
        <div className="mt-auto"><Toggles /></div>
      </aside>

      {/* mobile top bar */}
      <header className="glass sticky top-0 z-30 flex items-center justify-between border-x-0 border-t-0 px-4 py-3 md:hidden">
        <Logo />
        <div className="flex items-center gap-2">
          <Link href="/city" aria-label={t("nav_city")} className="chip press grid size-10 place-items-center rounded-full"><Landmark size={18} /></Link>
          <Toggles />
        </div>
      </header>

      <main className="px-4 pb-36 pt-6 md:ps-[19rem] md:pe-8 md:pt-10 md:pb-12"><div className="mx-auto max-w-6xl">{children}</div></main>

      {/* mobile tab bar */}
      <nav className="glass fixed inset-x-3 bottom-[max(.75rem,env(safe-area-inset-bottom))] z-30 flex items-center justify-around rounded-[28px] px-2 py-2 shadow-2xl md:hidden">
        {NAV.map(({ href, key, icon: Icon }) =>
          href === "/pickup" ? (
            <Link key={href} href={href} aria-label={t(key)}
              className="press -mt-9 grid size-16 place-items-center rounded-full bg-gradient-to-br from-brand to-brand-2 text-white shadow-xl shadow-brand/40 ring-4 ring-bg">
              <Icon size={30} strokeWidth={2.6} />
            </Link>
          ) : (
            <Link key={href} href={href} aria-current={active(href) ? "page" : undefined}
              className={`press flex w-16 flex-col items-center gap-1 rounded-2xl py-1.5 text-[11px] font-medium ${active(href) ? "text-brand" : "text-muted"}`}>
              <Icon size={22} strokeWidth={active(href) ? 2.5 : 2} /> {t(key)}
            </Link>
          ),
        )}
      </nav>
    </>
  );
}
