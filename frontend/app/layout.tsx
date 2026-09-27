import type { Metadata } from "next";
import localFont from "next/font/local";
import type { ReactNode } from "react";

import { Sidebar } from "@/components/sidebar";
import { AnalyticsBanner } from "@/components/ui";
import "./globals.css";

const plexSans = localFont({
  src: [
    { path: "./fonts/IBMPlexSans-Regular.woff2", weight: "400", style: "normal" },
    { path: "./fonts/IBMPlexSans-Medium.woff2", weight: "500", style: "normal" },
    { path: "./fonts/IBMPlexSans-SemiBold.woff2", weight: "600", style: "normal" },
    { path: "./fonts/IBMPlexSans-Bold.woff2", weight: "700", style: "normal" },
  ],
  variable: "--font-sans",
  display: "swap",
  adjustFontFallback: false,
  fallback: ["system-ui", "Segoe UI", "sans-serif"],
});

const plexMono = localFont({
  src: [
    { path: "./fonts/IBMPlexMono-Regular.woff2", weight: "400", style: "normal" },
    { path: "./fonts/IBMPlexMono-Medium.woff2", weight: "500", style: "normal" },
    { path: "./fonts/IBMPlexMono-SemiBold.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-mono",
  display: "swap",
  adjustFontFallback: false,
  fallback: ["ui-monospace", "Consolas", "monospace"],
});

export const metadata: Metadata = {
  title: { default: "InvestScope", template: "%s · InvestScope" },
  description: "Инвестиционная аналитика и анализ введённых пользователем позиций портфеля.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ru">
      <body className={`${plexSans.variable} ${plexMono.variable}`}>
        <Sidebar />
        <div className="app-shell">
          <AnalyticsBanner />
          <main>{children}</main>
          <footer>InvestScope · Рыночные данные демонстрационные · Время указано в UTC · Не является инвестиционной рекомендацией</footer>
        </div>
      </body>
    </html>
  );
}
