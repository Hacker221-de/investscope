import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Sidebar } from "@/components/sidebar";
import { AnalyticsBanner } from "@/components/ui";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "InvestScope", template: "%s · InvestScope" },
  description: "Инвестиционная аналитика и анализ введённых пользователем позиций портфеля.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ru">
      <body>
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
