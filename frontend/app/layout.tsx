import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Sidebar } from "@/components/sidebar";
import { AnalyticsBanner } from "@/components/ui";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "InvestScope", template: "%s · InvestScope" },
  description: "Investment research and analytics for user-entered portfolio positions.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <Sidebar />
        <div className="app-shell">
          <AnalyticsBanner />
          <main>{children}</main>
          <footer>InvestScope analytics · Market data is illustrative · Times shown in UTC · Not investment advice</footer>
        </div>
      </body>
    </html>
  );
}
