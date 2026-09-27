"use client";
import { createContext, useContext, useEffect, useState } from "react";

export type Locale = "fa" | "en";
export type L10n = { fa: string; en: string };

// Persian wording follows the Persian UX-writing vocabulary (پیش‌خوان، کیف پول، تراکنش، نشانی، فعال‌سازی، نادرست …)
const dict = {
  fa: {
    brand: "سبزبانک", tagline: "پسماندت را به امتیاز تبدیل کن",
    nav_home: "پیش‌خوان", nav_pickup: "درخواست", nav_rewards: "پاداش‌ها", nav_missions: "ماموریت‌ها", nav_activity: "تاریخچه", nav_city: "پیش‌خوان شهرداری",
    hello: "سلام", balance: "موجودی کیف پول", points: "امتیاز", pts: "امتیاز",
    tier_bronze: "برنزی", tier_silver: "نقره‌ای", tier_gold: "طلایی", to_next: "تا سطح", max_tier: "بالاترین سطح را دارید",
    impact: "اثر شما", kg_recycled: "کیلوگرم بازیافت", co2_saved: "کیلوگرم CO₂ کمتر", missions_done: "ماموریت انجام‌شده",
    trees: "درخت حفظ‌شده", landfill: "لیتر دفن کمتر",
    quick_pickup: "درخواست جمع‌آوری", quick_pickup_d: "جمع‌آوری پسماند خشک از درِ خانه", quick_rewards: "خرج امتیاز", quick_missions: "یاد بگیر و امتیاز بگیر",
    upcoming: "جمع‌آوری بعدی", no_upcoming: "درخواست فعالی ندارید", est: "امتیاز تخمینی",
    simulate: "شبیه‌سازی تحویل", simulate_d: "نسخه نمایشی: وزن‌کشی جمع‌آور را شبیه‌سازی کنید", cancel_req: "لغو درخواست",
    pickup_title: "درخواست جمع‌آوری", pickup_sub: "پسماند خشک تفکیک‌شده را انتخاب کنید و زمان مناسب را تعیین کنید.",
    step_what: "چه چیزی تحویل می‌دهید؟", step_when: "چه روزی؟", step_slot: "چه ساعتی؟", step_where: "نشانی",
    per_kg: "امتیاز برای هر کیلو", kg: "کیلو", address_ph: "مثلا تهران، یوسف‌آباد، خیابان ۳۳، پلاک ۱۲",
    confirm: "تایید درخواست", sending: "در حال ثبت…", total: "مجموع", select_one: "دست‌کم یک مورد را انتخاب کنید",
    address_err: "اینجا نباید خالی باشد", today: "امروز",
    done_title: "درخواست ثبت شد!", done_sub: "جمع‌آور در بازه انتخابی به نشانی شما می‌آید. امتیاز پس از وزن‌کشی تاییدشده به کیف پول شما اضافه می‌شود.",
    back_home: "بازگشت به پیش‌خوان",
    rewards_title: "فروشگاه پاداش", rewards_sub: "امتیازهایتان را نزد شرکای سبزبانک خرج کنید.",
    cat_all: "همه", cat_transport: "حمل‌ونقل", cat_food: "خوراک و تفریح", cat_shopping: "خرید", cat_digital: "دیجیتال", cat_impact: "اثر سبز",
    redeem: "فعال‌سازی", need_more: "امتیاز کم دارید", redeem_q: "این پاداش فعال شود؟", redeem_cost: "از کیف پول شما کسر می‌شود",
    cancel: "انصراف", redeemed: "پاداش فعال شد", your_code: "کد تخفیف شما", copy: "کپی", copied: "کپی شد", ok: "تایید",
    missions_title: "ماموریت‌ها", missions_sub: "با پاسخ به پرسش‌های کوتاه، تفکیک درست را یاد بگیرید.",
    correct: "آفرین! پاسخ درست است", wrong: "پاسخ نادرست است؛ دوباره امتحان کنید", done: "انجام شد",
    league: "لیگ محله", league_sub: "رتبه منطقه‌ها بر اساس امتیاز این فصل", you: "منطقه شما",
    activity_title: "تاریخچه", tab_pickups: "درخواست‌ها", tab_txns: "تراکنش‌ها", empty: "هنوز چیزی اینجا نیست",
    st_scheduled: "در انتظار جمع‌آوری", st_delivered: "تحویل‌شده", st_canceled: "لغوشده",
    tx_pickup: "تحویل پسماند", tx_redeem: "فعال‌سازی پاداش", tx_mission: "ماموریت", weight: "وزن تاییدشده",
    city_title: "پیش‌خوان شهرداری", city_sub: "داده زنده پایلوت سبزبانک در مناطق تهران",
    k_tons: "تن پسماند خشک", k_mau: "کاربر فعال ماهانه", k_part: "نرخ مشارکت", k_landfill: "تن دفن کمتر", k_co2: "تن CO₂ کمتر", k_partners: "شریک پاداش",
    monthly: "روند ماهانه جمع‌آوری (تن)", mix: "ترکیب پسماند", districts: "رتبه منطقه‌ها",
    theme: "پوسته", lang: "زبان", error: "ارتباط با سرور برقرار نشد", retry: "تلاش دوباره",
  },
  en: {
    brand: "SabzBank", tagline: "Turn your waste into rewards",
    nav_home: "Dashboard", nav_pickup: "Pickup", nav_rewards: "Rewards", nav_missions: "Missions", nav_activity: "History", nav_city: "City dashboard",
    hello: "Hi", balance: "Wallet balance", points: "points", pts: "pts",
    tier_bronze: "Bronze", tier_silver: "Silver", tier_gold: "Gold", to_next: "to", max_tier: "You're at the top tier",
    impact: "Your impact", kg_recycled: "kg recycled", co2_saved: "kg CO₂ avoided", missions_done: "missions done",
    trees: "trees saved", landfill: "L landfill avoided",
    quick_pickup: "Request pickup", quick_pickup_d: "Doorstep collection of dry waste", quick_rewards: "Spend points", quick_missions: "Learn & earn",
    upcoming: "Next pickup", no_upcoming: "No active requests", est: "est. points",
    simulate: "Simulate delivery", simulate_d: "Demo: simulate the collector weighing your bags", cancel_req: "Cancel request",
    pickup_title: "Request a pickup", pickup_sub: "Choose your separated dry waste and a time that suits you.",
    step_what: "What are you handing in?", step_when: "Which day?", step_slot: "What time?", step_where: "Address",
    per_kg: "pts per kg", kg: "kg", address_ph: "e.g. Tehran, Yousefabad, 33rd St, No. 12",
    confirm: "Confirm request", sending: "Sending…", total: "Total", select_one: "Select at least one item",
    address_err: "This can't be empty", today: "Today",
    done_title: "Request received!", done_sub: "A collector will come to your address in the chosen window. Points land in your wallet after verified weighing.",
    back_home: "Back to dashboard",
    rewards_title: "Rewards store", rewards_sub: "Spend your points with SabzBank partners.",
    cat_all: "All", cat_transport: "Transport", cat_food: "Food & fun", cat_shopping: "Shopping", cat_digital: "Digital", cat_impact: "Green impact",
    redeem: "Redeem", need_more: "Not enough points", redeem_q: "Redeem this reward?", redeem_cost: "will be deducted from your wallet",
    cancel: "Cancel", redeemed: "Reward redeemed", your_code: "Your code", copy: "Copy", copied: "Copied", ok: "OK",
    missions_title: "Missions", missions_sub: "Answer short questions and learn to sort right.",
    correct: "Nice! That's correct", wrong: "Not quite — try again", done: "Done",
    league: "Neighborhood league", league_sub: "District ranking by points this season", you: "Your district",
    activity_title: "History", tab_pickups: "Requests", tab_txns: "Transactions", empty: "Nothing here yet",
    st_scheduled: "Awaiting pickup", st_delivered: "Delivered", st_canceled: "Canceled",
    tx_pickup: "Waste delivered", tx_redeem: "Reward redeemed", tx_mission: "Mission", weight: "Verified weight",
    city_title: "City dashboard", city_sub: "Live data from the SabzBank pilot across Tehran districts",
    k_tons: "tons of dry waste", k_mau: "monthly active users", k_part: "participation rate", k_landfill: "t landfill avoided", k_co2: "t CO₂ avoided", k_partners: "reward partners",
    monthly: "Monthly collection (tons)", mix: "Waste mix", districts: "District ranking",
    theme: "Theme", lang: "Language", error: "Couldn't reach the server", retry: "Retry",
  },
};
export type Key = keyof typeof dict.fa;

type Ctx = { locale: Locale; setLocale: (l: Locale) => void; t: (k: Key) => string; n: (x: number, digits?: number) => string; pick: (v: L10n) => string };
const I18n = createContext<Ctx>(null!);

export function I18nProvider({ initial, children }: { initial: Locale; children: React.ReactNode }) {
  const [locale, setLocale] = useState(initial);
  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === "fa" ? "rtl" : "ltr";
    document.cookie = `lang=${locale};path=/;max-age=31536000;samesite=lax`;
  }, [locale]);
  const nf = locale === "fa" ? "fa-IR" : "en-US";
  const value: Ctx = {
    locale, setLocale,
    t: (k) => dict[locale][k],
    n: (x, digits = 0) => x.toLocaleString(nf, { maximumFractionDigits: digits }),
    pick: (v) => v[locale],
  };
  return <I18n.Provider value={value}>{children}</I18n.Provider>;
}

export const useI18n = () => useContext(I18n);

export function formatDay(iso: string, locale: Locale, opts: Intl.DateTimeFormatOptions = { weekday: "short", day: "numeric", month: "short" }) {
  return new Date(iso + (iso.length === 10 ? "T12:00:00" : "")).toLocaleDateString(locale === "fa" ? "fa-IR-u-ca-persian" : "en-US", opts);
}
