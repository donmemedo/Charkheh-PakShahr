import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import "@fontsource-variable/inter";
import "@fontsource-variable/vazirmatn";
import "./globals.css";
import { I18nProvider, type Locale } from "@/lib/i18n";
import { Shell } from "@/components/shell";

export const metadata: Metadata = {
  title: "SabzBank · سبزبانک",
  description: "Turn separated dry waste into points and rewards.",
};

export const viewport: Viewport = {
  viewportFit: "cover",
  themeColor: [{ media: "(prefers-color-scheme: light)", color: "#f2f2f7" }, { media: "(prefers-color-scheme: dark)", color: "#000000" }],
};

// runs before paint so the saved theme never flashes
const themeScript = `try{var p=localStorage.getItem("theme")||"system";document.documentElement.dataset.theme=p==="system"?(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"):p}catch(e){}`;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale: Locale = (await cookies()).get("lang")?.value === "en" ? "en" : "fa";
  return (
    <html lang={locale} dir={locale === "fa" ? "rtl" : "ltr"} suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
      <body className="font-sans antialiased">
        <I18nProvider initial={locale}><Shell>{children}</Shell></I18nProvider>
      </body>
    </html>
  );
}
