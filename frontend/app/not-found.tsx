"use client";
import Link from "next/link";
import { useI18n } from "@/lib/i18n";

// unmatched URLs: a localized page inside the shell, not Next's English default
export default function NotFound() {
  const { t } = useI18n();
  return (
    <div className="card flex flex-col items-center gap-4 p-10 text-center">
      <h1 className="text-xl font-bold">{t("not_found")}</h1>
      <Link href="/" className="btn btn-primary press">{t("back_home")}</Link>
    </div>
  );
}
